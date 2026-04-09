"""Support for MyHome sensors (power/energy, temperature, illuminance)."""

import re
from datetime import datetime, timedelta

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
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER
from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR,
    BinarySensorDeviceClass,
)
from homeassistant.components.switch import DOMAIN as SWITCH
from homeassistant.const import (
    CONF_ENTITIES,
    CONF_ENTITY_CATEGORY,
    CONF_NAME,
    CONF_MAC,
    EntityCategory,
    LIGHT_LUX,
    UnitOfPower,
    UnitOfEnergy,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er
from OWNd.message import (
    MESSAGE_TYPE_ACTIVE_POWER,
    MESSAGE_TYPE_CURRENT_DAY_CONSUMPTION,
    MESSAGE_TYPE_CURRENT_MONTH_CONSUMPTION,
    MESSAGE_TYPE_ENERGY_TOTALIZER,
    MESSAGE_TYPE_ILLUMINANCE,
    MESSAGE_TYPE_MAIN_TEMPERATURE,
    MESSAGE_TYPE_MOTION_TIMEOUT,
    MESSAGE_TYPE_PIR_SENSITIVITY,
    MESSAGE_TYPE_SECONDARY_TEMPERATURE,
    OWNEnergyCommand,
    OWNEnergyEvent,
    OWNHeatingCommand,
    OWNHeatingEvent,
    OWNLightingCommand,
    OWNLightingEvent,
    OWNCommand,
)

from .const import (
    CONF_PLATFORMS,
    CONF_ENTITY,
    CONF_DEVICE_CLASS,
    CONF_DEVICE_MODEL,
    CONF_ENTITY_NAME,
    CONF_MANUFACTURER,
    CONF_OPERATION,
    CONF_SENSOR_ADDRESS,
    CONF_WHERE,
    CONF_WHO,
    DOMAIN,
    LOGGER,
)
from .audio import build_audio_radio_command, build_audio_zone_command
from .gateway import MyHOMEGatewayHandler
from .light_management import EVENT_LIGHT_MANAGEMENT, build_light_management_request
from .media_player import ATTR_AREA as AUDIO_AREA_ATTR, ATTR_POINT as AUDIO_POINT_ATTR
from .myhome_device import MyHOMEEntity

SCAN_INTERVAL = timedelta(seconds=60)
PIR_SENSITIVITY = ["low", "medium", "high", "very high"]

_AUDIO_SENSOR_ENTITY_DEFINITIONS = {
    "equalization_1": {
        "name": "Equalization 1",
        "icon": "mdi:equalizer",
        "query_operation": "query_equalization_1",
        "snapshot_field": "equalization_1",
        "equalization": 1,
    },
    "equalization_2": {
        "name": "Equalization 2",
        "icon": "mdi:equalizer-outline",
        "query_operation": "query_equalization_2",
        "snapshot_field": "equalization_2",
        "equalization": 2,
    },
    "equalization_3": {
        "name": "Equalization 3",
        "icon": "mdi:equalizer-outline",
        "query_operation": "query_equalization_3",
        "snapshot_field": "equalization_3",
        "equalization": 3,
    },
}

_AUDIO_RADIO_SENSOR_DEFINITIONS = {
    "radio_frequency": {
        "name": "Radio frequency",
        "icon": "mdi:radio-fm",
        "snapshot_field": "frequency_label",
        "enabled_default": True,
    },
    "radio_station": {
        "name": "Radio station",
        "icon": "mdi:radio",
        "snapshot_field": "station",
        "enabled_default": True,
    },
    "radio_band": {
        "name": "Radio band",
        "icon": "mdi:waves-arrow-right",
        "snapshot_field": "band",
        "enabled_default": True,
    },
    "radio_rds": {
        "name": "Radio RDS",
        "icon": "mdi:text-box-outline",
        "snapshot_field": "rds_text",
        "enabled_default": True,
    },
}

_LIGHT_MANAGEMENT_SENSOR_DEFINITIONS = {
    "state_time": {
        "name": "State time",
        "icon": "mdi:timer-outline",
        "request": "state",
        "snapshot_field": "state_time",
    },
    "centralized_lux": {
        "name": "Centralized lux",
        "icon": "mdi:brightness-6",
        "request": "centralized_lux",
        "snapshot_field": "lux",
        "device_class": SensorDeviceClass.ILLUMINANCE,
        "native_unit": LIGHT_LUX,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "sensor_address": {
        "name": "Sensor address",
        "icon": "mdi:identifier",
        "request": "centralized_lux",
        "snapshot_field": "sensor_address",
        "enabled_default": False,
    },
    "error_name": {
        "name": "Sensor status",
        "icon": "mdi:alert-circle-outline",
        "request": "centralized_lux",
        "snapshot_field": "error_name",
        "enabled_default": False,
    },
}

LOAD_CONTROL_TOTALIZER_RE = re.compile(
    r"^\*#18\*(?P<where>\d+)(?:#0)?\*72#(?P<totalizer>[12])\*(?P<energy>\d+)\*(?P<day>\d+)\*(?P<month>\d+)\*(?P<year>\d+)\*(?P<hour>\d+)\*(?P<minute>\d+)##$"
)
LOAD_CONTROL_DIFFERENTIAL_LEVEL_RE = re.compile(
    r"^\*#18\*(?P<where>\d+)(?:#0)?\*73\*(?P<level>[1-3])##$"
)

SERVICE_SEND_INSTANT_POWER = "start_sending_instant_power"

ATTR_DURATION = "duration"
ATTR_DATE = "date"
ATTR_MONTH = "month"
ATTR_DAY = "day"


def _ensure_audio_sensor_configs(gateway_data: dict) -> None:
    sensor_config = gateway_data.setdefault(CONF_PLATFORMS, {}).setdefault(PLATFORM, {})
    media_players = gateway_data.get(CONF_PLATFORMS, {}).get(MEDIA_PLAYER, {})

    for media_player_id, media_player_config in media_players.items():
        area = media_player_config.get(AUDIO_AREA_ATTR)
        point = media_player_config.get(AUDIO_POINT_ATTR)
        if area is None or point is None:
            continue

        for operation, definition in _AUDIO_SENSOR_ENTITY_DEFINITIONS.items():
            device_id = f"{media_player_id}-{operation}"
            sensor_config.setdefault(
                device_id,
                {
                    CONF_WHO: "22",
                    CONF_WHERE: f"{int(area)}#{int(point)}",
                    CONF_NAME: media_player_config.get(
                        CONF_NAME,
                        f"Audio area {area} point {point}",
                    ),
                    CONF_ENTITY_NAME: definition["name"],
                    CONF_OPERATION: operation,
                    CONF_MANUFACTURER: media_player_config.get(
                        CONF_MANUFACTURER,
                        "BTicino S.p.A.",
                    ),
                    CONF_DEVICE_MODEL: media_player_config.get(CONF_DEVICE_MODEL),
                    CONF_ENTITIES: {},
                },
            )


def _ensure_audio_radio_sensor_configs(gateway_data: dict) -> None:
    sensor_config = gateway_data.setdefault(CONF_PLATFORMS, {}).setdefault(PLATFORM, {})
    media_players = gateway_data.get(CONF_PLATFORMS, {}).get(MEDIA_PLAYER, {})
    if not media_players:
        return

    first_media_player = next(iter(media_players.values()))
    base_name = "Audio radio"
    manufacturer = first_media_player.get(CONF_MANUFACTURER, "BTicino S.p.A.")
    model = first_media_player.get(CONF_DEVICE_MODEL)

    for operation, definition in _AUDIO_RADIO_SENSOR_DEFINITIONS.items():
        sensor_config.setdefault(
            f"audio-radio-{operation}",
            {
                CONF_WHO: "22",
                CONF_WHERE: "1",
                CONF_NAME: base_name,
                CONF_ENTITY_NAME: definition["name"],
                CONF_OPERATION: operation,
                CONF_MANUFACTURER: manufacturer,
                CONF_DEVICE_MODEL: model,
                CONF_ENTITIES: {},
            },
        )


def _build_own_command(raw_message: str):
    command = OWNCommand.parse(raw_message)
    return command if command is not None and command.is_valid else raw_message


def _format_totalizer_reset(
    day: str,
    month: str,
    year: str,
    hour: str,
    minute: str,
) -> str:
    year_value = int(year)
    if year_value < 100:
        year_value += 2000
    return datetime(
        year=year_value,
        month=int(month),
        day=int(day),
        hour=int(hour),
        minute=int(minute),
    ).isoformat(timespec="minutes")


async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    gateway_data = hass.data[DOMAIN][config_entry.data[CONF_MAC]]
    _ensure_audio_sensor_configs(gateway_data)
    _ensure_audio_radio_sensor_configs(gateway_data)

    _sensors = []
    _configured_sensors = gateway_data[CONF_PLATFORMS][PLATFORM]
    _power_devices_configured = False

    for _sensor in list(_configured_sensors.keys()):
        _sensor_config = _configured_sensors[_sensor]

        if _sensor_config.get(CONF_WHO) == "22":
            operation = _sensor_config.get(CONF_OPERATION)
            if operation in _AUDIO_RADIO_SENSOR_DEFINITIONS:
                _sensors.append(
                    MyHOMEAudioRadioSensor(
                        hass=hass,
                        device_id=_sensor,
                        who=_sensor_config[CONF_WHO],
                        where=_sensor_config[CONF_WHERE],
                        name=_sensor_config[CONF_NAME],
                        entity_name=_sensor_config.get(CONF_ENTITY_NAME),
                        operation=operation,
                        manufacturer=_sensor_config[CONF_MANUFACTURER],
                        model=_sensor_config[CONF_DEVICE_MODEL],
                        gateway=gateway_data[CONF_ENTITY],
                    )
                )
                continue
            _sensors.append(
                MyHOMEAudioEqualizationSensor(
                    hass=hass,
                    device_id=_sensor,
                    who=_sensor_config[CONF_WHO],
                    where=_sensor_config[CONF_WHERE],
                    name=_sensor_config[CONF_NAME],
                    entity_name=_sensor_config.get(CONF_ENTITY_NAME),
                    operation=_sensor_config.get(CONF_OPERATION),
                    manufacturer=_sensor_config[CONF_MANUFACTURER],
                    model=_sensor_config[CONF_DEVICE_MODEL],
                    gateway=gateway_data[CONF_ENTITY],
                )
            )
            continue

        if _sensor_config.get(CONF_WHO) == "24":
            _sensors.append(
                MyHOMELightManagementDiagnosticSensor(
                    hass=hass,
                    device_id=_sensor,
                    who=_sensor_config[CONF_WHO],
                    where=_sensor_config[CONF_WHERE],
                    name=_sensor_config[CONF_NAME],
                    entity_name=_sensor_config.get(CONF_ENTITY_NAME),
                    operation=_sensor_config.get(CONF_OPERATION),
                    sensor_address=_sensor_config.get(CONF_SENSOR_ADDRESS),
                    manufacturer=_sensor_config[CONF_MANUFACTURER],
                    model=_sensor_config[CONF_DEVICE_MODEL],
                    gateway=gateway_data[CONF_ENTITY],
                )
            )
            continue

        if (
            _sensor_config[CONF_DEVICE_CLASS] == SensorDeviceClass.POWER
            or _sensor_config[CONF_DEVICE_CLASS] == SensorDeviceClass.ENERGY
        ):
            _required_entities = list(
                _sensor_config[CONF_ENTITIES].keys()
            )

            if (
                _sensor_config[CONF_DEVICE_CLASS] == SensorDeviceClass.POWER
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
                        who=_sensor_config[CONF_WHO],
                        where=_sensor_config[CONF_WHERE],
                        name=_sensor_config[CONF_NAME],
                        device_class=_sensor_config[CONF_DEVICE_CLASS],
                        manufacturer=_sensor_config[CONF_MANUFACTURER],
                        model=_sensor_config[CONF_DEVICE_MODEL],
                        gateway=gateway_data[CONF_ENTITY],
                    )
                )
                _required_entities.remove(SensorDeviceClass.POWER)

            for entity_specific_id in _required_entities:
                _sensors.append(
                    MyHOMEEnergySensor(
                        hass=hass,
                        device_id=_sensor,
                        who=_sensor_config[CONF_WHO],
                        where=_sensor_config[CONF_WHERE],
                        name=_sensor_config[CONF_NAME],
                        entity_specific_id=entity_specific_id,
                        device_class=SensorDeviceClass.ENERGY,
                        manufacturer=_sensor_config[CONF_MANUFACTURER],
                        model=_sensor_config[CONF_DEVICE_MODEL],
                        gateway=gateway_data[CONF_ENTITY],
                    )
                )

        elif (
            _sensor_config[CONF_DEVICE_CLASS] == SensorDeviceClass.TEMPERATURE
        ):
            _sensors.append(
                MyHOMETemperatureSensor(
                    hass=hass,
                    device_id=_sensor,
                    who=_sensor_config[CONF_WHO],
                    where=_sensor_config[CONF_WHERE],
                    name=_sensor_config[CONF_NAME],
                    device_class=_sensor_config[CONF_DEVICE_CLASS],
                    manufacturer=_sensor_config[CONF_MANUFACTURER],
                    model=_sensor_config[CONF_DEVICE_MODEL],
                    gateway=gateway_data[CONF_ENTITY],
                )
            )

        elif (
            _sensor_config[CONF_DEVICE_CLASS] == SensorDeviceClass.ILLUMINANCE
        ):
            _sensors.append(
                MyHOMEIlluminanceSensor(
                    hass=hass,
                    device_id=_sensor,
                    who=_sensor_config[CONF_WHO],
                    where=_sensor_config[CONF_WHERE],
                    name=_sensor_config[CONF_NAME],
                    device_class=_sensor_config[CONF_DEVICE_CLASS],
                    manufacturer=_sensor_config[CONF_MANUFACTURER],
                    model=_sensor_config[CONF_DEVICE_MODEL],
                    gateway=gateway_data[CONF_ENTITY],
                )
            )

    _configured_binary_sensors = gateway_data[CONF_PLATFORMS].get(BINARY_SENSOR, {})
    for _binary_sensor, _binary_sensor_config in _configured_binary_sensors.items():
        if (
            _binary_sensor_config[CONF_WHO] != "1"
            or _binary_sensor_config.get(CONF_DEVICE_CLASS)
            != BinarySensorDeviceClass.MOTION
        ):
            continue

        _configured_sensors.setdefault(
            _binary_sensor,
            {
                CONF_WHO: _binary_sensor_config[CONF_WHO],
                CONF_WHERE: _binary_sensor_config[CONF_WHERE],
                CONF_NAME: _binary_sensor_config[CONF_NAME],
                CONF_MANUFACTURER: _binary_sensor_config[CONF_MANUFACTURER],
                CONF_DEVICE_MODEL: _binary_sensor_config[CONF_DEVICE_MODEL],
                CONF_ENTITIES: {},
            },
        )

        _sensors.extend(
            [
                MyHOMEMotionTimeoutSensor(
                    hass=hass,
                    device_id=_binary_sensor,
                    who=_binary_sensor_config[CONF_WHO],
                    where=_binary_sensor_config[CONF_WHERE],
                    name=_binary_sensor_config[CONF_NAME],
                    manufacturer=_binary_sensor_config[CONF_MANUFACTURER],
                    model=_binary_sensor_config[CONF_DEVICE_MODEL],
                    gateway=gateway_data[CONF_ENTITY],
                ),
                MyHOMEPIRSensitivitySensor(
                    hass=hass,
                    device_id=_binary_sensor,
                    who=_binary_sensor_config[CONF_WHO],
                    where=_binary_sensor_config[CONF_WHERE],
                    name=_binary_sensor_config[CONF_NAME],
                    manufacturer=_binary_sensor_config[CONF_MANUFACTURER],
                    model=_binary_sensor_config[CONF_DEVICE_MODEL],
                    gateway=gateway_data[CONF_ENTITY],
                ),
            ]
        )

    _configured_switches = gateway_data[CONF_PLATFORMS].get(SWITCH, {})
    for _switch, _switch_config in _configured_switches.items():
        if _switch_config[CONF_WHO] != "18":
            continue

        _configured_sensors.setdefault(
            _switch,
            {
                CONF_WHO: _switch_config[CONF_WHO],
                CONF_WHERE: _switch_config[CONF_WHERE],
                CONF_NAME: _switch_config[CONF_NAME],
                CONF_MANUFACTURER: _switch_config[CONF_MANUFACTURER],
                CONF_DEVICE_MODEL: _switch_config[CONF_DEVICE_MODEL],
                CONF_ENTITIES: {},
            },
        )

        _sensors.extend(
            [
                MyHOMELoadActivePowerSensor(
                    hass=hass,
                    device_id=_switch,
                    who=_switch_config[CONF_WHO],
                    where=_switch_config[CONF_WHERE],
                    name=_switch_config[CONF_NAME],
                    manufacturer=_switch_config[CONF_MANUFACTURER],
                    model=_switch_config[CONF_DEVICE_MODEL],
                    gateway=gateway_data[CONF_ENTITY],
                ),
                MyHOMELoadDifferentialLevelSensor(
                    hass=hass,
                    device_id=_switch,
                    who=_switch_config[CONF_WHO],
                    where=_switch_config[CONF_WHERE],
                    name=_switch_config[CONF_NAME],
                    manufacturer=_switch_config[CONF_MANUFACTURER],
                    model=_switch_config[CONF_DEVICE_MODEL],
                    gateway=gateway_data[CONF_ENTITY],
                ),
                MyHOMELoadTotalizerSensor(
                    hass=hass,
                    device_id=_switch,
                    who=_switch_config[CONF_WHO],
                    where=_switch_config[CONF_WHERE],
                    name=_switch_config[CONF_NAME],
                    totalizer=1,
                    manufacturer=_switch_config[CONF_MANUFACTURER],
                    model=_switch_config[CONF_DEVICE_MODEL],
                    gateway=gateway_data[CONF_ENTITY],
                ),
                MyHOMELoadTotalizerSensor(
                    hass=hass,
                    device_id=_switch,
                    who=_switch_config[CONF_WHO],
                    where=_switch_config[CONF_WHERE],
                    name=_switch_config[CONF_NAME],
                    totalizer=2,
                    manufacturer=_switch_config[CONF_MANUFACTURER],
                    model=_switch_config[CONF_DEVICE_MODEL],
                    gateway=gateway_data[CONF_ENTITY],
                ),
            ]
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


class MyHOMEAudioEqualizationSensor(MyHOMEEntity, SensorEntity):
    """Represent WHO=22 equalization bands as native sensors."""

    def __init__(
        self,
        hass,
        name: str,
        entity_name: str | None,
        device_id: str,
        who: str,
        where: str,
        operation: str | None,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ) -> None:
        operation = str(operation)
        definition = _AUDIO_SENSOR_ENTITY_DEFINITIONS[operation]
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model or "MyHOME Audio Control",
            gateway=gateway,
        )

        area_text, point_text = str(where).split("#", 1)
        self._operation = operation
        self._definition = definition
        self._area = int(area_text)
        self._point = int(point_text)
        self._attr_name = entity_name or definition["name"]
        self._attr_unique_id = f"{gateway.mac}-{self._device_id}"
        self._attr_icon = definition["icon"]
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "area": self._area,
            "point": self._point,
            "audio_operation": self._operation,
            "bands": None,
            "last_update": None,
        }

    async def async_added_to_hass(self):
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._platform] = self
        self.async_on_remove(
            self._hass.bus.async_listen(
                "myhome_audio_feedback_event",
                self._handle_audio_feedback_event,
            )
        )
        await self.async_update()

    async def async_will_remove_from_hass(self):
        if (
            self._platform
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES][self._platform]

    def _apply_snapshot(self, snapshot: dict | None) -> None:
        if not snapshot:
            return

        bands = snapshot.get(self._definition["snapshot_field"])
        if bands is None:
            return

        formatted_bands = [str(band) for band in bands]
        self._attr_native_value = ", ".join(formatted_bands)
        self._attr_extra_state_attributes["bands"] = formatted_bands
        self._attr_extra_state_attributes["last_update"] = snapshot.get("last_update")

    async def async_update(self):
        await self._gateway_handler.send_status_request_collect(
            build_audio_zone_command(
                self._area,
                self._point,
                self._definition["query_operation"],
            )
        )
        self._apply_snapshot(
            self._gateway_handler.audio.zone_snapshot(self._area, self._point)
        )
        self.async_schedule_update_ha_state()

    @callback
    def _handle_audio_feedback_event(self, event) -> None:
        data = dict(event.data)
        if data.get("gateway_mac") != self._gateway_handler.mac:
            return
        if int(data.get("area", -1)) != self._area:
            return
        if int(data.get("point", -1)) != self._point:
            return
        if data.get("kind") != "speaker_equalization":
            return
        if int(data.get("equalization", -1)) != self._definition["equalization"]:
            return

        self._apply_snapshot(
            self._gateway_handler.audio.zone_snapshot(self._area, self._point)
        )
        self.async_write_ha_state()


class MyHOMEAudioRadioSensor(MyHOMEEntity, SensorEntity):
    """Represent WHO=22 radio status as native sensors."""

    def __init__(
        self,
        hass,
        name: str,
        entity_name: str | None,
        device_id: str,
        who: str,
        where: str,
        operation: str | None,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ) -> None:
        operation = str(operation)
        definition = _AUDIO_RADIO_SENSOR_DEFINITIONS[operation]
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model or "MyHOME Audio Radio",
            gateway=gateway,
        )

        self._operation = operation
        self._definition = definition
        self._source_id = 1
        self._attr_name = entity_name or definition["name"]
        self._attr_unique_id = f"{gateway.mac}-{self._device_id}"
        self._attr_icon = definition["icon"]
        self._attr_entity_registry_enabled_default = definition.get(
            "enabled_default",
            True,
        )
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "source_id": self._source_id,
            "frequency": None,
            "frequency_label": None,
            "station": None,
            "band": None,
            "rds_text": None,
            "last_update": None,
        }

    async def async_added_to_hass(self):
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._platform] = self
        self.async_on_remove(
            self._hass.bus.async_listen(
                "myhome_audio_feedback_event",
                self._handle_audio_feedback_event,
            )
        )
        await self.async_update()

    async def async_will_remove_from_hass(self):
        if (
            self._platform
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES][self._platform]

    def _apply_snapshot(self, snapshot: dict | None) -> None:
        if not snapshot:
            return

        self._attr_native_value = snapshot.get(self._definition["snapshot_field"])
        self._attr_extra_state_attributes.update(
            {
                "frequency": snapshot.get("frequency"),
                "frequency_label": snapshot.get("frequency_label"),
                "station": snapshot.get("station"),
                "band": snapshot.get("band"),
                "rds_text": snapshot.get("rds_text"),
                "last_update": snapshot.get("last_update"),
            }
        )

    async def async_update(self):
        messages = build_audio_radio_command("query_status")
        if isinstance(messages, str):
            messages = [messages]
        for message in messages:
            await self._gateway_handler.send_status_request_collect(message)
        self._apply_snapshot(self._gateway_handler.audio.radio_snapshot())
        self.async_schedule_update_ha_state()

    @callback
    def _handle_audio_feedback_event(self, event) -> None:
        data = dict(event.data)
        if data.get("gateway_mac") != self._gateway_handler.mac:
            return
        if int(data.get("source_id", -1)) != self._source_id:
            return
        if data.get("kind") not in {
            "source_device_state",
            "source_frequency_station",
            "source_frequency",
            "source_station",
            "source_rds",
        }:
            return

        self._apply_snapshot(self._gateway_handler.audio.radio_snapshot())
        self.async_write_ha_state()


class MyHOMELightManagementDiagnosticSensor(MyHOMEEntity, SensorEntity):
    """Represent read-only WHO=24 state as native sensors."""

    def __init__(
        self,
        hass,
        name: str,
        entity_name: str | None,
        device_id: str,
        who: str,
        where: str,
        operation: str | None,
        sensor_address: str | None,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ) -> None:
        operation = str(operation)
        definition = _LIGHT_MANAGEMENT_SENSOR_DEFINITIONS[operation]
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model or "MyHOME Light Management",
            gateway=gateway,
        )

        self._operation = operation
        self._definition = definition
        self._sensor_address = (
            str(sensor_address).strip() if sensor_address is not None else None
        )
        self._attr_name = entity_name or definition["name"]
        self._attr_unique_id = f"{gateway.mac}-{self._device_id}"
        self._attr_icon = definition["icon"]
        self._attr_device_class = definition.get("device_class")
        self._attr_native_unit_of_measurement = definition.get("native_unit")
        self._attr_state_class = definition.get("state_class")
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = definition.get(
            "enabled_default",
            True,
        )
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "where": self._where,
            "lm_operation": self._operation,
            "sensor_address": self._sensor_address,
            "last_update": None,
        }

    async def async_added_to_hass(self):
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._platform] = self
        self.async_on_remove(
            self._hass.bus.async_listen(
                EVENT_LIGHT_MANAGEMENT,
                self._handle_light_management_event,
            )
        )
        await self.async_update()

    async def async_will_remove_from_hass(self):
        if (
            self._platform
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES][self._platform]

    def _apply_snapshot(self, snapshot: dict | None) -> None:
        if not snapshot:
            return

        value = snapshot.get(self._definition["snapshot_field"])
        if value is None:
            return

        self._attr_native_value = value
        self._sensor_address = snapshot.get("sensor_address", self._sensor_address)
        self._attr_extra_state_attributes["sensor_address"] = self._sensor_address
        self._attr_extra_state_attributes["last_update"] = snapshot.get("last_update")
        if self._operation == "state_time":
            self._attr_extra_state_attributes["mode"] = snapshot.get("mode_name")
            self._attr_extra_state_attributes["exit_condition"] = snapshot.get(
                "exit_condition_name"
            )
        elif self._operation in {"centralized_lux", "error_name", "sensor_address"}:
            self._attr_extra_state_attributes["error"] = snapshot.get("error_name")

    async def async_update(self):
        request = self._definition["request"]
        request_kwargs = {}
        if request == "centralized_lux":
            snapshot = self._gateway_handler.light_management.zone_snapshot(self._where)
            sensor_address = self._sensor_address or (
                None if snapshot is None else snapshot.get("sensor_address")
            )
            if not sensor_address:
                self._apply_snapshot(snapshot)
                self.async_schedule_update_ha_state()
                return
            request_kwargs["sensor_address"] = sensor_address

        await self._gateway_handler.send_status_request_collect(
            build_light_management_request(
                request,
                self._where,
                **request_kwargs,
            )
        )
        self._apply_snapshot(
            self._gateway_handler.light_management.zone_snapshot(self._where)
        )
        self.async_schedule_update_ha_state()

    @callback
    def _handle_light_management_event(self, event) -> None:
        data = dict(event.data)
        if data.get("gateway_mac") != self._gateway_handler.mac:
            return
        if str(data.get("where")) != self._where:
            return
        if data.get("kind") != self._definition["request"]:
            return

        self._apply_snapshot(
            self._gateway_handler.light_management.zone_snapshot(self._where)
        )
        self.async_write_ha_state()


class MyHOMEMotionDiagnosticSensor(MyHOMEEntity, SensorEntity):
    def __init__(
        self,
        hass,
        name: str,
        device_id: str,
        who: str,
        where: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
        *,
        entity_specific_id: str,
        entity_name: str,
        icon: str,
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
        self._attr_name = entity_name
        self._attr_unique_id = f"{gateway.mac}-{self._device_id}-{self._entity_specific_id}"
        self._attr_icon = icon
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False
        self._attr_extra_state_attributes = {
            "A": where[: len(where) // 2],
            "PL": where[len(where) // 2 :],
        }

    async def async_added_to_hass(self):
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._entity_specific_id] = self
        await self.async_update()

    async def async_will_remove_from_hass(self):
        if (
            self._entity_specific_id
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES][self._entity_specific_id]


class MyHOMEMotionTimeoutSensor(MyHOMEMotionDiagnosticSensor):
    def __init__(self, **kwargs) -> None:
        super().__init__(
            entity_specific_id="motion-timeout",
            entity_name="Motion timeout",
            icon="mdi:timer-outline",
            **kwargs,
        )
        self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
        self._attr_native_value = None

    async def async_update(self):
        await self._gateway_handler.send_status_request(
            OWNLightingCommand.get_motion_timeout(self._where)
        )

    def handle_event(self, message: OWNLightingEvent):
        if message.message_type != MESSAGE_TYPE_MOTION_TIMEOUT:
            return True

        self._attr_native_value = int(message.motion_timeout.total_seconds())
        self.async_schedule_update_ha_state()
        return True


class MyHOMEPIRSensitivitySensor(MyHOMEMotionDiagnosticSensor):
    def __init__(self, **kwargs) -> None:
        super().__init__(
            entity_specific_id="pir-sensitivity",
            entity_name="PIR sensitivity",
            icon="mdi:motion-sensor",
            **kwargs,
        )
        self._attr_native_value = None

    async def async_update(self):
        await self._gateway_handler.send_status_request(
            OWNLightingCommand.get_pir_sensitivity(self._where)
        )

    def handle_event(self, message: OWNLightingEvent):
        if message.message_type != MESSAGE_TYPE_PIR_SENSITIVITY:
            return True

        self._attr_native_value = PIR_SENSITIVITY[message.pir_sensitivity]
        self.async_schedule_update_ha_state()
        return True


class MyHOMELoadSensor(MyHOMEEntity, SensorEntity):
    def __init__(
        self,
        hass,
        name: str,
        device_id: str,
        who: str,
        where: str,
        entity_specific_id: str,
        entity_name: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
        device_class: str | None = None,
        native_unit: str | None = None,
        state_class: str | None = None,
        entity_category: str | None = None,
        enabled_default: bool = True,
    ):
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model or "F522",
            gateway=gateway,
        )

        self._entity_specific_id = entity_specific_id
        self._full_where = f"{self._where}#0" if self._where.startswith("7") else self._where
        self._attr_name = entity_name
        self._attr_unique_id = f"{gateway.mac}-{self._device_id}-{self._entity_specific_id}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = native_unit
        self._attr_state_class = state_class
        self._attr_entity_registry_enabled_default = enabled_default
        self._attr_extra_state_attributes = {
            "load": self._where[1:] if self._where.startswith("7") else self._where,
        }
        self._attr_native_value = None
        if entity_category is not None:
            self._attr_entity_category = entity_category

    async def async_added_to_hass(self):
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._entity_specific_id] = self

    async def async_will_remove_from_hass(self):
        if (
            self._entity_specific_id
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES][self._entity_specific_id]

    def _load_switch_attributes(self):
        switch_config = self._hass.data[DOMAIN][self._gateway_handler.mac][
            CONF_PLATFORMS
        ].get(SWITCH, {}).get(self._device_id, {})
        switch_entity = switch_config.get(CONF_ENTITIES, {}).get(SWITCH)
        if switch_entity is None:
            return {}
        return switch_entity.extra_state_attributes or {}

    def _load_switch_entity(self):
        switch_config = self._hass.data[DOMAIN][self._gateway_handler.mac][
            CONF_PLATFORMS
        ].get(SWITCH, {}).get(self._device_id, {})
        return switch_config.get(CONF_ENTITIES, {}).get(SWITCH)

    def apply_switch_attributes(self, switch_attrs):
        """Update the sensor from the parent load switch attributes."""


class MyHOMELoadActivePowerSensor(MyHOMELoadSensor):
    def __init__(self, **kwargs):
        super().__init__(
            entity_specific_id="load-active-power",
            entity_name="Active power",
            device_class=SensorDeviceClass.POWER,
            native_unit=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            **kwargs,
        )

    async def async_update(self):
        switch_entity = self._load_switch_entity()
        if switch_entity is not None:
            await switch_entity.async_update()
        self.apply_switch_attributes(self._load_switch_attributes())

    def apply_switch_attributes(self, switch_attrs):
        if switch_attrs.get("active_power_w") is None:
            return
        self._attr_native_value = switch_attrs["active_power_w"]
        self.async_schedule_update_ha_state()

    def handle_event(self, message: OWNEnergyEvent):
        if message.message_type != MESSAGE_TYPE_ACTIVE_POWER:
            return True

        self._attr_native_value = message.active_power
        self.async_schedule_update_ha_state()
        return True


class MyHOMELoadDifferentialLevelSensor(MyHOMELoadSensor):
    def __init__(self, **kwargs):
        super().__init__(
            entity_specific_id="load-differential-current-level",
            entity_name="Differential current level",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
            **kwargs,
        )

    async def async_update(self):
        switch_entity = self._load_switch_entity()
        if switch_entity is not None:
            await switch_entity.async_update()
        self.apply_switch_attributes(self._load_switch_attributes())

    def apply_switch_attributes(self, switch_attrs):
        if switch_attrs.get("differential_current_level") is None:
            return
        self._attr_native_value = switch_attrs["differential_current_level"]
        self.async_schedule_update_ha_state()

    def handle_event(self, message: OWNEnergyEvent):
        match = LOAD_CONTROL_DIFFERENTIAL_LEVEL_RE.match(str(message))
        if match is None:
            return True

        self._attr_native_value = int(match.group("level"))
        self.async_schedule_update_ha_state()
        return True


class MyHOMELoadTotalizerSensor(MyHOMELoadSensor):
    def __init__(self, totalizer: int, **kwargs):
        self._totalizer = int(totalizer)
        super().__init__(
            entity_specific_id=f"load-totalizer-{self._totalizer}",
            entity_name=f"Totalizer {self._totalizer}",
            device_class=SensorDeviceClass.ENERGY,
            native_unit=UnitOfEnergy.WATT_HOUR,
            state_class=SensorStateClass.TOTAL_INCREASING,
            entity_category=EntityCategory.DIAGNOSTIC,
            enabled_default=self._totalizer == 1,
            **kwargs,
        )

    async def async_update(self):
        switch_entity = self._load_switch_entity()
        if switch_entity is not None:
            if self._totalizer == 1:
                await switch_entity.async_update()
            else:
                await switch_entity.async_refresh_totalizer(self._totalizer)
        self.apply_switch_attributes(self._load_switch_attributes())

    def apply_switch_attributes(self, switch_attrs):
        totalizer_key = f"totalizer_{self._totalizer}_wh"
        if switch_attrs.get(totalizer_key) is not None:
            self._attr_native_value = switch_attrs[totalizer_key]
            self._attr_extra_state_attributes["last_reset_at"] = switch_attrs.get(
                f"totalizer_{self._totalizer}_last_reset"
            )
            self.async_schedule_update_ha_state()

    def handle_event(self, message: OWNEnergyEvent):
        match = LOAD_CONTROL_TOTALIZER_RE.match(str(message))
        if match is None or int(match.group("totalizer")) != self._totalizer:
            return True

        try:
            last_reset = _format_totalizer_reset(
                match.group("day"),
                match.group("month"),
                match.group("year"),
                match.group("hour"),
                match.group("minute"),
            )
        except ValueError:
            last_reset = None

        self._attr_native_value = int(match.group("energy"))
        self._attr_extra_state_attributes["last_reset_at"] = last_reset
        self.async_schedule_update_ha_state()
        return True
