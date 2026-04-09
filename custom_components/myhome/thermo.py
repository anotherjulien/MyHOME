"""Helpers for extended MyHOME thermoregulation support."""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime as dt
import re
from typing import Any

EVENT_THERMO = "myhome_thermo_event"

SERVICE_THERMO_ZONE_COMMAND = "thermo_zone_command"
SERVICE_THERMO_CENTRAL_COMMAND = "thermo_central_command"
SERVICE_THERMO_REQUEST = "thermo_request"
SERVICE_THERMO_SPLIT_SET = "thermo_split_set"

ATTR_OPERATION = "operation"
ATTR_REQUEST = "request"
ATTR_ZONE = "zone"
ATTR_WHERE = "where"
ATTR_MODE_FAMILY = "mode_family"
ATTR_TEMPERATURE = "temperature"
ATTR_PROGRAM = "program"
ATTR_SCENARIO = "scenario"
ATTR_DAYS = "days"
ATTR_DATE = "date"
ATTR_TIME = "time"
ATTR_FAN_MODE = "fan_mode"
ATTR_SWING_MODE = "swing_mode"
ATTR_ACTUATOR = "actuator"

MODE_FAMILY_HEAT = "heat"
MODE_FAMILY_COOL = "cool"
MODE_FAMILY_GENERIC = "generic"

PRESET_ANTIFREEZE = "antifreeze"
PRESET_THERMAL_PROTECTION = "thermal_protection"
PRESET_GENERIC_PROTECTION = "generic_protection"

OPERATING_MODE_MANUAL = "manual"
OPERATING_MODE_AUTO = "auto"
OPERATING_MODE_OFF = "off"
OPERATING_MODE_PROGRAM = "program"
OPERATING_MODE_SCENARIO = "scenario"
OPERATING_MODE_HOLIDAY_DAILY = "holiday_daily"
OPERATING_MODE_HOLIDAY_DAYS = "holiday_days"

ZONE_REQUESTS = {
    "zone_status",
    "zone_temperature",
    "zone_fan_speed",
    "zone_complete_status",
    "zone_local_offset",
    "zone_setpoint",
    "zone_valves",
    "zone_actuator",
}

CENTRAL_REQUESTS = {
    "central_mode",
    "holiday_end_date",
    "holiday_end_time",
}

DIAGNOSTIC_REQUESTS = {
    "diag_central",
    "diag_central_autodiagnostic",
    "diag_failure_zones",
    "diag_zone",
    "diag_all_zones",
    "diag_zone_autodiagnostic",
    "diag_failure_counts",
}

SPLIT_REQUESTS = {"split_control"}

ZONE_MAIN_RE = re.compile(r"^\*4\*(?P<what>[^*]+)\*(?P<where>[^*]+)##$")
ZONE_DIM_RE = re.compile(
    r"^\*#4\*(?P<where>[^*]+)\*(?P<dimension>\d+)(?:\*(?P<values>.*?))?##$"
)
ZONE_WRITE_RE = re.compile(
    r"^\*#4\*(?P<where>[^*]+)\*\#(?P<dimension>\d+)\*(?P<values>.*)##$"
)
DIAG_RE = re.compile(
    r"^\*#1004\*(?P<where>[^*]+)\*(?P<dimension>\d+)(?:\*(?P<values>.*?))?##$"
)


def _zone_number(where: str | None) -> int | None:
    if where is None:
        return None
    if where.startswith("#0#"):
        where = where.split("#")[-1]
    elif where.startswith("#"):
        where = where[1:]
    if where.isdigit():
        return int(where)
    return None


def _is_split_where(where: str | None) -> bool:
    return bool(where and where.startswith("3#"))


def _split_where(where: str | int | None) -> str | None:
    if where is None:
        return None
    where = str(where).strip()
    if _is_split_where(where):
        return where
    return None


def _temperature_from_code(code: str | None) -> float | None:
    if code is None:
        return None
    code = str(code).strip()
    if not code or not re.fullmatch(r"\d{3,4}", code):
        return None
    return int(code) / 10.0


def _temperature_to_code(
    temperature: float, minimum: float = 5.0, maximum: float = 40.0
) -> str:
    temperature = round(float(temperature) * 2) / 2
    temperature = min(maximum, max(minimum, temperature))
    return f"{int(round(temperature * 10)):04d}"


def _split_temperature_to_code(temperature: float) -> str:
    temperature = round(float(temperature) * 2) / 2
    temperature = min(127.0, max(0.0, temperature))
    return f"{int(round(temperature * 10)):03d}"


def _mode_family_for_code(code: int) -> str | None:
    if code in {1, 102, 103, 110, 111, 115} or 1101 <= code <= 1216 or 13000 <= code <= 13255:
        return MODE_FAMILY_HEAT
    if code in {0, 2, 202, 203, 210, 211, 215} or 2101 <= code <= 2216 or 23000 <= code <= 23255:
        return MODE_FAMILY_COOL
    if code in {3, 20, 21, 22, 23, 24, 30, 31, 302, 303, 310, 311, 315, 3000} or 3100 <= code <= 3216 or 33000 <= code <= 33255:
        return MODE_FAMILY_GENERIC
    return None


def _fan_mode_from_code(code: int | None) -> str | None:
    if code is None:
        return None
    return {
        0: "auto",
        1: "low",
        2: "medium",
        3: "high",
        4: "silent",
    }.get(code, "off")


def _valve_state(value: str) -> str:
    return {
        "0": "off",
        "1": "on",
        "2": "opened",
        "3": "closed",
        "4": "stopped",
        "5": "fan_auto",
        "6": "fan_low",
        "7": "fan_medium",
        "8": "fan_high",
    }.get(str(value), f"unknown_{value}")


def _decode_zone_diagnostics(bits: str) -> dict[str, bool | str]:
    return {
        "bits": bits,
        "probe_not_answering": len(bits) >= 11 and bits[10] == "0",
        "pump_not_answering": len(bits) >= 12 and bits[11] == "0",
        "eeprom_failure": len(bits) >= 13 and bits[12] == "0",
        "temperature_out_of_range": len(bits) >= 14 and bits[13] == "0",
        "slave_probe_not_answering": len(bits) >= 15 and bits[14] == "0",
        "actuator_not_answering": len(bits) >= 16 and bits[15] == "0",
    }


def _decode_central_diagnostics(bits: str) -> dict[str, bool | str]:
    return {
        "bits": bits,
        "probe_not_answering": len(bits) >= 11 and bits[10] == "0",
        "pump_not_answering": len(bits) >= 12 and bits[11] == "0",
        "battery_ko": len(bits) >= 15 and bits[14] == "0",
        "eeprom_failure": len(bits) >= 16 and bits[15] == "0",
        "generic_trouble": len(bits) >= 21 and bits[20] == "0",
        "configuration_trouble": len(bits) >= 22 and bits[21] == "0",
        "hardware_failure": len(bits) >= 23 and bits[22] == "0",
        "busy": len(bits) >= 24 and bits[23] == "0",
    }


def _where_for_zone_request(where: str | None) -> str:
    if where is None:
        raise ValueError("A thermo `where` value is required.")
    if where.startswith("#0#"):
        return f"#{_zone_number(where)}"
    return where


def _where_for_zone_actuator(where: str | None, actuator: int | str | None = None) -> str:
    zone = _zone_number(where)
    if zone is None:
        raise ValueError("A valid thermo zone `where` value is required.")

    if actuator is None:
        return f"{zone}#0"

    actuator = int(actuator)
    if actuator < 0 or actuator > 9:
        raise ValueError("`actuator` must be between 0 and 9.")
    return f"{zone}#{actuator}"


@dataclass
class ZoneThermoState:
    """Runtime state for a thermoregulation zone."""

    zone: int
    last_where: str | None = None
    mode_code: int | None = None
    mode_family: str | None = None
    operating_mode: str | None = None
    preset_mode: str | None = None
    target_temperature: float | None = None
    local_target_temperature: float | None = None
    local_offset: float | None = None
    current_temperature: float | None = None
    current_humidity: float | None = None
    fan_speed_code: int | None = None
    fan_mode: str | None = None
    program: int | None = None
    scenario: int | None = None
    holiday_days: int | None = None
    holiday_return_program: int | None = None
    remote_control_enabled: bool | None = None
    cooling_valve_status: str | None = None
    heating_valve_status: str | None = None
    actuator_statuses: dict[str, str] = field(default_factory=dict)
    diagnostics_bits: str | None = None
    diagnostics: dict[str, bool | str] = field(default_factory=dict)
    autodiagnostic_bits: str | None = None
    autodiagnostic: dict[str, bool | str] = field(default_factory=dict)
    last_message: str | None = None

    def to_attributes(self) -> dict[str, Any]:
        return {
            "zone": self.zone,
            "zone_where": self.last_where,
            "mode_code": self.mode_code,
            "mode_family": self.mode_family,
            "operating_mode": self.operating_mode,
            "preset_mode": self.preset_mode,
            "fan_mode_raw": self.fan_mode,
            "fan_speed_code": self.fan_speed_code,
            "program": self.program,
            "scenario": self.scenario,
            "holiday_days": self.holiday_days,
            "holiday_return_program": self.holiday_return_program,
            "remote_control_enabled": self.remote_control_enabled,
            "cooling_valve_status": self.cooling_valve_status,
            "heating_valve_status": self.heating_valve_status,
            "actuator_statuses": dict(self.actuator_statuses),
            "diagnostics_bits": self.diagnostics_bits,
            "diagnostics": dict(self.diagnostics),
            "autodiagnostic_bits": self.autodiagnostic_bits,
            "autodiagnostic": dict(self.autodiagnostic),
        }


@dataclass
class CentralThermoState:
    """Runtime state for the central thermoregulation unit."""

    mode_code: int | None = None
    mode_family: str | None = None
    operating_mode: str | None = None
    preset_mode: str | None = None
    target_temperature: float | None = None
    program: int | None = None
    scenario: int | None = None
    holiday_days: int | None = None
    holiday_return_program: int | None = None
    holiday_deadline_date: str | None = None
    holiday_deadline_time: str | None = None
    remote_control_enabled: bool | None = None
    any_probe_off: bool | None = None
    any_probe_in_antifreeze: bool | None = None
    any_probe_in_manual: bool | None = None
    failure_discovered: bool | None = None
    battery_ko: bool | None = None
    diagnostics_bits: str | None = None
    diagnostics: dict[str, bool | str] = field(default_factory=dict)
    autodiagnostic_bits: str | None = None
    autodiagnostic: dict[str, bool | str] = field(default_factory=dict)
    failure_zone_count: int | None = None
    not_answer_zone_count: int | None = None
    last_message: str | None = None

    def to_attributes(self) -> dict[str, Any]:
        return {
            "central_where": "#0",
            "central_mode_code": self.mode_code,
            "central_mode_family": self.mode_family,
            "central_operating_mode": self.operating_mode,
            "central_preset_mode": self.preset_mode,
            "central_program": self.program,
            "central_scenario": self.scenario,
            "central_holiday_days": self.holiday_days,
            "central_holiday_return_program": self.holiday_return_program,
            "central_holiday_deadline_date": self.holiday_deadline_date,
            "central_holiday_deadline_time": self.holiday_deadline_time,
            "central_remote_control_enabled": self.remote_control_enabled,
            "central_any_probe_off": self.any_probe_off,
            "central_any_probe_in_antifreeze": self.any_probe_in_antifreeze,
            "central_any_probe_in_manual": self.any_probe_in_manual,
            "central_failure_discovered": self.failure_discovered,
            "central_battery_ko": self.battery_ko,
            "central_diagnostics_bits": self.diagnostics_bits,
            "central_diagnostics": dict(self.diagnostics),
            "central_autodiagnostic_bits": self.autodiagnostic_bits,
            "central_autodiagnostic": dict(self.autodiagnostic),
            "central_failure_zone_count": self.failure_zone_count,
            "central_not_answer_zone_count": self.not_answer_zone_count,
        }


@dataclass
class SplitThermoState:
    """Runtime state for a split control actuator."""

    where: str
    mode_code: int | None = None
    mode: str | None = None
    target_temperature: float | None = None
    fan_speed_code: int | None = None
    fan_mode: str | None = None
    swing_code: int | None = None
    swing_mode: str | None = None
    last_message: str | None = None

    def to_attributes(self) -> dict[str, Any]:
        return {
            "split_where": self.where,
            "split_mode_code": self.mode_code,
            "split_mode": self.mode,
            "split_fan_speed_code": self.fan_speed_code,
            "split_fan_mode_raw": self.fan_mode,
            "split_swing_code": self.swing_code,
            "split_swing_mode_raw": self.swing_mode,
        }


class MyHOMEThermoState:
    """Keep an extended view of WHO=4/1004 state."""

    def __init__(self) -> None:
        self.central = CentralThermoState()
        self.zones: dict[int, ZoneThermoState] = {}
        self.splits: dict[str, SplitThermoState] = {}

    def get_zone(self, where: str | None) -> ZoneThermoState | None:
        zone = _zone_number(where)
        if zone is None:
            return None
        return self.zones.get(zone)

    def get_or_create_zone(self, where: str) -> ZoneThermoState:
        zone = _zone_number(where)
        if zone is None:
            raise ValueError(f"Invalid thermoregulation zone `{where}`.")
        state = self.zones.setdefault(zone, ZoneThermoState(zone=zone))
        state.last_where = where
        return state

    def get_split(self, where: str | None) -> SplitThermoState | None:
        where = _split_where(where)
        if where is None:
            return None
        return self.splits.get(where)

    def get_or_create_split(self, where: str) -> SplitThermoState:
        normalized = _split_where(where)
        if normalized is None:
            raise ValueError(f"Invalid split where `{where}`.")
        return self.splits.setdefault(normalized, SplitThermoState(where=normalized))

    def handle_message(self, raw_message: str) -> dict[str, Any] | None:
        raw_message = raw_message.strip()
        for handler in (
            self._handle_diag_message,
            self._handle_dimension_message,
            self._handle_main_message,
        ):
            result = handler(raw_message)
            if result is not None:
                result["raw_message"] = raw_message
                return result
        return None

    def _handle_main_message(self, raw_message: str) -> dict[str, Any] | None:
        match = ZONE_MAIN_RE.match(raw_message)
        if match is None:
            return None

        where = match.group("where")
        what = match.group("what")
        parts = what.split("#")
        if not parts[0].isdigit():
            return None

        code = int(parts[0])
        parameter = parts[1] if len(parts) > 1 else None

        if where == "#0":
            self._update_central_mode(code, parameter, raw_message)
            return {"scope": "central", "where": where}

        if _is_split_where(where):
            return None

        zone = self.get_or_create_zone(where)
        self._update_zone_mode(zone, code, parameter, raw_message)
        return {"scope": "zone", "where": where, "zone": zone.zone}

    def _handle_dimension_message(self, raw_message: str) -> dict[str, Any] | None:
        match = ZONE_DIM_RE.match(raw_message)
        if match is None:
            match = ZONE_WRITE_RE.match(raw_message)
        if match is None:
            return None

        where = match.group("where")
        dimension = int(match.group("dimension"))
        values = (
            (match.group("values") or "").split("*")
            if match.group("values") is not None
            else []
        )

        if _is_split_where(where) and dimension == 22:
            split = self.get_or_create_split(where)
            self._update_split(split, values, raw_message)
            return {"scope": "split", "where": where}

        if where == "#0" and dimension in {30, 31}:
            self._update_holiday_deadline(dimension, values, raw_message)
            return {"scope": "central", "where": where}

        zone = self.get_zone(where)
        if zone is None and where != "#0":
            try:
                zone = self.get_or_create_zone(where)
            except ValueError:
                zone = None

        if zone is None:
            return None

        if dimension == 0 and values:
            zone.current_temperature = _temperature_from_code(values[0])
        elif dimension == 11 and values and values[0].isdigit():
            zone.fan_speed_code = int(values[0])
            zone.fan_mode = _fan_mode_from_code(zone.fan_speed_code)
        elif dimension == 12 and values:
            zone.local_target_temperature = _temperature_from_code(values[0])
            if len(values) > 1 and values[1].isdigit():
                self._update_zone_mode(zone, int(values[1]), None, raw_message)
        elif dimension == 13 and values:
            zone.local_offset = self._parse_local_offset(values[0])
        elif dimension == 14 and values:
            zone.target_temperature = _temperature_from_code(values[0])
            if len(values) > 1 and values[1].isdigit():
                self._update_zone_mode(zone, int(values[1]), None, raw_message)
        elif dimension == 19 and len(values) >= 2:
            zone.cooling_valve_status = _valve_state(values[0])
            zone.heating_valve_status = _valve_state(values[1])
        elif dimension == 20 and values:
            actuator_key = where.split("#", 1)[1] if "#" in where else where
            zone.actuator_statuses[actuator_key] = _valve_state(values[0])
        elif dimension == 60 and values:
            try:
                zone.current_humidity = float(values[0])
            except ValueError:
                zone.current_humidity = None
        else:
            return None

        zone.last_message = raw_message
        return {"scope": "zone", "where": where, "zone": zone.zone}

    def _handle_diag_message(self, raw_message: str) -> dict[str, Any] | None:
        match = DIAG_RE.match(raw_message)
        if match is None:
            return None

        where = match.group("where")
        dimension = int(match.group("dimension"))
        values = (
            (match.group("values") or "").split("*")
            if match.group("values") is not None
            else []
        )

        if where == "#0":
            if dimension == 7 and values:
                self.central.diagnostics_bits = values[0]
                self.central.diagnostics = _decode_central_diagnostics(values[0])
            elif dimension == 11 and values:
                self.central.autodiagnostic_bits = values[0]
                self.central.autodiagnostic = _decode_central_diagnostics(values[0])
            elif dimension == 23 and len(values) >= 2:
                self.central.not_answer_zone_count = int(values[0])
                self.central.failure_zone_count = int(values[1])
            else:
                return None

            self.central.last_message = raw_message
            return {"scope": "central", "where": where}

        zone = self.get_or_create_zone(where)
        if dimension == 21 and values:
            zone.diagnostics_bits = values[0]
            zone.diagnostics = _decode_zone_diagnostics(values[0])
        elif dimension == 22 and values:
            zone.autodiagnostic_bits = values[0]
            zone.autodiagnostic = _decode_zone_diagnostics(values[0])
        else:
            return None

        zone.last_message = raw_message
        return {"scope": "zone", "where": where, "zone": zone.zone}

    def _update_zone_mode(
        self,
        zone: ZoneThermoState,
        code: int,
        parameter: str | None,
        raw_message: str,
    ) -> None:
        zone.mode_code = code
        zone.mode_family = _mode_family_for_code(code)
        zone.last_message = raw_message
        zone.preset_mode = None
        zone.program = None
        zone.scenario = None
        zone.holiday_days = None
        zone.holiday_return_program = None

        if parameter and parameter.isdigit() and len(parameter) >= 4:
            target = _temperature_from_code(parameter)
            if target is not None:
                zone.target_temperature = target

        if code in {102, 202, 302}:
            zone.operating_mode = OPERATING_MODE_OFF
            zone.preset_mode = {
                102: PRESET_ANTIFREEZE,
                202: PRESET_THERMAL_PROTECTION,
                302: PRESET_GENERIC_PROTECTION,
            }[code]
        elif code in {103, 203, 303}:
            zone.operating_mode = OPERATING_MODE_OFF
        elif code in {0, 1, 2, 3, 110, 210, 310}:
            zone.operating_mode = OPERATING_MODE_MANUAL
        elif code in {111, 211, 311}:
            zone.operating_mode = OPERATING_MODE_AUTO
        elif code in {115, 215, 315}:
            zone.operating_mode = OPERATING_MODE_HOLIDAY_DAILY
            if parameter and parameter.isdigit():
                zone.holiday_return_program = int(parameter[-1])
        elif 1101 <= code <= 1103:
            zone.operating_mode = OPERATING_MODE_PROGRAM
            zone.program = code - 1100
        elif 2101 <= code <= 2103:
            zone.operating_mode = OPERATING_MODE_PROGRAM
            zone.program = code - 2100
        elif 3101 <= code <= 3103:
            zone.operating_mode = OPERATING_MODE_PROGRAM
            zone.program = code - 3100
        elif 1201 <= code <= 1216:
            zone.operating_mode = OPERATING_MODE_SCENARIO
            zone.scenario = code - 1200
        elif 2201 <= code <= 2216:
            zone.operating_mode = OPERATING_MODE_SCENARIO
            zone.scenario = code - 2200
        elif 3201 <= code <= 3216:
            zone.operating_mode = OPERATING_MODE_SCENARIO
            zone.scenario = code - 3200
        elif 13000 <= code <= 13255:
            zone.operating_mode = OPERATING_MODE_HOLIDAY_DAYS
            zone.holiday_days = code - 13000
        elif 23000 <= code <= 23255:
            zone.operating_mode = OPERATING_MODE_HOLIDAY_DAYS
            zone.holiday_days = code - 23000
        elif 33000 <= code <= 33255:
            zone.operating_mode = OPERATING_MODE_HOLIDAY_DAYS
            zone.holiday_days = code - 33000
        elif code == 20:
            zone.remote_control_enabled = False
        elif code == 21:
            zone.remote_control_enabled = True

    def _update_central_mode(
        self, code: int, parameter: str | None, raw_message: str
    ) -> None:
        central = self.central
        central.mode_code = code
        central.mode_family = _mode_family_for_code(code)
        central.last_message = raw_message
        central.preset_mode = None
        central.program = None
        central.scenario = None
        central.holiday_days = None
        central.holiday_return_program = None

        if parameter and parameter.isdigit() and len(parameter) >= 4:
            target = _temperature_from_code(parameter)
            if target is not None:
                central.target_temperature = target

        if code == 20:
            central.remote_control_enabled = False
            return
        if code == 21:
            central.remote_control_enabled = True
            return
        if code == 22:
            central.any_probe_off = True
            return
        if code == 23:
            central.any_probe_in_antifreeze = True
            return
        if code == 24:
            central.any_probe_in_manual = True
            return
        if code == 30:
            central.failure_discovered = True
            return
        if code == 31:
            central.battery_ko = True
            return

        if code in {102, 202, 302}:
            central.operating_mode = OPERATING_MODE_OFF
            central.preset_mode = {
                102: PRESET_ANTIFREEZE,
                202: PRESET_THERMAL_PROTECTION,
                302: PRESET_GENERIC_PROTECTION,
            }[code]
        elif code in {103, 203, 303}:
            central.operating_mode = OPERATING_MODE_OFF
        elif code in {110, 210, 310}:
            central.operating_mode = OPERATING_MODE_MANUAL
        elif code in {111, 211, 311, 3000}:
            central.operating_mode = OPERATING_MODE_AUTO
        elif code in {115, 215, 315}:
            central.operating_mode = OPERATING_MODE_HOLIDAY_DAILY
        elif 1101 <= code <= 1103:
            central.operating_mode = OPERATING_MODE_PROGRAM
            central.program = code - 1100
        elif 2101 <= code <= 2103:
            central.operating_mode = OPERATING_MODE_PROGRAM
            central.program = code - 2100
        elif 3101 <= code <= 3103:
            central.operating_mode = OPERATING_MODE_PROGRAM
            central.program = code - 3100
        elif 1201 <= code <= 1216:
            central.operating_mode = OPERATING_MODE_SCENARIO
            central.scenario = code - 1200
        elif 2201 <= code <= 2216:
            central.operating_mode = OPERATING_MODE_SCENARIO
            central.scenario = code - 2200
        elif 3201 <= code <= 3216:
            central.operating_mode = OPERATING_MODE_SCENARIO
            central.scenario = code - 3200
        elif 13000 <= code <= 13255:
            central.operating_mode = OPERATING_MODE_HOLIDAY_DAYS
            central.holiday_days = code - 13000
        elif 23000 <= code <= 23255:
            central.operating_mode = OPERATING_MODE_HOLIDAY_DAYS
            central.holiday_days = code - 23000
        elif 33000 <= code <= 33255:
            central.operating_mode = OPERATING_MODE_HOLIDAY_DAYS
            central.holiday_days = code - 33000

        if parameter and parameter.isdigit():
            if code in {115, 215}:
                central.holiday_return_program = int(parameter)
            elif code in {315, 3000}:
                central.holiday_return_program = int(parameter[-1])

    def _update_holiday_deadline(
        self, dimension: int, values: list[str], raw_message: str
    ) -> None:
        self.central.last_message = raw_message
        if dimension == 30 and len(values) >= 3:
            self.central.holiday_deadline_date = (
                f"{int(values[2]):04d}-{int(values[1]):02d}-{int(values[0]):02d}"
            )
        elif dimension == 31 and len(values) >= 2:
            self.central.holiday_deadline_time = (
                f"{int(values[0]):02d}:{int(values[1]):02d}"
            )

    def _update_split(
        self, split: SplitThermoState, values: list[str], raw_message: str
    ) -> None:
        split.last_message = raw_message
        if len(values) >= 1 and values[0].isdigit():
            split.mode_code = int(values[0])
            split.mode = {
                11: "winter",
                12: "summer",
                13: "auto",
                14: "off",
                15: "fan_only",
                16: "dehumidification",
            }.get(split.mode_code, "unknown")
        if len(values) >= 2 and values[1].isdigit():
            split.target_temperature = _temperature_from_code(values[1])
        if len(values) >= 3 and values[2].isdigit():
            split.fan_speed_code = int(values[2])
            split.fan_mode = _fan_mode_from_code(split.fan_speed_code)
        if len(values) >= 4 and values[3].isdigit():
            split.swing_code = int(values[3])
            split.swing_mode = "on" if split.swing_code == 1 else "off"

    @staticmethod
    def _parse_local_offset(value: str) -> float | None:
        if value in {"0", "00", "4", "5"}:
            return 0.0
        if len(value) == 2 and value[0] == "0":
            return float(value[1])
        if len(value) == 2 and value[0] == "1":
            return -float(value[1])
        return None


def build_zone_command(
    where: str,
    operation: str,
    *,
    temperature: float | None = None,
    mode_family: str | None = None,
) -> str:
    operation = operation.lower()
    mode_family = (mode_family or MODE_FAMILY_GENERIC).lower()

    if operation == "manual":
        if temperature is None:
            raise ValueError("`temperature` is required for manual zone commands.")
        mode_code = {
            MODE_FAMILY_HEAT: "1",
            MODE_FAMILY_COOL: "2",
            MODE_FAMILY_GENERIC: "3",
        }.get(mode_family, "3")
        return (
            f"*#4*{where}*#14*{_temperature_to_code(temperature)}*{mode_code}##"
        )

    if operation == "auto":
        what = {
            MODE_FAMILY_HEAT: 111,
            MODE_FAMILY_COOL: 211,
            MODE_FAMILY_GENERIC: 311,
        }.get(mode_family, 311)
        return f"*4*{what}*{where}##"

    if operation == "off":
        what = {
            MODE_FAMILY_HEAT: 103,
            MODE_FAMILY_COOL: 203,
            MODE_FAMILY_GENERIC: 303,
        }.get(mode_family, 303)
        return f"*4*{what}*{where}##"

    if operation == PRESET_ANTIFREEZE:
        return f"*4*102*{where}##"
    if operation == PRESET_THERMAL_PROTECTION:
        return f"*4*202*{where}##"
    if operation == PRESET_GENERIC_PROTECTION:
        return f"*4*302*{where}##"
    if operation == "release_local_adjustment":
        return f"*4*40*{where}##"

    raise ValueError(f"Unsupported zone operation `{operation}`.")


def build_central_command(
    operation: str,
    *,
    temperature: float | None = None,
    mode_family: str | None = None,
    program: int | None = None,
    scenario: int | None = None,
    days: int | None = None,
    date_value: dt.date | str | None = None,
    time_value: dt.time | str | None = None,
) -> str:
    operation = operation.lower()
    mode_family = (mode_family or MODE_FAMILY_GENERIC).lower()

    if operation == "manual":
        if temperature is None:
            raise ValueError("`temperature` is required for central manual mode.")
        what = {
            MODE_FAMILY_HEAT: 110,
            MODE_FAMILY_COOL: 210,
            MODE_FAMILY_GENERIC: 310,
        }.get(mode_family, 310)
        return f"*4*{what}#{_temperature_to_code(temperature)}*#0##"

    if operation == "off":
        what = {
            MODE_FAMILY_HEAT: 103,
            MODE_FAMILY_COOL: 203,
            MODE_FAMILY_GENERIC: 303,
        }.get(mode_family, 303)
        return f"*4*{what}*#0##"

    if operation == PRESET_ANTIFREEZE:
        return "*4*102*#0##"
    if operation == PRESET_THERMAL_PROTECTION:
        return "*4*202*#0##"
    if operation == PRESET_GENERIC_PROTECTION:
        return "*4*302*#0##"

    if operation == "program":
        if program is None or int(program) < 1 or int(program) > 3:
            raise ValueError("`program` must be between 1 and 3.")
        base = {
            MODE_FAMILY_HEAT: 1100,
            MODE_FAMILY_COOL: 2100,
            MODE_FAMILY_GENERIC: 3100,
        }.get(mode_family, 3100)
        return f"*4*{base + int(program)}*#0##"

    if operation == "last_program":
        return "*4*3100*#0##"

    if operation == "scenario":
        if scenario is None or int(scenario) < 1 or int(scenario) > 16:
            raise ValueError("`scenario` must be between 1 and 16.")
        base = {
            MODE_FAMILY_HEAT: 1200,
            MODE_FAMILY_COOL: 2200,
            MODE_FAMILY_GENERIC: 3200,
        }.get(mode_family, 3200)
        return f"*4*{base + int(scenario)}*#0##"

    if operation == "last_scenario":
        return "*4*3200*#0##"

    if operation == "holiday_daily":
        if program is None or int(program) < 1 or int(program) > 3:
            raise ValueError("`program` must be between 1 and 3.")
        if mode_family == MODE_FAMILY_HEAT:
            return f"*4*115#{int(program)}*#0##"
        if mode_family == MODE_FAMILY_COOL:
            return f"*4*215#{int(program)}*#0##"
        return f"*4*315#31{int(program):02d}*#0##"

    if operation == "holiday_days":
        if days is None or int(days) < 0 or int(days) > 255:
            raise ValueError("`days` must be between 0 and 255.")
        if program is None or int(program) < 1 or int(program) > 3:
            raise ValueError("`program` must be between 1 and 3.")
        base = {
            MODE_FAMILY_HEAT: 13000,
            MODE_FAMILY_COOL: 23000,
            MODE_FAMILY_GENERIC: 33000,
        }.get(mode_family, 33000)
        return f"*4*{base + int(days)}#31{int(program):02d}*#0##"

    if operation == "disable_holiday":
        if program is None:
            return "*4*3000*#0##"
        if int(program) < 1 or int(program) > 3:
            raise ValueError("`program` must be between 1 and 3.")
        return f"*4*3000#31{int(program):02d}*#0##"

    if operation == "disable_holiday_program":
        if program is None:
            raise ValueError("`program` is required.")
        if int(program) < 1 or int(program) > 3:
            raise ValueError("`program` must be between 1 and 3.")
        return f"*4*3000#31{int(program):02d}*#0##"

    if operation == "disable_holiday_last_program":
        return "*4*3000*#0##"

    if operation == "set_holiday_date":
        if isinstance(date_value, str):
            date_value = dt.date.fromisoformat(date_value)
        if not isinstance(date_value, dt.date):
            raise ValueError("`date` must be an ISO date string or date object.")
        return (
            f"*#4*#0*#30*{date_value.day:02d}*{date_value.month:02d}"
            f"*{date_value.year:04d}##"
        )

    if operation == "set_holiday_time":
        if isinstance(time_value, str):
            time_value = dt.time.fromisoformat(time_value)
        if not isinstance(time_value, dt.time):
            raise ValueError("`time` must be an ISO time string or time object.")
        return f"*#4*#0*#31*{time_value.hour:02d}*{time_value.minute:02d}##"

    raise ValueError(f"Unsupported central operation `{operation}`.")


def build_request(
    request: str,
    *,
    where: str | None = None,
    actuator: int | str | None = None,
) -> str:
    request = request.lower()
    if where is None and request in {
        "zone_status",
        "zone_temperature",
        "zone_fan_speed",
        "zone_complete_status",
        "zone_local_offset",
        "zone_setpoint",
        "zone_valves",
        "zone_actuator",
        "split_control",
    }:
        raise ValueError("A thermo `where` value is required.")
    zone_where = _where_for_zone_request(where) if where is not None else None

    if request == "zone_status":
        return f"*#4*{where}##"
    if request == "zone_temperature":
        return f"*#4*{where}*0##"
    if request == "zone_fan_speed":
        return f"*#4*{where}*11##"
    if request == "zone_complete_status":
        return f"*#4*{where}*12##"
    if request == "zone_local_offset":
        return f"*#4*{where}*13##"
    if request == "zone_setpoint":
        return f"*#4*{where}*14##"
    if request == "zone_valves":
        return f"*#4*{where}*19##"
    if request == "zone_actuator":
        return f"*#4*{_where_for_zone_actuator(where, actuator)}*20##"
    if request == "central_mode":
        return "*#4*#0##"
    if request == "holiday_end_date":
        return "*#4*#0*30##"
    if request == "holiday_end_time":
        return "*#4*#0*31##"
    if request == "split_control":
        if where is None:
            raise ValueError("A split `where` value is required.")
        return f"*#4*{where}*22##"
    if request == "diag_central":
        return "*#1004*#0*7##"
    if request == "diag_central_autodiagnostic":
        return "*#1004*#0*11##"
    if request == "diag_failure_zones":
        return "*#1004*#0*20##"
    if request == "diag_zone":
        return f"*#1004*{zone_where}*21##"
    if request == "diag_all_zones":
        return "*#1004*#0*21##"
    if request == "diag_zone_autodiagnostic":
        return f"*#1004*{zone_where}*22##"
    if request == "diag_failure_counts":
        return "*#1004*#0*23##"

    raise ValueError(f"Unsupported thermo request `{request}`.")


def build_split_set_command(
    where: str,
    *,
    mode: str | None = None,
    temperature: float | None = None,
    fan_mode: str | None = None,
    swing_mode: str | None = None,
) -> str:
    normalized = _split_where(where)
    if normalized is None:
        raise ValueError("Invalid split `where`.")

    mode_code = ""
    if mode is not None:
        mode_code = {
            "heat": "11",
            "winter": "11",
            "cool": "12",
            "summer": "12",
            "auto": "13",
            "off": "14",
            "fan_only": "15",
            "fan": "15",
            "dry": "16",
            "dehumidification": "16",
        }.get(str(mode).lower())
        if mode_code is None:
            raise ValueError(f"Unsupported split mode `{mode}`.")

    setpoint_code = ""
    if temperature is not None:
        setpoint_code = _split_temperature_to_code(temperature)

    fan_code = ""
    if fan_mode is not None:
        fan_code = {
            "auto": "0",
            "low": "1",
            "medium": "2",
            "high": "3",
            "silent": "4",
            "off": "",
        }.get(str(fan_mode).lower())
        if fan_code is None:
            raise ValueError(f"Unsupported split fan mode `{fan_mode}`.")

    swing_code = ""
    if swing_mode is not None:
        swing_code = {
            "off": "0",
            "on": "1",
        }.get(str(swing_mode).lower())
        if swing_code is None:
            raise ValueError(f"Unsupported split swing mode `{swing_mode}`.")

    return (
        f"*#4*{normalized}*#22*{mode_code}*{setpoint_code}*{fan_code}"
        f"*{swing_code}##"
    )
