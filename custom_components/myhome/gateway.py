"""Code to handle a MyHome Gateway."""
import asyncio
from typing import Dict, List

from homeassistant.const import (
    CONF_ENTITIES,
    CONF_HOST,
    CONF_PORT,
    CONF_PASSWORD,
    CONF_NAME,
    CONF_MAC,
    CONF_FRIENDLY_NAME,
)

from OWNd.connection import OWNSession, OWNEventSession, OWNCommandSession, OWNGateway
from OWNd.message import (
    OWNLightingEvent,
    OWNLightingCommand,
    OWNEnergyEvent,
    OWNAutomationEvent,
    OWNDryContactEvent,
    OWNAuxEvent,
    OWNHeatingEvent,
    OWNHeatingCommand,
    OWNCENPlusEvent,
    OWNCENEvent,
    OWNGatewayEvent,
    OWNGatewayCommand,
    OWNCommand,
)

from .const import (
    CONF_FIRMWARE,
    CONF_SSDP_LOCATION,
    CONF_SSDP_ST,
    CONF_DEVICE_TYPE,
    CONF_MANUFACTURER,
    CONF_MANUFACTURER_URL,
    CONF_UDN,
    CONF_SHORT_PRESS,
    CONF_SHORT_RELEASE,
    CONF_LONG_PRESS,
    CONF_LONG_RELEASE,
    DOMAIN,
    LOGGER,
)


class MyHOMEGatewayHandler:
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
        self.config_entry = config_entry
        self.gateway = OWNGateway(build_info)
        self._terminate_listener = False
        self._terminate_sender = False
        self.is_connected = False
        self.listening_worker: asyncio.tasks.Task = None
        self.sending_workers: List[asyncio.tasks.Task] = []
        self.send_buffer = asyncio.Queue()

    @property
    def mac(self) -> str:
        return self.gateway.serial

    @property
    def unique_id(self) -> str:
        return self.mac

    @property
    def manufacturer(self) -> str:
        return self.gateway.manufacturer

    @property
    def name(self) -> str:
        return f"{self.gateway.model_name} Gateway"

    @property
    def model(self) -> str:
        return self.gateway.model_name

    @property
    def firmware(self) -> str:
        return self.gateway.firmware

    async def test(self) -> Dict:
        return await OWNSession(gateway=self.gateway, logger=LOGGER).test_connection()

    async def listening_loop(self):

        self._terminate_listener = False

        LOGGER.debug("Creating listening worker.")

        _event_session = OWNEventSession(gateway=self.gateway, logger=LOGGER)
        await _event_session.connect()
        self.is_connected = True

        while not self._terminate_listener:
            message = await _event_session.get_next()
            LOGGER.debug("Received: %s", message)
            if not message:
                LOGGER.warning("Data received is not a message: %s", message)
            elif isinstance(message, OWNEnergyEvent):
                if message.entity in self.hass.data[DOMAIN][CONF_ENTITIES]:
                    self.hass.data[DOMAIN][CONF_ENTITIES][message.entity].handle_event(
                        message
                    )
                else:
                    continue
            elif (
                isinstance(message, OWNLightingEvent)
                or isinstance(message, OWNAutomationEvent)
                or isinstance(message, OWNDryContactEvent)
                or isinstance(message, OWNAuxEvent)
                or isinstance(message, OWNHeatingEvent)
            ):
                if not message.is_translation:
                    is_event = False
                    if isinstance(message, OWNLightingEvent):
                        if message.is_general:
                            is_event = True
                            event = "on" if message.is_on else "off"
                            self.hass.bus.async_fire(
                                "myhome_general_light_event",
                                {"message": str(message), "event": event},
                            )
                            await asyncio.sleep(0.1)
                            await self.send_status_request(
                                OWNLightingCommand.status("0")
                            )
                        elif message.is_area:
                            is_event = True
                            event = "on" if message.is_on else "off"
                            self.hass.bus.async_fire(
                                "myhome_area_light_event",
                                {
                                    "message": str(message),
                                    "area": message.area,
                                    "event": event,
                                },
                            )
                            await asyncio.sleep(0.1)
                            await self.send_status_request(
                                OWNLightingCommand.status(message.area)
                            )
                        elif message.is_group:
                            is_event = True
                            event = "on" if message.is_on else "off"
                            self.hass.bus.async_fire(
                                "myhome_group_light_event",
                                {
                                    "message": str(message),
                                    "group": message.group,
                                    "event": event,
                                },
                            )
                    elif isinstance(message, OWNAutomationEvent):
                        if message.is_general:
                            is_event = True
                            if message.is_opening and not message.is_closing:
                                event = "open"
                            elif message.is_closing and not message.is_opening:
                                event = "close"
                            else:
                                event = "stop"
                            self.hass.bus.async_fire(
                                "myhome_general_automation_event",
                                {"message": str(message), "event": event},
                            )
                        elif message.is_area:
                            is_event = True
                            if message.is_opening and not message.is_closing:
                                event = "open"
                            elif message.is_closing and not message.is_opening:
                                event = "close"
                            else:
                                event = "stop"
                            self.hass.bus.async_fire(
                                "myhome_area_automation_event",
                                {
                                    "message": str(message),
                                    "area": message.area,
                                    "event": event,
                                },
                            )
                        elif message.is_group:
                            is_event = True
                            if message.is_opening and not message.is_closing:
                                event = "open"
                            elif message.is_closing and not message.is_opening:
                                event = "close"
                            else:
                                event = "stop"
                            self.hass.bus.async_fire(
                                "myhome_group_automation_event",
                                {
                                    "message": str(message),
                                    "group": message.group,
                                    "event": event,
                                },
                            )
                    if not is_event:
                        if message.entity in self.hass.data[DOMAIN][CONF_ENTITIES]:
                            if (
                                isinstance(message, OWNLightingEvent)
                                and message.brightness_preset
                            ):
                                await self.hass.data[DOMAIN][CONF_ENTITIES][
                                    message.entity
                                ].async_update()
                            else:
                                self.hass.data[DOMAIN][CONF_ENTITIES][
                                    message.entity
                                ].handle_event(message)
                        else:
                            LOGGER.warning(
                                "Unknown device: WHO=%s WHERE=%s",
                                message.who,
                                message.where,
                            )
                else:
                    LOGGER.debug("Ignoring translation message %s", message)
            elif (
                isinstance(message, OWNHeatingCommand)
                and message.dimension is not None
                and message.dimension == 14
            ):
                where = (
                    message.where[1:]
                    if message.where.startswith("#")
                    else message.where
                )
                LOGGER.debug(
                    "Received heating command, sending query to zone %s", where
                )
                await self.send_status_request(OWNHeatingCommand.status(where))
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
                    {
                        "object": int(message.object),
                        "pushbutton": int(message.push_button),
                        "event": event,
                    },
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
                    {
                        "object": int(message.object),
                        "pushbutton": int(message.push_button),
                        "event": event,
                    },
                )
                LOGGER.info(message.human_readable_log)
            elif isinstance(message, OWNGatewayEvent) or isinstance(
                message, OWNGatewayCommand
            ):
                LOGGER.info(message.human_readable_log)
            else:
                LOGGER.info("Unsupported message type: %s", message)

        await _event_session.close()
        self.is_connected = False

        LOGGER.debug("Destroying listening worker.")
        self.listening_worker.cancel()

    async def sending_loop(self, worker_id: int):

        self._terminate_sender = False

        LOGGER.debug("Creating sending worker %s", worker_id)

        _command_session = OWNCommandSession(gateway=self.gateway, logger=LOGGER)
        await _command_session.connect()

        while not self._terminate_sender:
            task = await self.send_buffer.get()
            LOGGER.debug(
                "Message %s was successfully unqueued by worker %s.",
                task["message"],
                worker_id,
            )
            await _command_session.send(
                message=task["message"], is_status_request=task["is_status_request"]
            )
            self.send_buffer.task_done()

        await _command_session.close()

        LOGGER.debug("Destroying sending worker %s", worker_id)
        self.sending_workers[worker_id].cancel()

    async def close_listener(self) -> bool:
        LOGGER.info("Closing event listener")
        self._terminate_sender = True
        self._terminate_listener = True

        return True

    async def send(self, message: OWNCommand):
        await self.send_buffer.put({"message": message, "is_status_request": False})
        LOGGER.debug("Message %s was successfully queued.", message)

    async def send_status_request(self, message: OWNCommand):
        await self.send_buffer.put({"message": message, "is_status_request": True})
        LOGGER.debug("Message %s was successfully queued.", message)
