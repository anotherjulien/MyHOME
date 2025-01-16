"""Support for MyHome covers."""
from homeassistant.components.cover import (
    ATTR_POSITION,
    DOMAIN as PLATFORM,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)

from homeassistant.const import (
    CONF_NAME,
    CONF_MAC,
)

from OWNd.message import (
    OWNAutomationEvent,
    OWNAutomationCommand,
)

from .const import (
    CONF_PLATFORMS,
    CONF_ENTITY,
    CONF_ENTITY_NAME,
    CONF_WHO,
    CONF_WHERE,
    CONF_BUS_INTERFACE,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_ADVANCED_SHUTTER,
    DOMAIN,
    LOGGER,
    CONF_SHUTTER_OPENING_TIME,
    CONF_SHUTTER_CLOSING_TIME,
)
from .myhome_device import MyHOMEEntity
from .gateway import MyHOMEGatewayHandler
from datetime import datetime
import asyncio

async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    _covers = []
    _configured_covers = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM]

    for _cover in _configured_covers.keys():
        _cover = MyHOMECover(
            hass=hass,
            device_id=_cover,
            who=_configured_covers[_cover][CONF_WHO],
            where=_configured_covers[_cover][CONF_WHERE],
            interface=_configured_covers[_cover][CONF_BUS_INTERFACE] if CONF_BUS_INTERFACE in _configured_covers[_cover] else None,
            name=_configured_covers[_cover][CONF_NAME],
            entity_name=_configured_covers[_cover][CONF_ENTITY_NAME],
            advanced=_configured_covers[_cover][CONF_ADVANCED_SHUTTER],
            manufacturer=_configured_covers[_cover][CONF_MANUFACTURER],
            model=_configured_covers[_cover][CONF_DEVICE_MODEL],
            gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
            opening_time=_configured_covers[_cover][CONF_SHUTTER_OPENING_TIME],
            closing_time=_configured_covers[_cover][CONF_SHUTTER_CLOSING_TIME],
        )
        _covers.append(_cover)

    async_add_entities(_covers)


async def async_unload_entry(hass, config_entry):  # pylint: disable=unused-argument
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    _configured_covers = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM]

    for _cover in _configured_covers.keys():
        del hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM][_cover]


class MyHOMECover(MyHOMEEntity, CoverEntity):
    device_class = CoverDeviceClass.SHUTTER

    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        advanced: bool,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
        opening_time: int,
        closing_time: int
    ):
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._attr_name = entity_name

        self._interface = interface
        self._full_where = f"{self._where}#4#{self._interface}" if self._interface is not None else self._where
        self._attr_opening_time = opening_time
        self._attr_closing_time = closing_time
        self._attr_advanced = advanced

        self._attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        if advanced:
            self._attr_supported_features |= CoverEntityFeature.SET_POSITION
        elif opening_time > 0 and closing_time > 0:
            self._attr_supported_features |= CoverEntityFeature.SET_POSITION
        self._gateway_handler = gateway

        self._attr_extra_state_attributes = {
            "A": where[: len(where) // 2],
            "PL": where[len(where) // 2 :],
        }
        if self._interface is not None:
            self._attr_extra_state_attributes["Int"] = self._interface

        self._attr_current_cover_position = None
        self._attr_is_opening = None
        self._attr_is_closing = None
        self._attr_is_closed = None
        self._attr_last_event = datetime.now()

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway_handler.send_status_request(OWNAutomationCommand.status(self._full_where))

    async def async_open_cover(self, **kwargs):  # pylint: disable=unused-argument
        """Open the cover."""
        await self._gateway_handler.send(OWNAutomationCommand.raise_shutter(self._full_where))

    async def async_close_cover(self, **kwargs):  # pylint: disable=unused-argument
        """Close cover."""
        await self._gateway_handler.send(OWNAutomationCommand.lower_shutter(self._full_where))

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        if ATTR_POSITION in kwargs:
            position = kwargs[ATTR_POSITION]
            if self._attr_advanced:
                await self._gateway_handler.send(OWNAutomationCommand.set_shutter_level(self._full_where, position))
            elif self._attr_opening_time > 0 or self._attr_closing_time > 0:

                if self._attr_is_closing or self._attr_is_closing:
                    await self._gateway_handler.send(OWNAutomationCommand.stop_shutter(self._full_where))

                if self._attr_current_cover_position is None:
                    return                

                required_move = int(position - self._attr_current_cover_position)
                if required_move > 0:
                    """ open """
                    required_time = abs(self._attr_opening_time * required_move / 100)
                    LOGGER.debug(
                        "Open -> Required time %s",
                        required_time,
                    )
                    await self._gateway_handler.send(OWNAutomationCommand.raise_shutter(self._full_where))
                    await asyncio.sleep(required_time)
                    await self._gateway_handler.send(OWNAutomationCommand.stop_shutter(self._full_where))
                elif required_move < 0:
                    """ close """
                    required_time = abs(self._attr_closing_time * required_move / 100)
                    LOGGER.debug(
                        "Close -> Required time %s",
                        required_time,
                    )
                    await self._gateway_handler.send(OWNAutomationCommand.lower_shutter(self._full_where))
                    await asyncio.sleep(required_time)
                    await self._gateway_handler.send(OWNAutomationCommand.stop_shutter(self._full_where))


    async def async_stop_cover(self, **kwargs):  # pylint: disable=unused-argument
        """Stop the cover."""
        await self._gateway_handler.send(OWNAutomationCommand.stop_shutter(self._full_where))

    def handle_event(self, message: OWNAutomationEvent):
        """Handle an event message."""
        LOGGER.info(
            "%s %s",
            self._gateway_handler.log_id,
            message.human_readable_log,
        )
        
        if message.current_position is not None:
            self._attr_current_cover_position = message.current_position
        elif self._attr_last_event is not None and self._attr_opening_time > 0 and self._attr_closing_time > 0:
            elapsed_seconds = (datetime.now() - self._attr_last_event).total_seconds()
            if elapsed_seconds > 0:
                if self._attr_is_opening:
                    if self._attr_opening_time < elapsed_seconds:
                        self._attr_current_cover_position = 100
                    elif (self._attr_current_cover_position is not None):
                        self._attr_current_cover_position = round(min(100, self._attr_current_cover_position + (100 * elapsed_seconds / self._attr_opening_time)), 0)
                elif self._attr_is_closing:
                    if self._attr_closing_time < elapsed_seconds:
                        self._attr_current_cover_position = 0
                    elif self._attr_current_cover_position is not None:
                        self._attr_current_cover_position = round(max(0, self._attr_current_cover_position - (100 * elapsed_seconds / self._attr_closing_time)), 0)

            LOGGER.debug(
                "%s %s",
                self._gateway_handler.log_id,
                self._attr_current_cover_position,
            )

        self._attr_last_event = datetime.now()
        self._attr_is_opening = message.is_opening
        self._attr_is_closing = message.is_closing
        if message.is_closed is not None:
            self._attr_is_closed = message.is_closed
        elif self._attr_current_cover_position is not None:
            self._attr_is_closed = self._attr_current_cover_position == 0

        self.async_schedule_update_ha_state()