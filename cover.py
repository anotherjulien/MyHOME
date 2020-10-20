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

    await gateway.send_status_request(OWNAutomationCommand.status("0"))

class MyHOMECover(CoverEntity):

    device_class = DEVICE_CLASS_SHUTTER

    def __init__(self, hass, name: str, where: str, advanced: bool, manufacturer: str, model: str, gateway):

        self._name = name
        self._where = where
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._who = "2"
        self._model = model
        self._id = f"{self._who}-{self._where}"
        if self._name is None:
            self._name = f"A{self._where[:len(self._where)//2]}PL{self._where[len(self._where)//2:]}"
        self._supported_features = 0
        self._advanced = advanced
        self._gateway = gateway
        self._current_cover_position = None
        self._is_opening = False
        self._is_closing = False
        self._is_closed = False

        hass.data[DOMAIN][self._id] = self

    
    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway.send_status_request(OWNAutomationCommand.status(self._where))

    @property
    def device_info(self):
        return {
            "identifiers": {
                (DOMAIN, self.unique_id)
            },
            "name": self.name,
            "manufacturer": self._manufacturer,
            "model": self._model,
            "via_device": (DOMAIN, self._gateway.id),
        }
    
    @property
    def should_poll(self):
        """No polling needed for a SCSGate light."""
        return False

    @property
    def name(self):
        """Return the name of the device if any."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique ID of the device."""
        return self._id

    @property
    def is_opening(self):
        """Return true if the cover is opening."""
        return self._is_opening

    @property
    def is_closing(self):
        """Return true if the cover is closing."""
        return self._is_closing

    @property
    def is_closed(self):
        """Return true if the cover is closed."""
        return self._is_closed

    @property
    def current_cover_position(self):
        """Return the current_cover_position of this cover between 0..100."""
        return self._current_cover_position

    @property
    def supported_features(self):
        """Flag supported features."""
        supported_features = (
            SUPPORT_OPEN | SUPPORT_CLOSE | SUPPORT_STOP
        )
        if self._advanced:
            supported_features |= SUPPORT_SET_POSITION
        return supported_features

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
        self._is_opening = message.is_opening
        self._is_closing = message.is_closing
        if message.is_closed is not None:
            self._is_closed = message.is_closed
        if message.currentPosition is not None:
            self._current_cover_position = message.currentPosition

        self.async_schedule_update_ha_state()


