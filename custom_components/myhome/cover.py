"""Support for MyHome covers."""
import voluptuous as vol

from homeassistant.components.cover import (
    ATTR_POSITION,
    PLATFORM_SCHEMA,
    DOMAIN as PLATFORM,
    SUPPORT_CLOSE,
    SUPPORT_OPEN,
    SUPPORT_SET_POSITION,
    SUPPORT_STOP,
    CoverDeviceClass,
    CoverEntity,
)

from homeassistant.const import (
    CONF_NAME,
    CONF_DEVICES,
    CONF_ENTITIES,
)

import homeassistant.helpers.config_validation as cv

from OWNd.message import (
    OWNAutomationEvent,
    OWNAutomationCommand,
)

from .const import (
    CONF,
    CONF_GATEWAY,
    CONF_WHO,
    CONF_WHERE,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_ADVANCED_SHUTTER,
    CONF_DEVICE_CLASS,
    DOMAIN,
    LOGGER,
)
from .myhome_device import MyHOMEEntity
from .gateway import MyHOMEGatewayHandler

MYHOME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WHERE): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_ADVANCED_SHUTTER): cv.boolean,
        vol.Optional(CONF_DEVICE_CLASS): vol.In(
            [
                CoverDeviceClass.SHUTTER, 
                CoverDeviceClass.WINDOW
            ]
        ),
        vol.Optional(CONF_MANUFACTURER): cv.string,
        vol.Optional(CONF_DEVICE_MODEL): cv.string,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_DEVICES): cv.schema_with_slug_keys(MYHOME_SCHEMA)}
)


async def async_setup_platform(
    hass, config, async_add_entities, discovery_info=None
):  # pylint: disable=unused-argument
    if CONF not in hass.data[DOMAIN]:
        return False
    hass.data[DOMAIN][CONF][PLATFORM] = {}
    _configured_covers = config.get(CONF_DEVICES)

    if _configured_covers:
        for _, entity_info in _configured_covers.items():
            who = "2"
            where = entity_info[CONF_WHERE]
            device_id = f"{who}-{where}"
            name = (
                entity_info[CONF_NAME]
                if CONF_NAME in entity_info
                else f"A{where[:len(where)//2]}PL{where[len(where)//2:]}"
            )
            advanced = (
                entity_info[CONF_ADVANCED_SHUTTER]
                if CONF_ADVANCED_SHUTTER in entity_info
                else False
            )
            device_class = (
                entity_info[CONF_DEVICE_CLASS]
                if CONF_DEVICE_CLASS in entity_info
                else CoverDeviceClass.SHUTTER
            )
            entities = []
            manufacturer = (
                entity_info[CONF_MANUFACTURER]
                if CONF_MANUFACTURER in entity_info
                else None
            )
            model = (
                entity_info[CONF_DEVICE_MODEL]
                if CONF_DEVICE_MODEL in entity_info
                else None
            )
            hass.data[DOMAIN][CONF][PLATFORM][device_id] = {
                CONF_WHO: who,
                CONF_WHERE: where,
                CONF_ENTITIES: entities,
                CONF_NAME: name,
                CONF_ADVANCED_SHUTTER: advanced,
                CONF_DEVICE_CLASS: device_class,
                CONF_MANUFACTURER: manufacturer,
                CONF_DEVICE_MODEL: model,
            }


async def async_setup_entry(
    hass, config_entry, async_add_entities
):  # pylint: disable=unused-argument
    if PLATFORM not in hass.data[DOMAIN][CONF]:
        return True

    _covers = []
    _configured_covers = hass.data[DOMAIN][CONF][PLATFORM]

    for _cover in _configured_covers.keys():
        _cover = MyHOMECover(
            hass=hass,
            device_id=_cover,
            who=_configured_covers[_cover][CONF_WHO],
            where=_configured_covers[_cover][CONF_WHERE],
            name=_configured_covers[_cover][CONF_NAME],
            advanced=_configured_covers[_cover][CONF_ADVANCED_SHUTTER],
            device_class=_configured_covers[_cover][CONF_DEVICE_CLASS],
            manufacturer=_configured_covers[_cover][CONF_MANUFACTURER],
            model=_configured_covers[_cover][CONF_DEVICE_MODEL],
            gateway=hass.data[DOMAIN][CONF_GATEWAY],
        )
        _covers.append(_cover)

    async_add_entities(_covers)


async def async_unload_entry(hass, config_entry):  # pylint: disable=unused-argument
    if PLATFORM not in hass.data[DOMAIN][CONF]:
        return True

    _configured_covers = hass.data[DOMAIN][CONF][PLATFORM]

    for _cover in _configured_covers.keys():
        del hass.data[DOMAIN][CONF_ENTITIES][_cover]


class MyHOMECover(MyHOMEEntity, CoverEntity):
    def __init__(
        self,
        hass,
        name: str,
        device_id: str,
        who: str,
        where: str,
        advanced: bool,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        super().__init__(
            hass=hass,
            name=name,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._attr_supported_features = SUPPORT_OPEN | SUPPORT_CLOSE | SUPPORT_STOP
        if advanced:
            self._attr_supported_features |= SUPPORT_SET_POSITION
        self._gateway_handler = gateway

        self._attr_extra_state_attributes = {
            "A": where[: len(where) // 2],
            "PL": where[len(where) // 2 :],
        }

        self._attr_device_class = device_class
        self._attr_current_cover_position = None
        self._attr_is_opening = None
        self._attr_is_closing = None
        self._attr_is_closed = None

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway_handler.send_status_request(
            OWNAutomationCommand.status(self._where)
        )

    async def async_open_cover(self, **kwargs):  # pylint: disable=unused-argument
        """Open the cover."""
        await self._gateway_handler.send(
            OWNAutomationCommand.raise_shutter(self._where)
        )

    async def async_close_cover(self, **kwargs):  # pylint: disable=unused-argument
        """Close cover."""
        await self._gateway_handler.send(
            OWNAutomationCommand.lower_shutter(self._where)
        )

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        if ATTR_POSITION in kwargs:
            position = kwargs[ATTR_POSITION]
            await self._gateway_handler.send(
                OWNAutomationCommand.set_shutter_level(self._where, position)
            )

    async def async_stop_cover(self, **kwargs):  # pylint: disable=unused-argument
        """Stop the cover."""
        await self._gateway_handler.send(OWNAutomationCommand.stop_shutter(self._where))

    def handle_event(self, message: OWNAutomationEvent):
        """Handle an event message."""
        LOGGER.info(message.human_readable_log)
        self._attr_is_opening = message.is_opening
        self._attr_is_closing = message.is_closing
        if message.is_closed is not None:
            self._attr_is_closed = message.is_closed
        if message.current_position is not None:
            self._attr_current_cover_position = message.current_position

        self.async_schedule_update_ha_state()
