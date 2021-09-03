"""Support for MyHome lights."""
import voluptuous as vol

from homeassistant.components.switch import (
    PLATFORM_SCHEMA,
    DOMAIN as PLATFORM,
    DEVICE_CLASS_OUTLET,
    DEVICE_CLASS_SWITCH,
    SwitchEntity,
)
from homeassistant.const import (
    CONF_NAME, 
    ATTR_ENTITY_ID,
    ATTR_STATE,
    CONF_DEVICES,
    CONF_ENTITIES,
)
import homeassistant.helpers.config_validation as cv

from OWNd.message import (
    OWNLightingEvent,
    OWNLightingCommand,
)

from .const import (
    CONF,
    CONF_GATEWAY,
    CONF_WHO,
    CONF_WHERE,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_CLASS,
    DOMAIN,
    LOGGER,
)
from .gateway import MyHOMEGatewayHandler

MYHOME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WHERE): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_DEVICE_CLASS): vol.In([DEVICE_CLASS_OUTLET, DEVICE_CLASS_SWITCH]),
        vol.Optional(CONF_MANUFACTURER): cv.string,
        vol.Optional(CONF_DEVICE_MODEL): cv.string,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_DEVICES): cv.schema_with_slug_keys(MYHOME_SCHEMA)}
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data[DOMAIN][CONF][PLATFORM] = {}
    _configured_switches = config.get(CONF_DEVICES)
    
    if _configured_switches:
        for _, entity_info in _configured_switches.items():
            name = entity_info[CONF_NAME] if CONF_NAME in entity_info else None
            where = entity_info[CONF_WHERE]
            device_class = entity_info[CONF_DEVICE_CLASS] if CONF_DEVICE_CLASS in entity_info else "switch"
            manufacturer = entity_info[CONF_MANUFACTURER] if CONF_MANUFACTURER in entity_info else None
            model = entity_info[CONF_DEVICE_MODEL] if CONF_DEVICE_MODEL in entity_info else None
            hass.data[DOMAIN][CONF][PLATFORM][where] = {CONF_NAME: name, CONF_DEVICE_CLASS: device_class, CONF_MANUFACTURER: manufacturer, CONF_DEVICE_MODEL: model}

async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][CONF]: return True

    _switches = []
    _configured_switches = hass.data[DOMAIN][CONF][PLATFORM]

    for _switch in _configured_switches.keys():
        _switch = MyHOMESwitch(
            hass=hass,
            where=_switch,
            name=_configured_switches[_switch][CONF_NAME],
            device_class=_configured_switches[_switch][CONF_DEVICE_CLASS],
            manufacturer=_configured_switches[_switch][CONF_MANUFACTURER],
            model=_configured_switches[_switch][CONF_DEVICE_MODEL],
            gateway=hass.data[DOMAIN][CONF_GATEWAY]
        )
        _switches.append(_switch)
        
    async_add_entities(_switches)

async def async_unload_entry(hass, config_entry):
    _configured_switches = hass.data[DOMAIN][CONF][PLATFORM]

    for _switch in _configured_switches.keys():
        del hass.data[DOMAIN][CONF_ENTITIES][f"1-{_switch}"]

class MyHOMESwitch(SwitchEntity):

    def __init__(self, hass, name: str, where: str, device_class: str, manufacturer: str, model: str, gateway: MyHOMEGatewayHandler):

        self._hass = hass
        self._where = where
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._who = "1"
        self._model = model
        self._gateway_handler = gateway

        self._attr_name = name or f"A{self._where[:len(self._where)//2]}PL{self._where[len(self._where)//2:]}"
        self._attr_unique_id = f"{self._who}-{self._where}"

        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, self._attr_unique_id)
            },
            "name": self._attr_name,
            "manufacturer": self._manufacturer,
            "model": self._model,
            "via_device": (DOMAIN, self._gateway_handler.id),
        }

        self._attr_device_class = DEVICE_CLASS_OUTLET if device_class.lower() == "outlet" else DEVICE_CLASS_SWITCH
        self._attr_entity_registry_enabled_default = True
        self._attr_should_poll = False
        self._attr_is_on = False

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self._hass.data[DOMAIN][CONF_ENTITIES][self._attr_unique_id] = self
        await self.async_update()

    async def async_will_remove_from_hass(self):
        """When entity is removed from hass."""
        del self._hass.data[DOMAIN][CONF_ENTITIES][self._attr_unique_id]

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway_handler.send_status_request(OWNLightingCommand.status(self._where))

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        await self._gateway_handler.send(OWNLightingCommand.switch_on(self._where))

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        await self._gateway_handler.send(OWNLightingCommand.switch_off(self._where))

    def handle_event(self, message: OWNLightingEvent):
        """Handle an event message."""
        LOGGER.info(message.human_readable_log)
        self._attr_is_on = message.is_on
        self.async_schedule_update_ha_state()
