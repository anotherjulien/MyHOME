import logging

import voluptuous as vol

from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA,
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
    CONF_DEVICE_CLASS,
    CONF_INVERTED,
    DOMAIN,
    LOGGER,
)
from .gateway import MyHOMEGateway

from OWNd.message import (
    OWNDryContactEvent,
    OWNDryContactCommand,
)

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

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    devices = config.get(CONF_DEVICES)
    gateway = hass.data[DOMAIN][CONF_GATEWAY]

    if devices:
        for _, entity_info in devices.items():
            name = entity_info[CONF_NAME] if CONF_NAME in entity_info else None
            where = entity_info[CONF_WHERE]
            who = entity_info[CONF_WHO] if CONF_WHO in entity_info else "25"
            inverted = entity_info[CONF_INVERTED] if CONF_INVERTED in entity_info else False
            device_class = entity_info[CONF_DEVICE_CLASS] if CONF_DEVICE_CLASS in entity_info else None
            manufacturer = entity_info[CONF_MANUFACTURER] if CONF_MANUFACTURER in entity_info else None
            model = entity_info[CONF_DEVICE_MODEL] if CONF_DEVICE_MODEL in entity_info else None
            gateway.add_binary_sensor(where, {CONF_WHO: who, CONF_NAME: name, CONF_INVERTED: inverted, CONF_DEVICE_CLASS: device_class, CONF_MANUFACTURER: manufacturer, CONF_DEVICE_MODEL: model})


async def async_setup_entry(hass, config_entry, async_add_entities):
    devices = []
    gateway = hass.data[DOMAIN][CONF_GATEWAY]

    gateway_devices = gateway.get_binary_sensors()
    for device in gateway_devices.keys():
        device = MyHOMEBinarySensor(
            hass=hass,
            who=gateway_devices[device][CONF_WHO],
            where=device,
            name=gateway_devices[device][CONF_NAME],
            inverted=gateway_devices[device][CONF_INVERTED],
            device_class=gateway_devices[device][CONF_DEVICE_CLASS],
            manufacturer=gateway_devices[device][CONF_MANUFACTURER],
            model=gateway_devices[device][CONF_DEVICE_MODEL],
            gateway=gateway
        )
        devices.append(device)
        
    async_add_entities(devices)

class MyHOMEBinarySensor(BinarySensorEntity):

    def __init__(self, hass, name: str, who: str, where: str, inverted: bool, device_class: str, manufacturer: str, model: str, gateway: MyHOMEGateway):

        self._name = name
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._model = model
        self._who = who
        self._where = where
        self._inverted = inverted
        self._id = f"{self._who}-{self._where}"
        if self._name is None:
            self._name = f"Sensor {self._where[1:]}"
        self._device_class = device_class
        self._gateway = gateway
        self._is_on = False

        hass.data[DOMAIN][self._id] = self

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        await self.async_update()

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway.send_status_request(OWNDryContactCommand.status(self._where))

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
    def device_class(self):
        """Return the device class if any."""
        return self._device_class

    @property
    def should_poll(self):
        """No polling needed for a MyHome device."""
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
        """Return true if sensor is on."""
        return self._is_on if not self._inverted else not self._is_on

    def handle_event(self, message: OWNDryContactEvent):
        """Handle an event message."""
        self._is_on = message.is_on
        self.async_schedule_update_ha_state()
