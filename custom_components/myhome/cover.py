"""Support for MyHome covers."""
from homeassistant.components.cover import (
    ATTR_POSITION,
    DOMAIN as PLATFORM,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
    CoverState,
)
from homeassistant.helpers.restore_state import RestoreEntity

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
)
from .myhome_device import MyHOMEEntity
from .gateway import MyHOMEGatewayHandler


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
        )
        _covers.append(_cover)

    async_add_entities(_covers)


async def async_unload_entry(hass, config_entry):  # pylint: disable=unused-argument
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    _configured_covers = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM]

    for _cover in _configured_covers.keys():
        del hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM][_cover]


class MyHOMECover(MyHOMEEntity, CoverEntity, RestoreEntity):
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

        self._attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        self._supports_position = advanced
        if advanced:
            self._attr_supported_features |= CoverEntityFeature.SET_POSITION
        self._gateway_handler = gateway
        self._attr_assumed_state = True

        self._attr_extra_state_attributes = {
            "A": where[: len(where) // 2],
            "PL": where[len(where) // 2 :],
        }
        if self._interface is not None:
            self._attr_extra_state_attributes["Int"] = self._interface

        self._attr_current_cover_position = None
        self._attr_is_opening = False
        self._attr_is_closing = False
        self._attr_is_closed = None

    async def async_added_to_hass(self):
        """Register the entity and restore a known state before Google queries it."""
        await super().async_added_to_hass()

        restored = False
        if (last_state := await self.async_get_last_state()) is not None:
            last_position = last_state.attributes.get("current_position")
            if last_position is not None:
                try:
                    self._attr_current_cover_position = int(last_position)
                    restored = True
                except (TypeError, ValueError):
                    pass

            if last_state.state == CoverState.CLOSED:
                self._attr_is_opening = False
                self._attr_is_closing = False
                self._attr_is_closed = True
                if self._supports_position and self._attr_current_cover_position is None:
                    self._attr_current_cover_position = 0
                restored = True
            elif last_state.state == CoverState.OPEN:
                self._attr_is_opening = False
                self._attr_is_closing = False
                self._attr_is_closed = False
                if self._supports_position and self._attr_current_cover_position is None:
                    self._attr_current_cover_position = 100
                restored = True
            elif last_state.state == CoverState.OPENING:
                self._attr_is_opening = True
                self._attr_is_closing = False
                self._attr_is_closed = False
                restored = True
            elif last_state.state == CoverState.CLOSING:
                self._attr_is_opening = False
                self._attr_is_closing = True
                self._attr_is_closed = False
                restored = True

        # Avoid exposing the shutter as `unknown`, which makes Google Home mark it offline.
        if self._attr_is_closed is None:
            self._attr_is_opening = False
            self._attr_is_closing = False
            self._attr_is_closed = False
            restored = True

        if restored:
            self.async_write_ha_state()

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway_handler.send_status_request(OWNAutomationCommand.status(self._full_where))

    async def _async_apply_command_state(
        self,
        *,
        is_closed: bool,
        position: int | None = None,
    ) -> None:
        """Apply an optimistic state and queue a follow-up status refresh."""
        self._attr_is_opening = False
        self._attr_is_closing = False
        self._attr_is_closed = is_closed
        if self._supports_position and position is not None:
            self._attr_current_cover_position = position
        self.async_write_ha_state()
        await self._gateway_handler.send_status_request(
            OWNAutomationCommand.status(self._full_where)
        )

    async def async_open_cover(self, **kwargs):  # pylint: disable=unused-argument
        """Open the cover."""
        await self._gateway_handler.send(OWNAutomationCommand.raise_shutter(self._full_where))
        await self._async_apply_command_state(
            is_closed=False,
            position=100 if self._supports_position else None,
        )

    async def async_close_cover(self, **kwargs):  # pylint: disable=unused-argument
        """Close cover."""
        await self._gateway_handler.send(OWNAutomationCommand.lower_shutter(self._full_where))
        await self._async_apply_command_state(
            is_closed=True,
            position=0 if self._supports_position else None,
        )

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        if ATTR_POSITION in kwargs:
            position = kwargs[ATTR_POSITION]
            await self._gateway_handler.send(OWNAutomationCommand.set_shutter_level(self._full_where, position))
            await self._async_apply_command_state(
                is_closed=position == 0,
                position=position,
            )

    async def async_stop_cover(self, **kwargs):  # pylint: disable=unused-argument
        """Stop the cover."""
        await self._gateway_handler.send(OWNAutomationCommand.stop_shutter(self._full_where))
        self._attr_is_opening = False
        self._attr_is_closing = False
        if self._attr_is_closed is None:
            self._attr_is_closed = False
        self.async_write_ha_state()
        await self._gateway_handler.send_status_request(
            OWNAutomationCommand.status(self._full_where)
        )

    def handle_event(self, message: OWNAutomationEvent):
        """Handle an event message."""
        LOGGER.info(
            "%s %s",
            self._gateway_handler.log_id,
            message.human_readable_log,
        )
        self._attr_is_opening = message.is_opening
        self._attr_is_closing = message.is_closing
        if message.is_closed is not None:
            self._attr_is_closed = message.is_closed
        if message.current_position is not None:
            self._attr_current_cover_position = message.current_position

        self.async_schedule_update_ha_state()
