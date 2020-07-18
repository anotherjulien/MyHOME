"""Support for SCSGate lights."""
import logging

import voluptuous as vol

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_FLASH,
    ATTR_HS_COLOR,
    ATTR_TRANSITION,
    EFFECT_COLORLOOP,
    EFFECT_RANDOM,
    FLASH_LONG,
    FLASH_SHORT,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_COLOR_TEMP,
    SUPPORT_EFFECT,
    SUPPORT_FLASH,
    SUPPORT_TRANSITION,
    PLATFORM_SCHEMA,
    LightEntity,
    Light,
)
from homeassistant.const import (
    CONF_IP_ADDRESS, 
    CONF_PORT, 
    CONF_PASSWORD, 
    CONF_NAME, 
    CONF_MAC, 
    CONF_ID, 
    CONF_FRIENDLY_NAME,
    ATTR_ENTITY_ID,
    ATTR_STATE,
    CONF_DEVICES,
    CONF_LIGHTS,
)
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_GATEWAY,
    CONF_WHO,
    CONF_WHERE,
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
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_DEVICES): cv.schema_with_slug_keys(MYHOME_SCHEMA)}
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Legacy, config file not supported."""
    devices = config.get(CONF_DEVICES)
    #lights = []
    gateway = hass.data[DOMAIN][CONF_GATEWAY]

    if devices:
        for _, entity_info in devices.items():
            name = entity_info[CONF_NAME] if CONF_NAME in entity_info else None
            where = str(entity_info[CONF_WHERE])
            dimmable = entity_info[CONF_DIMMABLE] if CONF_DIMMABLE in entity_info else False
            gateway.add_light(where, {CONF_NAME: name, CONF_DIMMABLE: dimmable})


async def async_setup_entry(hass, config_entry, async_add_entities):
    lights = []
    gateway = hass.data[DOMAIN][CONF_GATEWAY]

    gateway_lights = gateway.get_lights()
    for light in gateway_lights.keys():
        light = MyHOMELight(
            hass=hass, where=light, name=gateway_lights[light][CONF_NAME], dimmable=gateway_lights[light][CONF_DIMMABLE], gateway=gateway
        )
        lights.append(light)
        
    async_add_entities(lights)

    await gateway.send_status_request(OWNLightingCommand.status("0"))

def eight_bits_to_percent(value: int) -> int:
    return int(round(100/255*value, 0))

def percent_to_eight_bits(value: int) -> int:
    return int(round(255/100*value, 0))

class MyHOMELight(LightEntity):

    def __init__(self, hass, name: str, where: str, dimmable: bool, gateway):

        self._name = name
        self._who = "1"
        self._where = where
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


    @property
    def device_info(self):
        return {
            "identifiers": {
                (DOMAIN, self.unique_id)
            },
            "name": self.name,
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
        """Handle a SCSGate message related with this light."""
        self._is_on = message.is_on
        if self._dimmable and message.brightness is not None:
            self._brightness = percent_to_eight_bits(message.brightness)
        self.async_schedule_update_ha_state()


