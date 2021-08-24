import voluptuous as vol

from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA,
    DOMAIN as PLATFORM,
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_BATTERY_CHARGING,
    DEVICE_CLASS_COLD,
    DEVICE_CLASS_CONNECTIVITY,
    DEVICE_CLASS_DOOR,
    DEVICE_CLASS_GARAGE_DOOR,
    DEVICE_CLASS_GAS,
    DEVICE_CLASS_HEAT,
    DEVICE_CLASS_LIGHT,
    DEVICE_CLASS_LOCK,
    DEVICE_CLASS_MOISTURE,
    DEVICE_CLASS_MOTION,
    DEVICE_CLASS_MOVING,
    DEVICE_CLASS_OCCUPANCY,
    DEVICE_CLASS_OPENING,
    DEVICE_CLASS_PLUG,
    DEVICE_CLASS_POWER,
    DEVICE_CLASS_PRESENCE,
    DEVICE_CLASS_PROBLEM,
    DEVICE_CLASS_SAFETY,
    DEVICE_CLASS_SMOKE,
    DEVICE_CLASS_SOUND,
    DEVICE_CLASS_VIBRATION,
    DEVICE_CLASS_WINDOW,
    BinarySensorEntity,
)
from homeassistant.const import (
    CONF_NAME, 
    CONF_DEVICES,
    CONF_ENTITIES,
)
import homeassistant.helpers.config_validation as cv

from OWNd.message import (
    OWNDryContactEvent,
    OWNDryContactCommand,
)

from .const import (
    CONF,
    CONF_GATEWAY,
    CONF_WHO,
    CONF_WHERE,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_CLASS,
    CONF_INVERTED,
    DOMAIN,
    LOGGER,
)
from .gateway import MyHOMEGatewayHandler

MYHOME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WHERE): cv.string,
        vol.Optional(CONF_WHO): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_INVERTED): cv.boolean,
        vol.Optional(CONF_DEVICE_CLASS): vol.In([
            DEVICE_CLASS_BATTERY,
            DEVICE_CLASS_BATTERY_CHARGING,
            DEVICE_CLASS_COLD,
            DEVICE_CLASS_CONNECTIVITY,
            DEVICE_CLASS_DOOR,
            DEVICE_CLASS_GARAGE_DOOR,
            DEVICE_CLASS_GAS,
            DEVICE_CLASS_HEAT,
            DEVICE_CLASS_LIGHT,
            DEVICE_CLASS_LOCK,
            DEVICE_CLASS_MOISTURE,
            DEVICE_CLASS_MOTION,
            DEVICE_CLASS_MOVING,
            DEVICE_CLASS_OCCUPANCY,
            DEVICE_CLASS_OPENING,
            DEVICE_CLASS_PLUG,
            DEVICE_CLASS_POWER,
            DEVICE_CLASS_PRESENCE,
            DEVICE_CLASS_PROBLEM,
            DEVICE_CLASS_SAFETY,
            DEVICE_CLASS_SMOKE,
            DEVICE_CLASS_SOUND,
            DEVICE_CLASS_VIBRATION,
            DEVICE_CLASS_WINDOW,
            ]),
        vol.Optional(CONF_MANUFACTURER): cv.string,
        vol.Optional(CONF_DEVICE_MODEL): cv.string,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_DEVICES): cv.schema_with_slug_keys(MYHOME_SCHEMA)}
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data[DOMAIN][CONF][PLATFORM] = {}
    _configured_binary_sensors = config.get(CONF_DEVICES)

    if _configured_binary_sensors:
        for _, entity_info in _configured_binary_sensors.items():
            name = entity_info[CONF_NAME] if CONF_NAME in entity_info else None
            where = entity_info[CONF_WHERE]
            who = entity_info[CONF_WHO] if CONF_WHO in entity_info else "25"
            inverted = entity_info[CONF_INVERTED] if CONF_INVERTED in entity_info else False
            device_class = entity_info[CONF_DEVICE_CLASS] if CONF_DEVICE_CLASS in entity_info else None
            manufacturer = entity_info[CONF_MANUFACTURER] if CONF_MANUFACTURER in entity_info else None
            model = entity_info[CONF_DEVICE_MODEL] if CONF_DEVICE_MODEL in entity_info else None
            hass.data[DOMAIN][CONF][PLATFORM][where] = {CONF_WHO: who, CONF_NAME: name, CONF_INVERTED: inverted, CONF_DEVICE_CLASS: device_class, CONF_MANUFACTURER: manufacturer, CONF_DEVICE_MODEL: model}

async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][CONF]: return True

    _binary_sensors = []
    _configured_binary_sensors = hass.data[DOMAIN][CONF][PLATFORM]

    for _binary_sensor in _configured_binary_sensors.keys():
        _binary_sensor = MyHOMEBinarySensor(
            hass=hass,
            who=_configured_binary_sensors[_binary_sensor][CONF_WHO],
            where=_binary_sensor,
            name=_configured_binary_sensors[_binary_sensor][CONF_NAME],
            inverted=_configured_binary_sensors[_binary_sensor][CONF_INVERTED],
            device_class=_configured_binary_sensors[_binary_sensor][CONF_DEVICE_CLASS],
            manufacturer=_configured_binary_sensors[_binary_sensor][CONF_MANUFACTURER],
            model=_configured_binary_sensors[_binary_sensor][CONF_DEVICE_MODEL],
            gateway=hass.data[DOMAIN][CONF_GATEWAY]
        )
        _binary_sensors.append(_binary_sensor)
        
    async_add_entities(_binary_sensors)

async def async_unload_entry(hass, config_entry):
    _configured_binary_sensors = hass.data[DOMAIN][CONF][PLATFORM]

    for _binary_sensor in _configured_binary_sensors.keys():
        del hass.data[DOMAIN][CONF_ENTITIES][f"25-{_binary_sensor}"]

class MyHOMEBinarySensor(BinarySensorEntity):

    def __init__(self, hass, name: str, who: str, where: str, inverted: bool, device_class: str, manufacturer: str, model: str, gateway: MyHOMEGatewayHandler):

        self._hass = hass
        self._where = where
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._who = who
        self._model = model
        self._gateway_handler = gateway
        self._inverted = inverted

        self._attr_name = name or f"Sensor {self._where[1:]}"
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

        self._attr_device_class = device_class
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
        await self._gateway_handler.send_status_request(OWNDryContactCommand.status(self._where))

    def handle_event(self, message: OWNDryContactEvent):
        """Handle an event message."""
        LOGGER.info(message.human_readable_log)
        self._attr_is_on = message.is_on != self._inverted
        self.async_schedule_update_ha_state()
