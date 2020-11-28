"""Support for MyHome lights."""
import logging

import voluptuous as vol

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_FLASH,
    FLASH_LONG,
    FLASH_SHORT,
    SUPPORT_BRIGHTNESS,
    SUPPORT_FLASH,
    PLATFORM_SCHEMA,
    LightEntity,
    Light,
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
    CONF_DIMMABLE,
    DOMAIN,
    LOGGER,
)
from .gateway import MyHOMEGateway
from OWNd.message import (
    OWNLightingEvent,
    OWNLightingCommand,
)

MYHOME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WHERE): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_DIMMABLE): cv.boolean,
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
                dimmable = entity_info[CONF_DIMMABLE] if CONF_DIMMABLE in entity_info else False
                manufacturer = entity_info[CONF_MANUFACTURER] if CONF_MANUFACTURER in entity_info else None
                model = entity_info[CONF_DEVICE_MODEL] if CONF_DEVICE_MODEL in entity_info else None
                gateway.add_light(where, {CONF_NAME: name, CONF_DIMMABLE: dimmable, CONF_MANUFACTURER: manufacturer, CONF_DEVICE_MODEL: model})
    except KeyError:
        _LOGGER.warning("Light devices configured but no gateway present in configuration.")


async def async_setup_entry(hass, config_entry, async_add_entities):
    devices = []
    gateway = hass.data[DOMAIN][CONF_GATEWAY]

    gateway_devices = gateway.get_lights()
    for device in gateway_devices.keys():
        device = MyHOMELight(
            hass=hass,
            where=device,
            name=gateway_devices[device][CONF_NAME],
            dimmable=gateway_devices[device][CONF_DIMMABLE],
            manufacturer=gateway_devices[device][CONF_MANUFACTURER],
            model=gateway_devices[device][CONF_DEVICE_MODEL],
            gateway=gateway
        )
        devices.append(device)
        
    async_add_entities(devices)

    await gateway.send_status_request(OWNLightingCommand.status("0"))

def eight_bits_to_percent(value: int) -> int:
    return int(round(100/255*value, 0))

def percent_to_eight_bits(value: int) -> int:
    return int(round(255/100*value, 0))

class MyHOMELight(LightEntity):

    def __init__(self, hass, name: str, where: str, dimmable: bool, manufacturer: str, model: str, gateway):

        self._name = name
        self._where = where
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._who = "1"
        self._model = model
        self._id = f"{self._who}-{self._where}"
        if self._name is None:
            self._name = f"A{self._where[:len(self._where)//2]}PL{self._where[len(self._where)//2:]}"
        self._supported_features = 0
        self._dimmable = dimmable
        if self._dimmable:
            self._supported_features |= SUPPORT_BRIGHTNESS
        self._gateway = gateway
        self._is_on = False
        self._brightness = 0

        hass.data[DOMAIN][self._id] = self

    
    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway.send_status_request(OWNLightingCommand.status(self._where))

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
    def is_on(self):
        """Return true if light is on."""
        return self._is_on

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        return self._brightness

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._supported_features

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""

        if ATTR_BRIGHTNESS in kwargs:
            percent_brightness = eight_bits_to_percent(kwargs[ATTR_BRIGHTNESS])
            if percent_brightness > 0:
                await self._gateway.send(OWNLightingCommand.set_brightness(self._where, percent_brightness))
            else:
                await self.async_turn_off
        else:    
            await self._gateway.send(OWNLightingCommand.switch_on(self._where))

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        await self._gateway.send(OWNLightingCommand.switch_off(self._where))

    def handle_event(self, message: OWNLightingEvent):
        """Handle an event message."""
        self._is_on = message.is_on
        if self._dimmable and message.brightness is not None:
            self._brightness = percent_to_eight_bits(message.brightness)
        self.async_schedule_update_ha_state()


