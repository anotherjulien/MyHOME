import logging

import voluptuous as vol

from homeassistant.helpers.entity import Entity

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
)
from homeassistant.const import (
    CONF_NAME, 
    ATTR_ENTITY_ID,
    ATTR_STATE,
    CONF_DEVICES,
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_ILLUMINANCE,
    DEVICE_CLASS_SIGNAL_STRENGTH,
    DEVICE_CLASS_TEMPERATURE,
    DEVICE_CLASS_TIMESTAMP,
    DEVICE_CLASS_PRESSURE,
    DEVICE_CLASS_POWER,
    POWER_WATT,
    TEMP_CELSIUS,
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
    MESSAGE_TYPE_ACTIVE_POWER,
    MESSAGE_TYPE_HOURLY_CONSUMPTION,
    MESSAGE_TYPE_DAILY_CONSUMPTION,
    MESSAGE_TYPE_MONTHLY_CONSUMPTION,
    MESSAGE_TYPE_CURRENT_DAY_CONSUMPTION,
    MESSAGE_TYPE_CURRENT_MONTH_CONSUMPTION,
    OWNEnergyEvent,
)

MYHOME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WHERE): cv.string,
        vol.Optional(CONF_WHO): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_INVERTED): cv.boolean,
        vol.Required(CONF_DEVICE_CLASS): vol.In([
            DEVICE_CLASS_BATTERY, 
            DEVICE_CLASS_HUMIDITY, 
            DEVICE_CLASS_ILLUMINANCE,
            DEVICE_CLASS_SIGNAL_STRENGTH,
            DEVICE_CLASS_TEMPERATURE,
            DEVICE_CLASS_TIMESTAMP,
            DEVICE_CLASS_PRESSURE,
            DEVICE_CLASS_POWER,
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
    """Legacy, config file not supported."""
    devices = config.get(CONF_DEVICES)
    gateway = hass.data[DOMAIN][CONF_GATEWAY]

    if devices:
        for _, entity_info in devices.items():
            name = entity_info[CONF_NAME] if CONF_NAME in entity_info else None
            where = entity_info[CONF_WHERE]
            who = entity_info[CONF_WHO] if CONF_WHO in entity_info else None
            device_class = entity_info[CONF_DEVICE_CLASS] if CONF_DEVICE_CLASS in entity_info else None
            manufacturer = entity_info[CONF_MANUFACTURER] if CONF_MANUFACTURER in entity_info else None
            model = entity_info[CONF_DEVICE_MODEL] if CONF_DEVICE_MODEL in entity_info else None
            gateway.add_sensor(where, {CONF_WHO: who, CONF_NAME: name, CONF_DEVICE_CLASS: device_class, CONF_MANUFACTURER: manufacturer, CONF_DEVICE_MODEL: model})


async def async_setup_entry(hass, config_entry, async_add_entities):
    devices = []
    gateway = hass.data[DOMAIN][CONF_GATEWAY]

    gateway_devices = gateway.get_sensors()
    for device in gateway_devices.keys():
        if gateway_devices[device][CONF_DEVICE_CLASS] == DEVICE_CLASS_POWER:
            device = MyHOMEPowerSensor(
                hass=hass,
                who=gateway_devices[device][CONF_WHO],
                where=device,
                name=gateway_devices[device][CONF_NAME],
                device_class=gateway_devices[device][CONF_DEVICE_CLASS],
                manufacturer=gateway_devices[device][CONF_MANUFACTURER],
                model=gateway_devices[device][CONF_DEVICE_MODEL],
                gateway=gateway
            )
            devices.append(device)
        
    async_add_entities(devices)

class MyHOMEPowerSensor(Entity):

    def __init__(self, hass, name: str, who: str, where: str, device_class: str, manufacturer: str, model: str, gateway: MyHOMEGateway):

        self._name = name
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._model = model
        self._who = who or 18
        self._where = where
        self._id = f"{self._who}-{self._where}"
        if self._name is None:
            self._name = f"Sensor {self._where[1:]}"
        self._device_class = device_class
        self._gateway = gateway
        self._value = 0
        self._unit = POWER_WATT

        hass.data[DOMAIN][self._id] = self

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        await self.async_update()

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        #await self._gateway.send_status_request(OWNDryContactCommand.status(self._where))

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
    def state(self):
        """Return the state of the sensor."""
        return self._value

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._unit

    def handle_event(self, message: OWNEnergyEvent):
        """Handle a SCSGate message related with this light."""
        if message.message_type == MESSAGE_TYPE_ACTIVE_POWER:
            self._value = message.active_power
            self.async_schedule_update_ha_state()
