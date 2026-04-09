"""Support for MyHome heating and extended thermoregulation."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, DOMAIN as PLATFORM
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    SWING_OFF,
    SWING_ON,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import CONF_MAC, CONF_NAME, UnitOfTemperature
from homeassistant.core import Event

from OWNd.message import (
    CLIMATE_MODE_AUTO,
    CLIMATE_MODE_COOL,
    CLIMATE_MODE_HEAT,
    CLIMATE_MODE_OFF,
    MESSAGE_TYPE_ACTION,
    MESSAGE_TYPE_LOCAL_OFFSET,
    MESSAGE_TYPE_LOCAL_TARGET_TEMPERATURE,
    MESSAGE_TYPE_MAIN_HUMIDITY,
    MESSAGE_TYPE_MAIN_TEMPERATURE,
    MESSAGE_TYPE_MODE,
    MESSAGE_TYPE_MODE_TARGET,
    MESSAGE_TYPE_TARGET_TEMPERATURE,
    OWNHeatingCommand,
    OWNHeatingEvent,
)

from .const import (
    CONF_CENTRAL,
    CONF_COOLING_SUPPORT,
    CONF_DEVICE_MODEL,
    CONF_ENTITY,
    CONF_FAN_SUPPORT,
    CONF_HEATING_SUPPORT,
    CONF_MANUFACTURER,
    CONF_PLATFORMS,
    CONF_STANDALONE,
    CONF_WHO,
    CONF_ZONE,
    DOMAIN,
    LOGGER,
)
from .gateway import MyHOMEGatewayHandler
from .myhome_device import MyHOMEEntity
from .thermo import (
    EVENT_THERMO,
    MODE_FAMILY_COOL,
    MODE_FAMILY_GENERIC,
    MODE_FAMILY_HEAT,
    OPERATING_MODE_AUTO,
    OPERATING_MODE_HOLIDAY_DAILY,
    OPERATING_MODE_HOLIDAY_DAYS,
    OPERATING_MODE_PROGRAM,
    OPERATING_MODE_SCENARIO,
    PRESET_ANTIFREEZE,
    PRESET_GENERIC_PROTECTION,
    PRESET_THERMAL_PROTECTION,
    build_central_command,
    build_request,
    build_split_set_command,
    build_zone_command,
)

PRESET_NONE = "none"

SPLIT_TO_HVAC = {
    "winter": HVACMode.HEAT,
    "summer": HVACMode.COOL,
    "auto": HVACMode.AUTO,
    "off": HVACMode.OFF,
    "fan_only": HVACMode.FAN_ONLY,
    "dehumidification": HVACMode.DRY,
}

HVAC_TO_SPLIT = {
    HVACMode.HEAT: "heat",
    HVACMode.COOL: "cool",
    HVACMode.AUTO: "auto",
    HVACMode.HEAT_COOL: "auto",
    HVACMode.OFF: "off",
    HVACMode.FAN_ONLY: "fan_only",
    HVACMode.DRY: "dry",
}

FAN_MODE_TO_SPLIT = {
    FAN_AUTO: "auto",
    FAN_LOW: "low",
    FAN_MEDIUM: "medium",
    FAN_HIGH: "high",
    "off": "off",
}

SPLIT_TO_FAN_MODE = {
    "auto": FAN_AUTO,
    "low": FAN_LOW,
    "medium": FAN_MEDIUM,
    "high": FAN_HIGH,
}


async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    climate_devices = []
    configured_devices = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][
        PLATFORM
    ]

    for climate_device in configured_devices.keys():
        config = configured_devices[climate_device]
        climate_devices.append(
            MyHOMEClimate(
                hass=hass,
                device_id=climate_device,
                who=config[CONF_WHO],
                where=config[CONF_ZONE],
                name=config[CONF_NAME],
                heating=config[CONF_HEATING_SUPPORT],
                cooling=config[CONF_COOLING_SUPPORT],
                fan=config[CONF_FAN_SUPPORT],
                standalone=config[CONF_STANDALONE],
                central=config[CONF_CENTRAL],
                manufacturer=config[CONF_MANUFACTURER],
                model=config[CONF_DEVICE_MODEL],
                gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
            )
        )

    async_add_entities(climate_devices)


async def async_unload_entry(hass, config_entry):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    configured_devices = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][
        PLATFORM
    ]

    for climate_device in configured_devices.keys():
        del hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM][
            climate_device
        ]


class MyHOMEClimate(MyHOMEEntity, ClimateEntity):
    """Expose MyHOME thermoregulation zones and split controls."""

    def __init__(
        self,
        hass,
        name: str,
        device_id: str,
        who: str,
        where: str,
        heating: bool,
        cooling: bool,
        fan: bool,
        standalone: bool,
        central: bool,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
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

        self._standalone = standalone
        self._central = True if self._where == "#0" else central
        self._is_split = self._where.startswith("3#")
        self._fan = fan

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_precision = 0.1
        self._attr_target_temperature_step = 0.5
        self._attr_min_temp = 5
        self._attr_max_temp = 40

        self._heating = heating or self._is_split
        self._cooling = cooling or self._is_split

        self._attr_supported_features = 0
        self._attr_hvac_modes = [HVACMode.OFF]
        self._attr_fan_modes = []
        self._attr_swing_modes = []

        if self._is_split:
            self._attr_supported_features |= (
                ClimateEntityFeature.TARGET_TEMPERATURE
                | ClimateEntityFeature.FAN_MODE
                | ClimateEntityFeature.SWING_MODE
            )
            self._attr_hvac_modes.extend(
                [
                    HVACMode.HEAT,
                    HVACMode.COOL,
                    HVACMode.AUTO,
                    HVACMode.FAN_ONLY,
                    HVACMode.DRY,
                ]
            )
            self._attr_fan_modes = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH, "off"]
            self._attr_swing_modes = [SWING_OFF, SWING_ON]
        elif self._heating or self._cooling:
            self._attr_supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
            self._attr_hvac_modes.append(HVACMode.AUTO)
            if self._heating:
                self._attr_hvac_modes.append(HVACMode.HEAT)
            if self._cooling:
                self._attr_hvac_modes.append(HVACMode.COOL)

            preset_modes = [PRESET_NONE]
            if self._heating:
                preset_modes.append(PRESET_ANTIFREEZE)
            if self._cooling:
                preset_modes.append(PRESET_THERMAL_PROTECTION)
            if self._heating and self._cooling:
                preset_modes.append(PRESET_GENERIC_PROTECTION)
            if len(preset_modes) > 1:
                self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE
                self._attr_preset_modes = preset_modes

        self._attr_current_temperature = None
        self._attr_current_humidity = None
        self._target_temperature = None
        self._local_offset = 0
        self._local_target_temperature = None

        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_action = HVACAction.OFF
        self._attr_fan_mode = None
        self._attr_swing_mode = None
        self._attr_preset_mode = PRESET_NONE

    async def async_added_to_hass(self):
        self.async_on_remove(
            self._hass.bus.async_listen(EVENT_THERMO, self._handle_thermo_event)
        )
        await super().async_added_to_hass()
        self._sync_from_thermo()

    async def async_update(self):
        """Update the entity by requesting all relevant thermoregulation state."""

        requests: list[str] = []

        if self._is_split:
            requests.append("split_control")
        else:
            requests.extend(
                [
                    "zone_status",
                    "zone_temperature",
                    "zone_complete_status",
                    "zone_local_offset",
                    "zone_setpoint",
                    "zone_valves",
                ]
            )
            if self._fan:
                requests.append("zone_fan_speed")
            if self._central:
                requests.extend(
                    [
                        "central_mode",
                        "holiday_end_date",
                        "holiday_end_time",
                        "diag_central",
                        "diag_central_autodiagnostic",
                        "diag_failure_counts",
                    ]
                )

        for request in dict.fromkeys(requests):
            await self.async_request_thermo(request)

    @property
    def target_temperature(self) -> float | None:
        self._sync_from_thermo()
        if self._local_target_temperature is not None:
            return self._local_target_temperature
        return self._target_temperature

    @property
    def extra_state_attributes(self) -> dict:
        attributes = {
            "where": self._where,
            "is_split": self._is_split,
            "is_central_managed": self._central,
            "local_offset": self._local_offset,
        }

        zone_state = self._gateway_handler.thermo.get_zone(self._where)
        if zone_state is not None:
            attributes.update(zone_state.to_attributes())

        if self._central:
            attributes.update(self._gateway_handler.thermo.central.to_attributes())

        if self._is_split:
            split_state = self._gateway_handler.thermo.get_split(self._where)
            if split_state is not None:
                attributes.update(split_state.to_attributes())

        return attributes

    def _handle_thermo_event(self, event: Event) -> None:
        data = event.data
        if data.get("gateway_mac") != self._gateway_handler.mac:
            return

        scope = data.get("scope")
        zone = data.get("zone")
        if scope == "split" and self._is_split and data.get("where") == self._where:
            self._sync_from_thermo()
            self.async_schedule_update_ha_state()
            return

        if scope == "central" and self._central:
            self._sync_from_thermo()
            self.async_schedule_update_ha_state()
            return

        zone_number = self._zone_number
        if scope == "zone" and zone is not None and zone_number == int(zone):
            self._sync_from_thermo()
            self.async_schedule_update_ha_state()

    @property
    def _zone_number(self) -> int | None:
        if self._where.startswith("#0#"):
            return int(self._where.split("#")[-1])
        if self._where.startswith("#"):
            return int(self._where[1:])
        if self._where.isdigit():
            return int(self._where)
        return None

    def _zone_state(self):
        return self._gateway_handler.thermo.get_zone(self._where)

    def _split_state(self):
        return self._gateway_handler.thermo.get_split(self._where)

    def _mode_family_for_hvac(self, hvac_mode: HVACMode | str | None = None) -> str:
        hvac_mode = hvac_mode or self._attr_hvac_mode
        if hvac_mode == HVACMode.COOL:
            return MODE_FAMILY_COOL
        if hvac_mode == HVACMode.HEAT:
            return MODE_FAMILY_HEAT
        return MODE_FAMILY_GENERIC

    def _hvac_mode_from_zone_state(self) -> HVACMode | None:
        zone_state = self._zone_state()
        central_state = self._gateway_handler.thermo.central if self._central else None
        state = zone_state or central_state
        if state is None:
            return None

        preset_mode = getattr(state, "preset_mode", None)
        if preset_mode in {
            PRESET_ANTIFREEZE,
            PRESET_THERMAL_PROTECTION,
            PRESET_GENERIC_PROTECTION,
        }:
            return HVACMode.OFF

        operating_mode = getattr(state, "operating_mode", None)
        mode_family = getattr(state, "mode_family", None)
        if operating_mode == "off":
            return HVACMode.OFF
        if operating_mode in {
            OPERATING_MODE_AUTO,
            OPERATING_MODE_PROGRAM,
            OPERATING_MODE_SCENARIO,
            OPERATING_MODE_HOLIDAY_DAILY,
            OPERATING_MODE_HOLIDAY_DAYS,
        } and HVACMode.AUTO in self._attr_hvac_modes:
            return HVACMode.AUTO
        if mode_family == MODE_FAMILY_COOL and HVACMode.COOL in self._attr_hvac_modes:
            return HVACMode.COOL
        if mode_family == MODE_FAMILY_HEAT and HVACMode.HEAT in self._attr_hvac_modes:
            return HVACMode.HEAT
        if mode_family == MODE_FAMILY_GENERIC and HVACMode.AUTO in self._attr_hvac_modes:
            return HVACMode.AUTO
        return self._attr_hvac_mode

    def _hvac_action_from_zone_state(self) -> HVACAction | None:
        if self._is_split:
            split = self._split_state()
            if split is None or split.mode is None:
                return None
            if split.mode == "off":
                return HVACAction.OFF
            if split.mode == "fan_only":
                return HVACAction.FAN
            if split.mode == "dehumidification":
                return HVACAction.DRYING
            if split.mode == "winter":
                return HVACAction.HEATING
            if split.mode == "summer":
                return HVACAction.COOLING
            return HVACAction.IDLE

        zone_state = self._zone_state()
        if zone_state is None:
            return self._attr_hvac_action
        active_states = {"on", "opened", "fan_auto", "fan_low", "fan_medium", "fan_high"}
        if zone_state.heating_valve_status in active_states:
            return HVACAction.HEATING
        if zone_state.cooling_valve_status in active_states:
            return HVACAction.COOLING
        if self._attr_hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        return HVACAction.IDLE

    def _preset_from_state(self) -> str:
        zone_state = self._zone_state()
        central_state = self._gateway_handler.thermo.central if self._central else None
        preset = None
        if zone_state is not None:
            preset = zone_state.preset_mode
        if preset is None and central_state is not None:
            preset = central_state.preset_mode
        return preset or PRESET_NONE

    def _sync_from_thermo(self) -> None:
        if self._is_split:
            split_state = self._split_state()
            if split_state is None:
                return
            if split_state.target_temperature is not None:
                self._target_temperature = split_state.target_temperature
            if split_state.mode is not None:
                self._attr_hvac_mode = SPLIT_TO_HVAC.get(
                    split_state.mode, self._attr_hvac_mode
                )
            if split_state.fan_mode is not None:
                self._attr_fan_mode = SPLIT_TO_FAN_MODE.get(
                    split_state.fan_mode, self._attr_fan_mode
                )
            if split_state.swing_mode is not None:
                self._attr_swing_mode = (
                    SWING_ON if split_state.swing_mode == "on" else SWING_OFF
                )
            self._attr_hvac_action = self._hvac_action_from_zone_state()
            return

        zone_state = self._zone_state()
        if zone_state is not None:
            if zone_state.current_temperature is not None:
                self._attr_current_temperature = zone_state.current_temperature
            if zone_state.current_humidity is not None:
                self._attr_current_humidity = zone_state.current_humidity
            if zone_state.target_temperature is not None:
                self._target_temperature = zone_state.target_temperature
            if zone_state.local_offset is not None:
                self._local_offset = zone_state.local_offset
            if zone_state.local_target_temperature is not None:
                self._local_target_temperature = zone_state.local_target_temperature
            if zone_state.fan_mode is not None:
                self._attr_fan_mode = SPLIT_TO_FAN_MODE.get(
                    zone_state.fan_mode, zone_state.fan_mode
                )

        hvac_mode = self._hvac_mode_from_zone_state()
        if hvac_mode is not None:
            self._attr_hvac_mode = hvac_mode
        hvac_action = self._hvac_action_from_zone_state()
        if hvac_action is not None:
            self._attr_hvac_action = hvac_action
        self._attr_preset_mode = self._preset_from_state()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if self._is_split:
            await self._gateway_handler.send(
                build_split_set_command(
                    self._where,
                    mode=HVAC_TO_SPLIT.get(hvac_mode),
                )
            )
            return

        if hvac_mode == HVACMode.OFF:
            await self._gateway_handler.send(
                build_zone_command(
                    self._where,
                    "off",
                    mode_family=self._mode_family_for_hvac(self._attr_hvac_mode),
                )
            )
        elif hvac_mode == HVACMode.AUTO:
            await self._gateway_handler.send(
                build_zone_command(
                    self._where,
                    "auto",
                    mode_family=self._mode_family_for_hvac(hvac_mode),
                )
            )
        elif hvac_mode in (HVACMode.HEAT, HVACMode.COOL):
            target = self.target_temperature
            if target is not None:
                await self._gateway_handler.send(
                    build_zone_command(
                        self._where,
                        "manual",
                        temperature=target,
                        mode_family=self._mode_family_for_hvac(hvac_mode),
                    )
                )

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        target_temperature = kwargs.get("temperature", self.target_temperature)
        if target_temperature is None:
            return

        if self._is_split:
            hvac_mode = kwargs.get("hvac_mode", self._attr_hvac_mode)
            await self._gateway_handler.send(
                build_split_set_command(
                    self._where,
                    mode=HVAC_TO_SPLIT.get(hvac_mode),
                    temperature=target_temperature,
                )
            )
            return

        effective_temperature = target_temperature - self._local_offset
        hvac_mode = kwargs.get("hvac_mode", self._attr_hvac_mode)
        await self._gateway_handler.send(
            build_zone_command(
                self._where,
                "manual",
                temperature=effective_temperature,
                mode_family=self._mode_family_for_hvac(hvac_mode),
            )
        )

    async def async_set_fan_mode(self, fan_mode):
        """Set new fan mode on split controls."""
        if not self._is_split:
            return
        await self._gateway_handler.send(
            build_split_set_command(
                self._where,
                fan_mode=FAN_MODE_TO_SPLIT.get(fan_mode, fan_mode),
            )
        )

    async def async_set_swing_mode(self, swing_mode):
        """Set new swing mode on split controls."""
        if not self._is_split:
            return
        await self._gateway_handler.send(
            build_split_set_command(
                self._where,
                swing_mode="on" if swing_mode == SWING_ON else "off",
            )
        )

    async def async_set_preset_mode(self, preset_mode: str):
        """Set one of the supported thermoregulation protection presets."""
        if self._is_split:
            return

        if preset_mode == PRESET_NONE:
            await self._gateway_handler.send(
                build_zone_command(
                    self._where,
                    "auto",
                    mode_family=self._mode_family_for_hvac(),
                )
            )
            return

        await self._gateway_handler.send(
            build_zone_command(
                self._where,
                preset_mode,
                mode_family=self._mode_family_for_hvac(),
            )
        )

    async def async_zone_command(self, operation: str, **kwargs):
        await self._gateway_handler.send(
            build_zone_command(
                self._where,
                operation,
                temperature=kwargs.get("temperature"),
                mode_family=kwargs.get("mode_family"),
            )
        )

    async def async_central_command(self, operation: str, **kwargs):
        await self._gateway_handler.send(
            build_central_command(
                operation,
                temperature=kwargs.get("temperature"),
                mode_family=kwargs.get("mode_family"),
                program=kwargs.get("program"),
                scenario=kwargs.get("scenario"),
                days=kwargs.get("days"),
                date_value=kwargs.get("date_value", kwargs.get("date")),
                time_value=kwargs.get("time_value", kwargs.get("time")),
            )
        )

    async def async_request_thermo(self, request: str, **kwargs):
        where = kwargs.get("where", self._where)
        await self._gateway_handler.send_status_request(
            build_request(
                request,
                where=where,
                actuator=kwargs.get("actuator"),
            ),
            wait_for_completion=kwargs.get("wait_for_completion", False),
        )

    def handle_event(self, message: OWNHeatingEvent):
        """Handle an event message."""
        if message.message_type == MESSAGE_TYPE_MAIN_TEMPERATURE:
            LOGGER.info("%s %s", self._gateway_handler.log_id, message.human_readable_log)
            self._attr_current_temperature = message.main_temperature
        elif message.message_type == MESSAGE_TYPE_MAIN_HUMIDITY:
            LOGGER.info("%s %s", self._gateway_handler.log_id, message.human_readable_log)
            self._attr_current_humidity = message.main_humidity
        elif message.message_type == MESSAGE_TYPE_TARGET_TEMPERATURE:
            LOGGER.info("%s %s", self._gateway_handler.log_id, message.human_readable_log)
            self._target_temperature = message.set_temperature
            self._local_target_temperature = self._target_temperature + self._local_offset
        elif message.message_type == MESSAGE_TYPE_LOCAL_OFFSET:
            LOGGER.info("%s %s", self._gateway_handler.log_id, message.human_readable_log)
            self._local_offset = message.local_offset
            if self._target_temperature is not None:
                self._local_target_temperature = self._target_temperature + self._local_offset
        elif message.message_type == MESSAGE_TYPE_LOCAL_TARGET_TEMPERATURE:
            LOGGER.info("%s %s", self._gateway_handler.log_id, message.human_readable_log)
            self._local_target_temperature = message.local_set_temperature
            self._target_temperature = self._local_target_temperature - self._local_offset
        elif message.message_type in {MESSAGE_TYPE_MODE, MESSAGE_TYPE_MODE_TARGET}:
            LOGGER.info("%s %s", self._gateway_handler.log_id, message.human_readable_log)
            if message.mode == CLIMATE_MODE_OFF:
                self._attr_hvac_mode = HVACMode.OFF
                self._attr_hvac_action = HVACAction.OFF
            elif message.mode == CLIMATE_MODE_COOL and HVACMode.COOL in self._attr_hvac_modes:
                self._attr_hvac_mode = HVACMode.COOL
            elif message.mode == CLIMATE_MODE_HEAT and HVACMode.HEAT in self._attr_hvac_modes:
                self._attr_hvac_mode = HVACMode.HEAT
            elif message.mode == CLIMATE_MODE_AUTO and HVACMode.AUTO in self._attr_hvac_modes:
                self._attr_hvac_mode = HVACMode.AUTO
            if message.message_type == MESSAGE_TYPE_MODE_TARGET:
                self._target_temperature = message.set_temperature
                self._local_target_temperature = self._target_temperature + self._local_offset
        elif message.message_type == MESSAGE_TYPE_ACTION:
            LOGGER.info("%s %s", self._gateway_handler.log_id, message.human_readable_log)
            if message.is_active():
                if self._heating and self._cooling:
                    if message.is_heating():
                        self._attr_hvac_action = HVACAction.HEATING
                    elif message.is_cooling():
                        self._attr_hvac_action = HVACAction.COOLING
                elif self._heating:
                    self._attr_hvac_action = HVACAction.HEATING
                elif self._cooling:
                    self._attr_hvac_action = HVACAction.COOLING
            elif self._attr_hvac_mode == HVACMode.OFF:
                self._attr_hvac_action = HVACAction.OFF
            else:
                self._attr_hvac_action = HVACAction.IDLE

        self._sync_from_thermo()
        self.async_schedule_update_ha_state()
