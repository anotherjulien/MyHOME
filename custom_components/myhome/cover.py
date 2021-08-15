"""Support for MyHome covers."""
import logging

import voluptuous as vol

from homeassistant.components.cover import (
    ATTR_POSITION,
    PLATFORM_SCHEMA,
    SUPPORT_CLOSE,
    SUPPORT_OPEN,
    SUPPORT_SET_POSITION,
    SUPPORT_STOP,
    DEVICE_CLASS_AWNING,
    DEVICE_CLASS_BLIND,
    DEVICE_CLASS_CURTAIN,
    DEVICE_CLASS_DAMPER,
    DEVICE_CLASS_DOOR,
    DEVICE_CLASS_GARAGE,
    DEVICE_CLASS_GATE,
    DEVICE_CLASS_SHADE,
    DEVICE_CLASS_SHUTTER,
    DEVICE_CLASS_WINDOW,
    CoverEntity,
)

from homeassistant.const import (
    CONF_NAME, 
    ATTR_ENTITY_ID,
    ATTR_STATE,
    CONF_DEVICES,
)

import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_GATEWAY,
    CONF_WHO,
    CONF_WHERE,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_ADVANCED_SHUTTER,
    CONF_INVERTED,
    DOMAIN,
    LOGGER,
)
from .gateway import MyHOMEGateway
from OWNd.message import (
    OWNAutomationEvent,
    OWNAutomationCommand,
)

MYHOME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WHERE): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_ADVANCED_SHUTTER): cv.boolean,
        vol.Optional(CONF_MANUFACTURER): cv.string,
        vol.Optional(CONF_DEVICE_MODEL): cv.string,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_DEVICES): cv.schema_with_slug_keys(MYHOME_SCHEMA)}
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    devices = config.get(CONF_DEVICES)
    try:
        gateway = hass.data[DOMAIN][CONF_GATEWAY]

        if devices:
            for _, entity_info in devices.items():
                name = entity_info[CONF_NAME] if CONF_NAME in entity_info else None
                where = entity_info[CONF_WHERE]
                advanced = entity_info[CONF_ADVANCED_SHUTTER] if CONF_ADVANCED_SHUTTER in entity_info else False
                manufacturer = entity_info[CONF_MANUFACTURER] if CONF_MANUFACTURER in entity_info else None
                model = entity_info[CONF_DEVICE_MODEL] if CONF_DEVICE_MODEL in entity_info else None
                gateway.add_cover(where, {CONF_NAME: name, CONF_ADVANCED_SHUTTER: advanced, CONF_MANUFACTURER: manufacturer, CONF_DEVICE_MODEL: model})
    except KeyError:
        _LOGGER.warning("Cover devices configured but no gateway present in configuration.")


async def async_setup_entry(hass, config_entry, async_add_entities):
    devices = []
    gateway = hass.data[DOMAIN][CONF_GATEWAY]

    gateway_devices = gateway.get_covers()
    for device in gateway_devices.keys():
        device = MyHOMECover(
            hass=hass,
            where=device,
            name=gateway_devices[device][CONF_NAME],
            advanced=gateway_devices[device][CONF_ADVANCED_SHUTTER],
            manufacturer=gateway_devices[device][CONF_MANUFACTURER],
            model=gateway_devices[device][CONF_DEVICE_MODEL],
            gateway=gateway
        )
        devices.append(device)
        
    async_add_entities(devices)

    # await gateway.send_status_request(OWNAutomationCommand.status("0"))

async def async_unload_entry(hass, config_entry):

    gateway = hass.data[DOMAIN][CONF_GATEWAY]
    gateway_devices = gateway.get_covers()

    for device in gateway_devices.keys():
        del hass.data[DOMAIN][f"2-{device}"]

class MyHOMECover(CoverEntity):

    device_class = DEVICE_CLASS_SHUTTER

    def __init__(self, hass, name: str, where: str, advanced: bool, manufacturer: str, model: str, gateway):

        self._hass = hass
        self._where = where
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._who = "2"
        self._model = model
        self._attr_supported_features = (SUPPORT_OPEN | SUPPORT_CLOSE | SUPPORT_STOP)
        if advanced:
            self._attr_supported_features |= SUPPORT_SET_POSITION
        self._gateway = gateway

        self._attr_name = name or f"A{self._where[:len(self._where)//2]}PL{self._where[len(self._where)//2:]}"
        self._attr_unique_id = f"{self._who}-{self._where}"

        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, self._attr_unique_id)
            },
            "name": self._attr_name,
            "manufacturer": self._manufacturer,
            "model": self._model,
            "via_device": (DOMAIN, self._gateway.id),
        }

        self._attr_entity_registry_enabled_default = True
        self._attr_should_poll = False
        self._attr_current_cover_position = None
        self._attr_is_opening = None
        self._attr_is_closing = None
        self._attr_is_closed = None

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self._hass.data[DOMAIN][self._attr_unique_id] = self
        await self.async_update()

    async def async_will_remove_from_hass(self):
        """When entity is removed from hass."""
        del self._hass.data[DOMAIN][self._attr_unique_id]
    
    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway.send_status_request(OWNAutomationCommand.status(self._where))

    async def async_open_cover(self, **kwargs):
        """Open the cover."""
        await self._gateway.send(OWNAutomationCommand.raise_shutter(self._where))

    async def async_close_cover(self, **kwargs):
        """Close cover."""
        await self._gateway.send(OWNAutomationCommand.lower_shutter(self._where))

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        if ATTR_POSITION in kwargs:
            position = kwargs[ATTR_POSITION]
            await self._gateway.send(OWNAutomationCommand.set_shutter_level(self._where, position))

    async def async_stop_cover(self, **kwargs):
        """Stop the cover."""
        await self._gateway.send(OWNAutomationCommand.stop_shutter(self._where))

    def handle_event(self, message: OWNAutomationEvent):
        """Handle an event message."""
        _LOGGER.info(message.human_readable_log)
        self._attr_is_opening = message.is_opening
        self._attr_is_closing = message.is_closing
        if message.is_closed is not None:
            self._attr_is_closed = message.is_closed
        if message.currentPosition is not None:
            self._attr_current_cover_position = message.currentPosition

        self.async_schedule_update_ha_state()


