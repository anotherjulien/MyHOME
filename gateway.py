"""Code to handle a MyHome Gateway."""
import asyncio
from functools import partial
import logging

from OWNd.connection import OWNSession, OWNEventSession, OWNCommandSession, OWNGateway
from OWNd.message import *

from aiohttp import client_exceptions
import async_timeout
import slugify as unicode_slug
import voluptuous as vol

from homeassistant import core
from homeassistant.core import EVENT_HOMEASSISTANT_STOP
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client, config_validation as cv

from homeassistant.const import (
    CONF_HOST,
    CONF_PORT, 
    CONF_PASSWORD, 
    CONF_NAME, 
    CONF_MAC, 
    CONF_ID, 
    CONF_FRIENDLY_NAME,
)
from homeassistant.helpers import aiohttp_client

from .const import (
    CONF_FIRMWARE,
    CONF_SSDP_LOCATION,
    CONF_SSDP_ST,
    CONF_DEVICE_TYPE,
    CONF_MANUFACTURER,
    CONF_MANUFACTURER_URL,
    CONF_UDN,
    CONF_PARENT_ID,
    CONF_SHORT_PRESS,
    CONF_SHORT_RELEASE,
    CONF_LONG_PRESS,
    CONF_LONG_RELEASE,
    DOMAIN,
    LOGGER,
)

_LOGGER = logging.getLogger(__name__)

class MyHOMEGateway:
    """Manages a single MyHOME Gateway."""

    def __init__(self, hass, config_entry):
        build_info = {
            "address": config_entry.data[CONF_HOST],
            "port": config_entry.data[CONF_PORT],
            "password": config_entry.data[CONF_PASSWORD],
            "ssdp_location": config_entry.data[CONF_SSDP_LOCATION],
            "ssdp_st": config_entry.data[CONF_SSDP_ST],
            "deviceType": config_entry.data[CONF_DEVICE_TYPE],
            "friendlyName": config_entry.data[CONF_FRIENDLY_NAME],
            "manufacturer": config_entry.data[CONF_MANUFACTURER],
            "manufacturerURL": config_entry.data[CONF_MANUFACTURER_URL],
            "modelName": config_entry.data[CONF_NAME],
            "modelNumber": config_entry.data[CONF_FIRMWARE],
            "serialNumber": config_entry.data[CONF_MAC],
            "UDN": config_entry.data[CONF_UDN],
        }
        self.hass = hass
        self.config_entry =  config_entry
        self.gateway = OWNGateway(build_info)
        self.test_session = OWNSession(gateway=self.gateway, logger=LOGGER)
        self.event_session = OWNEventSession(gateway=self.gateway, logger=LOGGER)
        self._terminate_listener = False
        self.is_connected = False
        self.listening_task: asyncio.tasks.Task
        self._lights = {}
        self._switches = {}
        self._binary_sensors = {}
        self._covers = {}
        self._sensors = {}
        self._climate_zones = {}

    @property
    def mac(self) -> str:
        return self.gateway.serial

    @property
    def id(self) -> str:
        return self.mac

    @property
    def manufacturer(self) -> str:
        return self.gateway.manufacturer
    
    @property
    def name(self) -> str:
        return f"{self.gateway.modelName} Gateway"

    @property
    def model(self) -> str:
        return self.gateway.modelName

    @property
    def firmware(self) -> str:
        return self.gateway.firmware

    def add_light(self, where: str, parameters: dict) -> None:
        self._lights[where] = parameters

    def get_lights(self) -> dict:
        return self._lights
    
    def add_switch(self, where: str, parameters: dict) -> None:
        self._switches[where] = parameters

    def get_switches(self) -> dict:
        return self._switches
    
    def add_binary_sensor(self, where: str, parameters: dict) -> None:
        self._binary_sensors[where] = parameters

    def get_binary_sensors(self) -> dict:
        return self._binary_sensors
    
    def add_cover(self, where: str, parameters: dict) -> None:
        self._covers[where] = parameters

    def get_covers(self) -> dict:
        return self._covers
    
    def add_sensor(self, where: str, parameters: dict) -> None:
        self._sensors[where] = parameters

    def get_sensors(self) -> dict:
        return self._sensors

    def add_climate_zone(self, zone: str, parameters: dict) -> None:
        self._climate_zone[zone] = parameters

    def get_climate_zones(self) -> dict:
        return self._climate_zone

    async def test(self) -> bool:
        result = await self.test_session.test_connection()
        return result["Success"]

    async def build_lights_list(self) -> list:
        await self.connect()
        await self.send(OWNCommand(""))

    async def connect(self) -> None:
        await self.event_session.connect()
        #self.hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, self.close_listener)
        self.is_connected = True

    async def listening_loop(self):

        self._terminate_listener = False
        while not self._terminate_listener:
            message = await self.event_session.get_next()
            LOGGER.debug("Received: %s", message)
            if not message:
                LOGGER.info("Received: %s", message)
            elif isinstance(message, OWNEnergyEvent) or isinstance(message, OWNLightingEvent) or isinstance(message, OWNAutomationEvent) or isinstance(message, OWNDryContactEvent) or isinstance(message, OWNHeatingEvent):
                if not message.is_translation():
                    if message.unique_id in self.hass.data[DOMAIN]:
                        self.hass.data[DOMAIN][message.unique_id].handle_event(message)
                    else:
                        LOGGER.warning("Unknown device: WHO=%s WHERE=%s", message.who, message.where)
                else:
                    LOGGER.debug("Ignoring translation message %s", message)
            elif isinstance(message, OWNCENPlusEvent):
                event = None
                if message.is_short_pressed:
                    event = CONF_SHORT_PRESS
                elif message.is_held or message.is_still_held:
                    event = CONF_LONG_PRESS
                elif message.is_released:
                    event = CONF_LONG_RELEASE
                else:
                    event = None
                self.hass.bus.async_fire(
                    "myhome_cenplus_event",
                    {"object": int(message.object), "pushbutton": int(message.push_button), "event": event},
                )
                LOGGER.info(message.human_readable_log)
            elif isinstance(message, OWNCENEvent):
                event = None
                if message.is_pressed:
                    event = CONF_SHORT_PRESS
                elif message.is_released_after_short_press:
                    event = CONF_SHORT_RELEASE
                elif message.is_held:
                    event = CONF_LONG_PRESS
                elif message.is_released_after_long_press:
                    event = CONF_LONG_RELEASE
                else:
                    event = None
                self.hass.bus.async_fire(
                    "myhome_cen_event",
                    {"object": int(message.object), "pushbutton": int(message.push_button), "event": event},
                )
                LOGGER.info(message.human_readable_log)
            elif isinstance(message, OWNGatewayEvent) or isinstance(message, OWNGatewayCommand):
                LOGGER.info(message.human_readable_log)
            else:
                LOGGER.info("Unsupported message type: %s", message)


    async def close_listener(self, event=None) -> None:
        LOGGER.info("Closing event listener")
        self._terminate_listener = True
        await self.event_session.close()
        self.is_connected = False
        self.listening_task.cancel()
    
    async def send(self, message: OWNCommand):
        command_session = OWNCommandSession(gateway=self.gateway, logger=LOGGER)
        await command_session.send(message=message)
    
    async def send_status_request(self, message: OWNCommand):
        command_session = OWNCommandSession(gateway=self.gateway, logger=LOGGER)
        await command_session.send(message=message, is_status_request=True)