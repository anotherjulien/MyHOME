"""Support for MyHome sensors (power/energy, temperature, illuminance)."""

from datetime import timedelta

from voluptuous import (
    Optional,
    Coerce,
    All,
    Range,
)

from homeassistant.components.sensor import DOMAIN as PLATFORM
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_ENTITIES,
    CONF_NAME,
    CONF_MAC,
    LIGHT_LUX,
    UnitOfPower,
    UnitOfEnergy,
    UnitOfTemperature,
)
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er
from OWNd.message import (
    MESSAGE_TYPE_ACTIVE_POWER,
    MESSAGE_TYPE_CURRENT_DAY_CONSUMPTION,
    MESSAGE_TYPE_CURRENT_MONTH_CONSUMPTION,
    MESSAGE_TYPE_ENERGY_TOTALIZER,
    MESSAGE_TYPE_ILLUMINANCE,
    MESSAGE_TYPE_MAIN_TEMPERATURE,
    MESSAGE_TYPE_SECONDARY_TEMPERATURE,
    OWNEnergyCommand,
    OWNEnergyEvent,
    OWNHeatingCommand,
    OWNHeatingEvent,
    OWNLightingCommand,
    OWNLightingEvent,
)

from .const import (
    CONF_PLATFORMS,
    CONF_ENTITY,
    CONF_DEVICE_CLASS,
    CONF_DEVICE_MODEL,
    CONF_MANUFACTURER,
    CONF_WHERE,
    CONF_WHO,
    DOMAIN,
    LOGGER,
)
from .gateway import MyHOMEGatewayHandler
from .myhome_device import MyHOMEEntity

SCAN_INTERVAL = timedelta(seconds=60)

SERVICE_SEND_INSTANT_POWER = "start_sending_instant_power"

ATTR_DURATION = "duration"
ATTR_DATE = "date"
ATTR_MONTH = "month"
ATTR_DAY = "day"


async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    _sensors = []
    _configured_sensors = hass.data[DOMAIN][config_entry.data[CONF_MAC]][
        CONF_PLATFORMS
    ][PLATFORM]
    _power_devices_configured = False

    for _sensor in _configured_sensors.keys():
        if (
            _configured_sensors[_sensor][CONF_DEVICE_CLASS] == SensorDeviceClass.POWER
            or _configured_sensors[_sensor][CONF_DEVICE_CLASS]
            == SensorDeviceClass.ENERGY
        ):
            _required_entities = list(
                _configured_sensors[_sensor][CONF_ENTITIES].keys()
            )

            if (
                _configured_sensors[_sensor][CONF_DEVICE_CLASS]
                == SensorDeviceClass.POWER
            ):
                _power_devices_configured = True

                ent_reg = er.async_get(hass)
                existing_entity_id = ent_reg.async_get_entity_id(
                    "sensor", DOMAIN, _sensor
                )
                if existing_entity_id is not None:
                    LOGGER.warning(
                        "Sensor %s: %s will be migrated to %s-%s",
                        _sensor,
                        existing_entity_id,
                        _sensor,
                        SensorDeviceClass.POWER,
                    )
                    ent_reg.async_update_entity(
                        entity_id=existing_entity_id,
                        new_unique_id=f"{_sensor}-{SensorDeviceClass.POWER}",
                    )

                _sensors.append(
                    MyHOMEPowerSensor(
                        hass=hass,
                        device_id=_sensor,
                        who=_configured_sensors[_sensor][CONF_WHO],
                        where=_configured_sensors[_sensor][CONF_WHERE],
                        name=_configured_sensors[_sensor][CONF_NAME],
                        device_class=_configured_sensors[_sensor][CONF_DEVICE_CLASS],
                        manufacturer=_configured_sensors[_sensor][CONF_MANUFACTURER],
                        model=_configured_sensors[_sensor][CONF_DEVICE_MODEL],
                        gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][
                            CONF_ENTITY
                        ],
                    )
                )
                _required_entities.remove(SensorDeviceClass.POWER)

            for entity_specific_id in _required_entities:
                _sensors.append(
                    MyHOMEEnergySensor(
                        hass=hass,
                        device_id=_sensor,
                        who=_configured_sensors[_sensor][CONF_WHO],
                        where=_configured_sensors[_sensor][CONF_WHERE],
                        name=_configured_sensors[_sensor][CONF_NAME],
                        entity_specific_id=entity_specific_id,
                        device_class=SensorDeviceClass.ENERGY,
                        manufacturer=_configured_sensors[_sensor][CONF_MANUFACTURER],
                        model=_configured_sensors[_sensor][CONF_DEVICE_MODEL],
                        gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][
                            CONF_ENTITY
                        ],
                    )
                )

        elif (
            _configured_sensors[_sensor][CONF_DEVICE_CLASS]
            == SensorDeviceClass.TEMPERATURE
        ):
            _sensors.append(
                MyHOMETemperatureSensor(
                    hass=hass,
                    device_id=_sensor,
                    who=_configured_sensors[_sensor][CONF_WHO],
                    where=_configured_sensors[_sensor][CONF_WHERE],
                    name=_configured_sensors[_sensor][CONF_NAME],
                    device_class=_configured_sensors[_sensor][CONF_DEVICE_CLASS],
                    manufacturer=_configured_sensors[_sensor][CONF_MANUFACTURER],
                    model=_configured_sensors[_sensor][CONF_DEVICE_MODEL],
                    gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
                )
            )

        elif (
            _configured_sensors[_sensor][CONF_DEVICE_CLASS]
            == SensorDeviceClass.ILLUMINANCE
        ):
            _sensors.append(
                MyHOMEIlluminanceSensor(
                    hass=hass,
                    device_id=_sensor,
                    who=_configured_sensors[_sensor][CONF_WHO],
                    where=_configured_sensors[_sensor][CONF_WHERE],
                    name=_configured_sensors[_sensor][CONF_NAME],
                    device_class=_configured_sensors[_sensor][CONF_DEVICE_CLASS],
                    manufacturer=_configured_sensors[_sensor][CONF_MANUFACTURER],
                    model=_configured_sensors[_sensor][CONF_DEVICE_MODEL],
                    gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
                )
            )

    if _power_devices_configured:
        platform = entity_platform.current_platform.get()

        platform.async_register_entity_service(
            SERVICE_SEND_INSTANT_POWER,
            {Optional(ATTR_DURATION): All(Coerce(int), Range(min=1, max=255))},
            "start_sending_instant_power",
        )

    async_add_entities(_sensors)


async def async_unload_entry(hass, config_entry):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    _configured_sensors = hass.data[DOMAIN][config_entry.data[CONF_MAC]][
        CONF_PLATFORMS
    ][PLATFORM]

    for _sensor in _configured_sensors.keys():
        del hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM][
            _sensor
        ]


class MyHOMEPowerSensor(MyHOMEEntity, SensorEntity):
    def __init__(
        self,
        hass,
        name: str,
        device_id: str,
        who: str,
        where: str,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ) -> None:
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._entity_specific_name = "Power"
        self._attr_name = f"{name} {self._entity_specific_name}"

        self._attr_device_class = device_class
        self._attr_unique_id = (
            f"{gateway.mac}-{self._device_id}-{self._attr_device_class}"
        )
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_state_class = SensorStateClass.MEASUREMENT

        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "Sensor": f"({self._where[0]}){self._where[1:]}"
        }

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._attr_device_class] = self
        await self.async_update()

    async def async_will_remove_from_hass(self):
        """When entity is removed from hass."""
        if (
            self._attr_device_class
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES][self._attr_device_class]

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        # await self.start_sending_instant_power(255)

    def handle_event(self, message: OWNEnergyEvent):
        """Handle an event message."""
        if message.message_type not in [MESSAGE_TYPE_ACTIVE_POWER]:
            return True

        LOGGER.info(
            "%s %s",
            self._gateway_handler.log_id,
            message.human_readable_log,
        )
        self._attr_native_value = message.active_power
        self.async_schedule_update_ha_state()

    async def start_sending_instant_power(self, duration):
        """Request automatic instant power."""
        await self._gateway_handler.send(
            OWNEnergyCommand.start_sending_instant_power(self._where, duration)
        )


class MyHOMEEnergySensor(MyHOMEEntity, SensorEntity):
    def __init__(
        self,
        hass,
        name: str,
        device_id: str,
        who: str,
        where: str,
        entity_specific_id: str,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ) -> None:
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._entity_specific_id = entity_specific_id
        if self._entity_specific_id == "daily-energy":
            self._entity_specific_name = "Energy (today)"
            self._attr_entity_registry_enabled_default = False
        elif self._entity_specific_id == "monthly-energy":
            self._entity_specific_name = "Energy (current month)"
            self._attr_entity_registry_enabled_default = False
        elif self._entity_specific_id == "total-energy":
            self._entity_specific_name = "Energy"
            self._attr_entity_registry_enabled_default = True
        self._attr_name = f"{name} {self._entity_specific_name}"

        self._attr_unique_id = (
            f"{gateway.mac}-{self._device_id}-{self._entity_specific_id}"
        )
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_should_poll = True
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "Sensor": f"({self._where[0]}){self._where[1:]}"
        }

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._entity_specific_id] = self
        await self.async_update()

    async def async_will_remove_from_hass(self):
        """When entity is removed from hass."""
        if (
            self._entity_specific_id
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES][self._entity_specific_id]

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        if self._entity_specific_id == "total-energy":
            await self._gateway_handler.send_status_request(
                OWNEnergyCommand.get_total_consumption(self._where)
            )
        elif self._entity_specific_id == "monthly-energy":
            await self._gateway_handler.send_status_request(
                OWNEnergyCommand.get_partial_monthly_consumption(self._where)
            )
        elif self._entity_specific_id == "daily-energy":
            await self._gateway_handler.send_status_request(
                OWNEnergyCommand.get_partial_daily_consumption(self._where)
            )

    def handle_event(self, message: OWNEnergyEvent):
        """Handle an event message."""
        if message.message_type not in [
            MESSAGE_TYPE_ENERGY_TOTALIZER,
            MESSAGE_TYPE_CURRENT_MONTH_CONSUMPTION,
            MESSAGE_TYPE_CURRENT_DAY_CONSUMPTION,
        ]:
            return True

        if (
            self._entity_specific_id == "total-energy"
            and message.message_type == MESSAGE_TYPE_ENERGY_TOTALIZER
        ):
            LOGGER.info(
                "%s %s",
                self._gateway_handler.log_id,
                message.human_readable_log,
            )
            self._attr_native_value = message.total_consumption
        elif (
            self._entity_specific_id == "monthly-energy"
            and message.message_type == MESSAGE_TYPE_CURRENT_MONTH_CONSUMPTION
        ):
            LOGGER.info(
                "%s %s",
                self._gateway_handler.log_id,
                message.human_readable_log,
            )
            self._attr_native_value = message.current_month_partial_consumption
        elif (
            self._entity_specific_id == "daily-energy"
            and message.message_type == MESSAGE_TYPE_CURRENT_DAY_CONSUMPTION
        ):
            LOGGER.info(
                "%s %s",
                self._gateway_handler.log_id,
                message.human_readable_log,
            )
            self._attr_native_value = message.current_day_partial_consumption
        self.async_schedule_update_ha_state()


class MyHOMETemperatureSensor(MyHOMEEntity, SensorEntity):
    def __init__(
        self,
        hass,
        name: str,
        device_id: str,
        who: str,
        where: str,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ) -> None:
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._entity_specific_name = "Temperature"
        self._attr_name = f"{name} {self._entity_specific_name}"

        self._attr_device_class = device_class
        self._attr_unique_id = (
            f"{gateway.mac}-{self._device_id}-{self._attr_device_class}"
        )
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_should_poll = True
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "Sensor": f"({self._where[0]}){self._where[1:]}"
        }

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._attr_device_class] = self
        await self.async_update()

    async def async_will_remove_from_hass(self):
        """When entity is removed from hass."""
        if (
            self._attr_device_class
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES][self._attr_device_class]

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway_handler.send_status_request(
            OWNHeatingCommand.get_temperature(self._where)
        )

    def handle_event(self, message: OWNHeatingEvent):
        """Handle an event message."""
        if message.message_type not in [
            MESSAGE_TYPE_MAIN_TEMPERATURE,
            MESSAGE_TYPE_SECONDARY_TEMPERATURE,
        ]:
            return True

        if message.message_type == MESSAGE_TYPE_MAIN_TEMPERATURE:
            LOGGER.info(
                "%s %s",
                self._gateway_handler.log_id,
                message.human_readable_log,
            )
            self._attr_native_value = message.main_temperature
            self.async_schedule_update_ha_state()
        elif message.message_type == MESSAGE_TYPE_SECONDARY_TEMPERATURE:
            LOGGER.info(
                "%s %s",
                self._gateway_handler.log_id,
                message.human_readable_log,
            )
            self._attr_native_value = message.secondary_temperature[1]
            self.async_schedule_update_ha_state()


class MyHOMEIlluminanceSensor(MyHOMEEntity, SensorEntity):
    def __init__(
        self,
        hass,
        name: str,
        device_id: str,
        who: str,
        where: str,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ) -> None:
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._entity_specific_name = "Illuminance"
        self._attr_name = f"{name} {self._entity_specific_name}"

        self._attr_device_class = device_class
        self._attr_unique_id = (
            f"{gateway.mac}-{self._device_id}-{self._attr_device_class}"
        )
        self._attr_native_unit_of_measurement = LIGHT_LUX
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "A": where[: len(where) // 2],
            "PL": where[len(where) // 2 :],
        }

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._attr_device_class] = self
        await self.async_update()

    async def async_will_remove_from_hass(self):
        """When entity is removed from hass."""
        if (
            self._attr_device_class
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES][self._attr_device_class]

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway_handler.send_status_request(
            OWNLightingCommand.get_illuminance(self._where)
        )

    def handle_event(self, message: OWNLightingEvent):
        """Handle an event message."""
        if message.message_type not in [MESSAGE_TYPE_ILLUMINANCE]:
            return True

        LOGGER.info(
            "%s %s",
            self._gateway_handler.log_id,
            message.human_readable_log,
        )
        self._attr_native_value = message.illuminance
        self.async_schedule_update_ha_state()
