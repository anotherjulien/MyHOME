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
)
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_PARENT_ID,
    CONF_WHO,
    CONF_WHERE,
    DOMAIN,
    LOGGER,
)
from .gateway import MyHOMEGateway
from OWNd.message import (
    OWNLightingEvent,
    OWNLightingCommand,
)

_LOGGER = logging.getLogger(__name__)

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Legacy, config file not supported."""
    LOGGER.info("SETUP_PLATFORM CALLED")

async def async_setup_entry(hass, config_entry, async_add_entities):
    LOGGER.info("SETUP ENTRY")
    await async_add_entities(MyHOMELight(hass, config_entry))


class MyHOMELight(Light):

    def __init__(self, hass, config_entry):

        self._name = config_entry.title
        self._id = config_entry.data[CONF_ID]
        self._who = config_entry.data[CONF_WHO]
        self._where = config_entry.data[CONF_WHERE]
        self._parent_id = config_entry.data[CONF_PARENT_ID]
        self._gateway = hass.data[DOMAIN][self._parent_id]
        self._is_on = False

        hass.data[DOMAIN][self._id] = self


    @property
    def device_info(self):
        return {
            "identifiers": {
                (DOMAIN, self.unique_id)
            },
            "name": self.name,
            "via_device": (DOMAIN, self._parent_id),
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

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        await self._gateway.send(OWNLightingCommand.switch_on(self._where))

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        await self._gateway.send(OWNLightingCommand.switch_off(self._where))

    async def handle_event(self, message: OWNLightingEvent):
        """Handle a SCSGate message related with this light."""
        if self._is_on != message.is_on:
            self._is_on = message.is_on
            await self.async_schedule_update_ha_state()


