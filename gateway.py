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
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client, config_validation as cv

from homeassistant.const import (
    CONF_IP_ADDRESS, 
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
    DOMAIN,
    LOGGER,
)

_LOGGER = logging.getLogger(__name__)

class MyHOMEGateway:
    """Manages a single MyHOME Gateway."""

    def __init__(self, hass, config_entry):
        build_info = {
            "address": config_entry.data[CONF_IP_ADDRESS],
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

        self.gateway = OWNGateway(build_info)
        self.test_session = OWNSession(gateway=self.gateway, logger=LOGGER)
        self.event_session = OWNEventSession(gateway=self.gateway, logger=LOGGER)

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

    async def test(self) -> bool:
        result = await self.test_session.test_connection()
        return result["Success"]

    async def connect(self) -> None:
        await self.event_session.connect()

    async def listening_loop(self):
        while True:
            message = await self.event_session.get_next()
            if message:
                LOGGER.debug("Received: %s", message)
                if message.is_event():
                    LOGGER.info(message.human_readable_log)
    