"""Support for MyHome sensors (power/energy, temperature, illuminance)."""
from datetime import timedelta
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    DOMAIN as PLATFORM,
    SensorStateClass,
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_DEVICES,
    CONF_ENTITIES,
    POWER_WATT,
    ENERGY_WATT_HOUR,
    TEMP_CELSIUS,
    LIGHT_LUX,
)
from homeassistant.helpers import (
    config_validation as cv,
    entity_platform,
    entity_registry,
)

from OWNd.message import (
    MESSAGE_TYPE_ACTIVE_POWER,
    MESSAGE_TYPE_ENERGY_TOTALIZER,
    MESSAGE_TYPE_CURRENT_DAY_CONSUMPTION,
    MESSAGE_TYPE_CURRENT_MONTH_CONSUMPTION,
    MESSAGE_TYPE_MAIN_TEMPERATURE,
    MESSAGE_TYPE_SECONDARY_TEMPERATURE,
    MESSAGE_TYPE_ILLUMINANCE,
    OWNEnergyEvent,
    OWNEnergyCommand,
    OWNHeatingEvent,
    OWNHeatingCommand,
    OWNLightingCommand,
    OWNLightingEvent,
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
from .myhome_device import MyHOMEEntity
from .gateway import MyHOMEGatewayHandler

SCAN_INTERVAL = timedelta(seconds=60)

MYHOME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WHERE): cv.string,
        vol.Optional(CONF_WHO): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_INVERTED): cv.boolean,
        vol.Required(CONF_DEVICE_CLASS): vol.In(
            [
                SensorDeviceClass.TEMPERATURE,
                SensorDeviceClass.POWER,
                SensorDeviceClass.ENERGY,
                SensorDeviceClass.ILLUMINANCE,
            ]
        ),
        vol.Optional(CONF_MANUFACTURER): cv.string,
        vol.Optional(CONF_DEVICE_MODEL): cv.string,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_DEVICES): cv.schema_with_slug_keys(MYHOME_SCHEMA)}
)

SERVICE_SEND_INSTANT_POWER = "start_sending_instant_power"

ATTR_DURATION = "duration"
ATTR_DATE = "date"
ATTR_MONTH = "month"
ATTR_DAY = "day"


async def async_setup_platform(
    hass, config, async_add_entities, discovery_info=None
):  # pylint: disable=unused-argument
    if CONF not in hass.data[DOMAIN]:
        return False
    hass.data[DOMAIN][CONF][PLATFORM] = {}
    _configured_sensors = config.get(CONF_DEVICES)

    if _configured_sensors:
        for _, entity_info in _configured_sensors.items():
            who = entity_info[CONF_WHO] if CONF_WHO in entity_info else None
            where = entity_info[CONF_WHERE]
            name = (
                entity_info[CONF_NAME]
                if CONF_NAME in entity_info
                else f"Sensor {where}"
            )
            device_class = (
                entity_info[CONF_DEVICE_CLASS]
                if CONF_DEVICE_CLASS in entity_info
                else None
            )
            if who is None:
                if (
                    device_class == SensorDeviceClass.POWER
                    or device_class == SensorDeviceClass.ENERGY
                ):
                    who = "18"
                elif device_class == SensorDeviceClass.TEMPERATURE:
                    who = "4"
                elif device_class == SensorDeviceClass.ILLUMINANCE:
                    who = "1"
            device_id = f"{who}-{where}"
            if device_class == SensorDeviceClass.POWER:
                entities = [
                    SensorDeviceClass.POWER,
                    f"daily-{SensorDeviceClass.ENERGY}",
                    f"monthly-{SensorDeviceClass.ENERGY}",
                    f"total-{SensorDeviceClass.ENERGY}",
                ]
            elif device_class == SensorDeviceClass.ENERGY:
                entities = [
                    f"daily-{SensorDeviceClass.ENERGY}",
                    f"monthly-{SensorDeviceClass.ENERGY}",
                    f"total-{SensorDeviceClass.ENERGY}",
                ]
            elif device_class == SensorDeviceClass.ILLUMINANCE:
                entities = [SensorDeviceClass.ILLUMINANCE]
            elif device_class == SensorDeviceClass.TEMPERATURE:
                entities = []
            manufacturer = (
                entity_info[CONF_MANUFACTURER]
                if CONF_MANUFACTURER in entity_info
                else None
            )
            model = (
                entity_info[CONF_DEVICE_MODEL]
                if CONF_DEVICE_MODEL in entity_info
                else None
            )
            hass.data[DOMAIN][CONF][PLATFORM][device_id] = {
                CONF_WHO: who,
                CONF_WHERE: where,
                CONF_ENTITIES: entities,
                CONF_NAME: name,
                CONF_DEVICE_CLASS: device_class,
                CONF_MANUFACTURER: manufacturer,
                CONF_DEVICE_MODEL: model,
            }


async def async_setup_entry(
    hass, config_entry, async_add_entities
):  # pylint: disable=unused-argument
    if PLATFORM not in hass.data[DOMAIN][CONF]:
        return True

    _sensors = []
    _configured_sensors = hass.data[DOMAIN][CONF][PLATFORM]
    _power_devices_configured = False

    for _sensor in _configured_sensors.keys():
        if (
            _configured_sensors[_sensor][CONF_DEVICE_CLASS] == SensorDeviceClass.POWER
            or _configured_sensors[_sensor][CONF_DEVICE_CLASS] == SensorDeviceClass.ENERGY
        ):

            _required_entities = _configured_sensors[_sensor][CONF_ENTITIES]

            if _configured_sensors[_sensor][CONF_DEVICE_CLASS] == SensorDeviceClass.POWER:
                _power_devices_configured = True

                ent_reg = entity_registry.async_get(hass)
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
                        entity_specific_id=_configured_sensors[_sensor][CONF_ENTITIES][
                            0
                        ],
                        device_class=_configured_sensors[_sensor][CONF_DEVICE_CLASS],
                        manufacturer=_configured_sensors[_sensor][CONF_MANUFACTURER],
                        model=_configured_sensors[_sensor][CONF_DEVICE_MODEL],
                        gateway=hass.data[DOMAIN][CONF_GATEWAY],
                    )
                )

            for entity_specific_id in _required_entities:
                if entity_specific_id == SensorDeviceClass.POWER:
                    continue
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
                        gateway=hass.data[DOMAIN][CONF_GATEWAY],
                    )
                )

        elif (
            _configured_sensors[_sensor][CONF_DEVICE_CLASS] == SensorDeviceClass.TEMPERATURE
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
                    gateway=hass.data[DOMAIN][CONF_GATEWAY],
                )
            )

        elif (
            _configured_sensors[_sensor][CONF_DEVICE_CLASS] == SensorDeviceClass.ILLUMINANCE
        ):
            _sensors.append(
                MyHOMEIlluminanceSensor(
                    hass=hass,
                    device_id=_sensor,
                    who=_configured_sensors[_sensor][CONF_WHO],
                    where=_configured_sensors[_sensor][CONF_WHERE],
                    name=_configured_sensors[_sensor][CONF_NAME],
                    entity_specific_id=_configured_sensors[_sensor][CONF_ENTITIES][0],
                    device_class=_configured_sensors[_sensor][CONF_DEVICE_CLASS],
                    manufacturer=_configured_sensors[_sensor][CONF_MANUFACTURER],
                    model=_configured_sensors[_sensor][CONF_DEVICE_MODEL],
                    gateway=hass.data[DOMAIN][CONF_GATEWAY],
                )
            )

    if _power_devices_configured:
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

    async_add_entities(_sensors)


async def async_unload_entry(hass, config_entry):  # pylint: disable=unused-argument
    if PLATFORM not in hass.data[DOMAIN][CONF]:
        return True

    _configured_sensors = hass.data[DOMAIN][CONF][PLATFORM]

    for _sensor in _configured_sensors.keys():
        if _configured_sensors[_sensor][CONF_ENTITIES]:
            for _entity_name in _configured_sensors[_sensor][CONF_ENTITIES]:
                del hass.data[DOMAIN][CONF_ENTITIES][f"{_sensor}-{_entity_name}"]
        else:
            del hass.data[DOMAIN][CONF_ENTITIES][_sensor]


class MyHOMEPowerSensor(MyHOMEEntity, SensorEntity):
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
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._entity_specific_id = entity_specific_id
        self._entity_specific_name = "Power"

        self._attr_name = f"{name} {self._entity_specific_name}"
        self._attr_unique_id = f"{self._device_id}-{self._entity_specific_id}"

        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = POWER_WATT
        self._attr_state_class = SensorStateClass.MEASUREMENT

        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "Sensor": f"({self._where[0]}){self._where[1:]}"
        }

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        # await self.start_sending_instant_power(255)

    def handle_event(self, message: OWNEnergyEvent):
        """Handle an event message."""
        if message.message_type == MESSAGE_TYPE_ACTIVE_POWER:
            LOGGER.info(message.human_readable_log)
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
        self._attr_unique_id = f"{self._device_id}-{self._entity_specific_id}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = ENERGY_WATT_HOUR
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_should_poll = True
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "Sensor": f"({self._where[0]}){self._where[1:]}"
        }

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
        if (
            self._entity_specific_id == "total-energy"
            and message.message_type == MESSAGE_TYPE_ENERGY_TOTALIZER
        ):
            LOGGER.info(message.human_readable_log)
            self._attr_native_value = message.total_consumption
        elif (
            self._entity_specific_id == "monthly-energy"
            and message.message_type == MESSAGE_TYPE_CURRENT_MONTH_CONSUMPTION
        ):
            LOGGER.info(message.human_readable_log)
            self._attr_native_value = message.current_month_partial_consumption
        elif (
            self._entity_specific_id == "daily-energy"
            and message.message_type == MESSAGE_TYPE_CURRENT_DAY_CONSUMPTION
        ):
            LOGGER.info(message.human_readable_log)
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
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = TEMP_CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_should_poll = True
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "Sensor": f"({self._where[0]}){self._where[1:]}"
        }

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway_handler.send_status_request(
            OWNHeatingCommand.get_temperature(self._where)
        )

    def handle_event(self, message: OWNHeatingEvent):
        """Handle an event message."""
        if message.message_type == MESSAGE_TYPE_MAIN_TEMPERATURE:
            LOGGER.info(message.human_readable_log)
            self._attr_native_value = message.main_temperature
            self.async_schedule_update_ha_state()
        elif message.message_type == MESSAGE_TYPE_SECONDARY_TEMPERATURE:
            LOGGER.info(message.human_readable_log)
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
        entity_specific_id: str,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ) -> None:
        super().__init__(
            hass=hass,
            name=name,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._entity_specific_id = entity_specific_id

        self._attr_unique_id = f"{self._device_id}-{self._entity_specific_id}"

        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = LIGHT_LUX
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "A": where[: len(where) // 2],
            "PL": where[len(where) // 2 :],
        }

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway_handler.send_status_request(
            OWNLightingCommand.get_illuminance(self._where)
        )

    def handle_event(self, message: OWNLightingEvent):
        """Handle an event message."""
        if message.message_type == MESSAGE_TYPE_ILLUMINANCE:
            # if message.illuminance == 65535:
            #     return True
            LOGGER.info(message.human_readable_log)
            self._attr_native_value = message.illuminance
            self.async_schedule_update_ha_state()
