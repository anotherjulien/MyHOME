"""Support for MyHome lights."""
import logging

import voluptuous as vol

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_FLASH,
    FLASH_LONG,
    FLASH_SHORT,
    ATTR_TRANSITION,
    SUPPORT_BRIGHTNESS,
    SUPPORT_FLASH,
    SUPPORT_TRANSITION,
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

    # await gateway.send_status_request(OWNLightingCommand.status("0"))

async def async_unload_entry(hass, config_entry):

    gateway = hass.data[DOMAIN][CONF_GATEWAY]
    gateway_devices = gateway.get_lights()

    for device in gateway_devices.keys():
        del hass.data[DOMAIN][f"1-{device}"]

def eight_bits_to_percent(value: int) -> int:
    return int(round(100/255*value, 0))

def percent_to_eight_bits(value: int) -> int:
    return int(round(255/100*value, 0))

class MyHOMELight(LightEntity):

    def __init__(self, hass, name: str, where: str, dimmable: bool, manufacturer: str, model: str, gateway):

        self._hass = hass
        self._where = where
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._who = "1"
        self._model = model
        self._attr_supported_features = 0
        if dimmable:
            self._attr_supported_features |= SUPPORT_BRIGHTNESS
            self._attr_supported_features |= SUPPORT_TRANSITION
        else:
            self._attr_supported_features |= SUPPORT_FLASH
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
        self._attr_is_on = False
        self._attr_brightness = 0
        self._attr_brightness_pct = 0
    
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
        if self._attr_supported_features & SUPPORT_BRIGHTNESS:
            await self._gateway.send_status_request(OWNLightingCommand.get_brightness(self._where))
        else:
            await self._gateway.send_status_request(OWNLightingCommand.status(self._where))

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""

        if ATTR_FLASH in kwargs and self._attr_supported_features & SUPPORT_FLASH:
            if kwargs[ATTR_FLASH] == FLASH_SHORT:
                return await self._gateway.send(OWNLightingCommand.flash(self._where, 0.5))
            elif kwargs[ATTR_FLASH] == FLASH_LONG:
                return await self._gateway.send(OWNLightingCommand.flash(self._where, 1.5))

        
        if ((ATTR_BRIGHTNESS in kwargs or ATTR_BRIGHTNESS_PCT in kwargs) and self._attr_supported_features & SUPPORT_BRIGHTNESS) or (ATTR_TRANSITION in kwargs and self._attr_supported_features & SUPPORT_TRANSITION):
            if ATTR_BRIGHTNESS in kwargs or ATTR_BRIGHTNESS_PCT in kwargs:
                _percent_brightness = eight_bits_to_percent(kwargs[ATTR_BRIGHTNESS]) if ATTR_BRIGHTNESS in kwargs else None
                _percent_brightness = kwargs[ATTR_BRIGHTNESS_PCT] if ATTR_BRIGHTNESS_PCT in kwargs else _percent_brightness

                if _percent_brightness == 0:
                    return await self.async_turn_off(kwargs)
                else:
                    return await self._gateway.send(OWNLightingCommand.set_brightness(self._where, _percent_brightness, int(kwargs[ATTR_TRANSITION]))) if ATTR_TRANSITION in kwargs else await self._gateway.send(OWNLightingCommand.set_brightness(self._where, _percent_brightness))
            else:
                return await self._gateway.send(OWNLightingCommand.switch_on(self._where, int(kwargs[ATTR_TRANSITION])))
        else:    
            await self._gateway.send(OWNLightingCommand.switch_on(self._where))
            if self._attr_supported_features & SUPPORT_BRIGHTNESS:
                await self.async_update()

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""

        if ATTR_TRANSITION in kwargs and self._attr_supported_features & SUPPORT_TRANSITION:
            return await self._gateway.send(OWNLightingCommand.switch_off(self._where, int(kwargs[ATTR_TRANSITION])))

        if ATTR_FLASH in kwargs and self._attr_supported_features & SUPPORT_FLASH:
            if kwargs[ATTR_FLASH] == FLASH_SHORT:
                return await self._gateway.send(OWNLightingCommand.flash(self._where, 0.5))
            elif kwargs[ATTR_FLASH] == FLASH_LONG:
                return await self._gateway.send(OWNLightingCommand.flash(self._where, 1.5))

        return await self._gateway.send(OWNLightingCommand.switch_off(self._where))
        
        

    def handle_event(self, message: OWNLightingEvent):
        """Handle an event message."""
        _LOGGER.info(message.human_readable_log)
        self._attr_is_on = message.is_on
        if self._attr_supported_features & SUPPORT_BRIGHTNESS and message.brightness is not None:
            self._attr_brightness_pct = message.brightness
            self._attr_brightness = percent_to_eight_bits(message.brightness)
        self.async_schedule_update_ha_state()


