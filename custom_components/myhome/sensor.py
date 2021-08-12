import logging

import voluptuous as vol

from datetime import timedelta

from homeassistant.helpers.entity import Entity

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    STATE_CLASS_MEASUREMENT,
    SensorEntity,
)
from homeassistant.const import (
    CONF_NAME, 
    ATTR_ENTITY_ID,
    ATTR_STATE,
    CONF_DEVICES,
    DEVICE_CLASS_TEMPERATURE,
    DEVICE_CLASS_POWER,
    DEVICE_CLASS_ENERGY,
    POWER_WATT,
    ENERGY_WATT_HOUR,
    TEMP_CELSIUS,
)
from homeassistant.helpers import config_validation as cv, entity_platform, service

from homeassistant.util import dt as dt_util

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
    MESSAGE_TYPE_ENERGY_TOTALIZER,
    MESSAGE_TYPE_HOURLY_CONSUMPTION,
    MESSAGE_TYPE_DAILY_CONSUMPTION,
    MESSAGE_TYPE_MONTHLY_CONSUMPTION,
    MESSAGE_TYPE_CURRENT_DAY_CONSUMPTION,
    MESSAGE_TYPE_CURRENT_MONTH_CONSUMPTION,
    MESSAGE_TYPE_MAIN_TEMPERATURE,
    MESSAGE_TYPE_SECONDARY_TEMPERATURE,
    OWNEnergyEvent,
    OWNEnergyCommand,
    OWNHeatingEvent,
    OWNHeatingCommand,
)

SCAN_INTERVAL = timedelta(seconds=60)

MYHOME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WHERE): cv.string,
        vol.Optional(CONF_WHO): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_INVERTED): cv.boolean,
        vol.Required(CONF_DEVICE_CLASS): vol.In([
            DEVICE_CLASS_TEMPERATURE,
            DEVICE_CLASS_POWER,
            DEVICE_CLASS_ENERGY,
            ]),
        vol.Optional(CONF_MANUFACTURER): cv.string,
        vol.Optional(CONF_DEVICE_MODEL): cv.string,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_DEVICES): cv.schema_with_slug_keys(MYHOME_SCHEMA)}
)

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_INSTANT_POWER = "start_sending_instant_power"

ATTR_DURATION = "duration"
ATTR_DATE = "date"
ATTR_MONTH = "month"
ATTR_DAY = "day"

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    devices = config.get(CONF_DEVICES)
    try:
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
    except KeyError:
        _LOGGER.warning("Sensor devices configured but no gateway present in configuration.")


async def async_setup_entry(hass, config_entry, async_add_entities):
    devices = []
    gateway = hass.data[DOMAIN][CONF_GATEWAY]

    power_devices_configured = False

    gateway_devices = gateway.get_sensors()

    for device in gateway_devices.keys():
        if gateway_devices[device][CONF_DEVICE_CLASS] == DEVICE_CLASS_POWER:
            power_devices_configured = True
            
            devices.append(MyHOMEPowerSensor(
                hass=hass,
                who=gateway_devices[device][CONF_WHO],
                where=device,
                name=gateway_devices[device][CONF_NAME],
                device_class=gateway_devices[device][CONF_DEVICE_CLASS],
                manufacturer=gateway_devices[device][CONF_MANUFACTURER],
                model=gateway_devices[device][CONF_DEVICE_MODEL],
                gateway=gateway
            ))

            devices.append(MyHOMEEnergySensor(
                hass=hass,
                who=gateway_devices[device][CONF_WHO],
                where=device,
                name=gateway_devices[device][CONF_NAME],
                period="daily",
                manufacturer=gateway_devices[device][CONF_MANUFACTURER],
                model=gateway_devices[device][CONF_DEVICE_MODEL],
                gateway=gateway
            ))

            devices.append(MyHOMEEnergySensor(
                hass=hass,
                who=gateway_devices[device][CONF_WHO],
                where=device,
                name=gateway_devices[device][CONF_NAME],
                period="monthly",
                manufacturer=gateway_devices[device][CONF_MANUFACTURER],
                model=gateway_devices[device][CONF_DEVICE_MODEL],
                gateway=gateway
            ))

            devices.append(MyHOMEEnergySensor(
                hass=hass,
                who=gateway_devices[device][CONF_WHO],
                where=device,
                name=gateway_devices[device][CONF_NAME],
                period=None,
                manufacturer=gateway_devices[device][CONF_MANUFACTURER],
                model=gateway_devices[device][CONF_DEVICE_MODEL],
                gateway=gateway
            ))

        elif gateway_devices[device][CONF_DEVICE_CLASS] == DEVICE_CLASS_TEMPERATURE:
            device = MyHOMETemperatureSensor(
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
    
    if power_devices_configured:
        platform = entity_platform.current_platform.get()

        platform.async_register_entity_service(
            SERVICE_SEND_INSTANT_POWER,
            {
                vol.Optional(ATTR_DURATION): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=255)
                )
            },
            "start_sending_instant_power",
        )

    async_add_entities(devices)

class MyHOMEPowerSensor(SensorEntity):

    def __init__(self, hass, name: str, who: str, where: str, device_class: str, manufacturer: str, model: str, gateway: MyHOMEGateway):

        self._hass = hass
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._model = model
        self._who = who or 18
        self._where = where
        self._device_name = name or f"Sensor {self._where[1:]}"
        self._device_id = f"{self._who}-{self._where}"
        self._gateway = gateway
        self._type_id = "power"
        self._type_name = "Power"

        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, self._device_id)
            },
            "name": self._device_name,
            "manufacturer": self._manufacturer,
            "model": self._model,
            "via_device": (DOMAIN, self._gateway.id),
        }

        self._attr_name = f"{self._device_name} {self._type_name}"
        self._attr_unique_id = f"{self._device_id}-{self._type_id}"
        self._attr_entity_registry_enabled_default = True
        self._attr_device_class = DEVICE_CLASS_POWER
        self._attr_unit_of_measurement = POWER_WATT
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_should_poll = False
        self._attr_state = 0

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
        #await self.start_sending_instant_power(255)

    def handle_event(self, message: OWNEnergyEvent):
        """Handle an event message."""
        if message.message_type == MESSAGE_TYPE_ACTIVE_POWER:
            self._attr_state = message.active_power
            self.async_schedule_update_ha_state()
    
    async def start_sending_instant_power(self, duration):
        """Request automatic instant power."""
        await self._gateway.send(OWNEnergyCommand.start_sending_instant_power(self._where, duration))

class MyHOMEEnergySensor(SensorEntity):

    def __init__(self, hass, name: str, who: str, where: str, period: str, manufacturer: str, model: str, gateway: MyHOMEGateway):

        self._hass = hass
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._model = model
        self._who = who or 18
        self._where = where
        self._device_name = name or f"Sensor {self._where[1:]}"
        self._device_id = f"{self._who}-{self._where}"
        self._gateway = gateway

        if period == "daily":
            self._type_id = "daily-energy"
            self._type_name = "Energy (today)"
            self._attr_entity_registry_enabled_default = False
            self._attr_last_reset = dt_util.start_of_local_day()
        elif period == "monthly":
            self._type_id = "monthly-energy"
            self._type_name = "Energy (current month)"
            self._attr_entity_registry_enabled_default = False
            self._attr_last_reset = dt_util.start_of_local_day().replace(day=1)
        else:
            self._type_id = "total-energy"
            self._type_name = "Energy"
            self._attr_entity_registry_enabled_default = True
            self._attr_last_reset = dt_util.utc_from_timestamp(0)

        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, self._device_id)
            },
            "name": self._device_name,
            "manufacturer": self._manufacturer,
            "model": self._model,
            "via_device": (DOMAIN, self._gateway.id),
        }

        self._attr_name = f"{self._device_name} {self._type_name}"
        self._attr_unique_id = f"{self._device_id}-{self._type_id}"
        self._attr_device_class = DEVICE_CLASS_ENERGY
        self._attr_unit_of_measurement = ENERGY_WATT_HOUR
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_should_poll = True
        self._attr_state = None

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
        if self._type_id == "total-energy":
            await self._gateway.send_status_request(OWNEnergyCommand.get_total_consumption(self._where))
        elif self._type_id == "monthly-energy":
            await self._gateway.send_status_request(OWNEnergyCommand.get_partial_monthly_consumption(self._where))
        elif self._type_id == "daily-energy":
            await self._gateway.send_status_request(OWNEnergyCommand.get_partial_daily_consumption(self._where))

    def handle_event(self, message: OWNEnergyEvent):
        """Handle an event message."""
        if self._type_id == "total-energy" and message.message_type == MESSAGE_TYPE_ENERGY_TOTALIZER:
            self._attr_state = message.total_consumption
        elif self._type_id == "monthly-energy" and message.message_type == MESSAGE_TYPE_CURRENT_MONTH_CONSUMPTION:
            self._attr_state = message.current_month_partial_consumption
            self._attr_last_reset = dt_util.start_of_local_day().replace(day=1)
        elif self._type_id == "daily-energy" and message.message_type == MESSAGE_TYPE_CURRENT_DAY_CONSUMPTION:
            self._attr_state = message.current_day_partial_consumption
            self._attr_last_reset = dt_util.start_of_local_day()
        self.async_schedule_update_ha_state()

class MyHOMETemperatureSensor(Entity):

    def __init__(self, hass, name: str, who: str, where: str, device_class: str, manufacturer: str, model: str, gateway: MyHOMEGateway):

        self._hass = hass
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._model = model
        self._who = who or 4
        self._where = where
        self._attr_name = name or f"Sensor {self._where[1:]}"
        self._attr_unique_id = f"{self._who}-{self._where}"
        self._gateway = gateway

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
        self._attr_device_class = DEVICE_CLASS_TEMPERATURE
        self._attr_unit_of_measurement = TEMP_CELSIUS
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_should_poll = True
        self._attr_state = None

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
        await self._gateway.send_status_request(OWNHeatingCommand.get_temperature(self._where))

    def handle_event(self, message: OWNHeatingEvent):
        """Handle an event message."""
        if message.message_type == MESSAGE_TYPE_MAIN_TEMPERATURE:
            self._attr_state = message.main_temperature
            self.async_schedule_update_ha_state()
        elif message.message_type == MESSAGE_TYPE_SECONDARY_TEMPERATURE:
            self._attr_state = message.secondary_temperature[1]
            self.async_schedule_update_ha_state()
