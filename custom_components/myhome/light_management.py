"""Helpers and state cache for MyHOME WHO=24 lighting management."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re

ATTR_ENABLED = "enabled"
ATTR_ERROR = "error"
ATTR_EXIT_CONDITION = "exit_condition"
ATTR_HOURS = "hours"
ATTR_LUX = "lux"
ATTR_MINUTES = "minutes"
ATTR_MODE = "mode"
ATTR_OPERATION = "operation"
ATTR_PROFILE = "profile"
ATTR_QUERY_AFTER = "query_after"
ATTR_REQUEST = "request"
ATTR_SECONDS = "seconds"
ATTR_SENSOR_ADDRESS = "sensor_address"
ATTR_VALUE = "value"
ATTR_WHERE = "where"

EVENT_LIGHT_MANAGEMENT = "myhome_light_management_event"
SERVICE_LIGHT_MANAGEMENT_COMMAND = "light_management_command"
SERVICE_LIGHT_MANAGEMENT_REQUEST = "light_management_request"

REQUEST_SWITCH_ON_VALUE = "switch_on_value"
REQUEST_MAX_LUX = "max_lux"
REQUEST_MAINTAINED_LUX = "maintained_lux"
REQUEST_AUTO_SWITCH_ON = "auto_switch_on"
REQUEST_SWITCH_ON_DELAY = "switch_on_delay"
REQUEST_AUTO_SWITCH_OFF = "auto_switch_off"
REQUEST_SWITCH_OFF_DELAY = "switch_off_delay"
REQUEST_DELAY_TIMER = "delay_timer"
REQUEST_STANDBY_TIMER = "standby_timer"
REQUEST_STANDBY_VALUE = "standby_value"
REQUEST_OFF_VALUE = "off_value"
REQUEST_SLAVE_OFFSET = "slave_offset"
REQUEST_STATE = "state"
REQUEST_CENTRALIZED_LUX = "centralized_lux"
REQUEST_ALL = "all"

MODE_NAMES = {
    0: "stop",
    1: "automatic",
    2: "manual",
}
MODE_OPTIONS = [
    MODE_NAMES[0],
    MODE_NAMES[1],
    MODE_NAMES[2],
]
EXIT_CONDITION_NAMES = {
    1: "time",
    2: "for",
    3: "profile",
    4: "normal",
    5: "never",
}
EXIT_CONDITION_OPTIONS = [
    EXIT_CONDITION_NAMES[1],
    EXIT_CONDITION_NAMES[2],
    EXIT_CONDITION_NAMES[3],
    EXIT_CONDITION_NAMES[4],
    EXIT_CONDITION_NAMES[5],
]
CENTRALIZED_LUX_ERROR_NAMES = {
    0: "ok",
    1: "sensor_not_configured",
    2: "sensor_parameters_missing",
}

REQUEST_TO_DIMENSION = {
    REQUEST_SWITCH_ON_VALUE: 1,
    REQUEST_MAX_LUX: 2,
    REQUEST_MAINTAINED_LUX: 3,
    REQUEST_AUTO_SWITCH_ON: 4,
    REQUEST_SWITCH_ON_DELAY: 5,
    REQUEST_AUTO_SWITCH_OFF: 6,
    REQUEST_SWITCH_OFF_DELAY: 7,
    REQUEST_DELAY_TIMER: 8,
    REQUEST_STANDBY_TIMER: 9,
    REQUEST_STANDBY_VALUE: 10,
    REQUEST_OFF_VALUE: 11,
    REQUEST_SLAVE_OFFSET: 12,
    REQUEST_STATE: 17,
    REQUEST_CENTRALIZED_LUX: 18,
}
DIMENSION_TO_REQUEST = {
    dimension: request for request, dimension in REQUEST_TO_DIMENSION.items()
}
SCALAR_REQUESTS = {
    REQUEST_SWITCH_ON_VALUE,
    REQUEST_MAX_LUX,
    REQUEST_MAINTAINED_LUX,
    REQUEST_AUTO_SWITCH_ON,
    REQUEST_SWITCH_ON_DELAY,
    REQUEST_AUTO_SWITCH_OFF,
    REQUEST_SWITCH_OFF_DELAY,
    REQUEST_DELAY_TIMER,
    REQUEST_STANDBY_TIMER,
    REQUEST_STANDBY_VALUE,
    REQUEST_OFF_VALUE,
    REQUEST_SLAVE_OFFSET,
}
SUPPORTED_REQUESTS = set(REQUEST_TO_DIMENSION) | {REQUEST_ALL}

SCALAR_FIELD_MAP = {
    REQUEST_SWITCH_ON_VALUE: "switch_on_value",
    REQUEST_MAX_LUX: "max_lux",
    REQUEST_MAINTAINED_LUX: "maintained_lux",
    REQUEST_AUTO_SWITCH_ON: "auto_switch_on",
    REQUEST_SWITCH_ON_DELAY: "switch_on_delay",
    REQUEST_AUTO_SWITCH_OFF: "auto_switch_off",
    REQUEST_SWITCH_OFF_DELAY: "switch_off_delay",
    REQUEST_DELAY_TIMER: "delay_timer",
    REQUEST_STANDBY_TIMER: "standby_timer",
    REQUEST_STANDBY_VALUE: "standby_value",
    REQUEST_OFF_VALUE: "off_value",
    REQUEST_SLAVE_OFFSET: "slave_offset",
}
BOOLEAN_REQUESTS = {
    REQUEST_AUTO_SWITCH_ON,
    REQUEST_AUTO_SWITCH_OFF,
}
SWITCH_REQUESTS = tuple(sorted(BOOLEAN_REQUESTS))
SELECT_OPERATIONS = {
    "mode",
    "exit_condition",
}
NUMBER_REQUESTS = tuple(sorted(SCALAR_REQUESTS))
SCALAR_RANGES = {
    "set_switch_on_value": (1, 100),
    "set_max_lux": (1, 2000),
    "set_maintained_lux": (0, 2000),
    "set_auto_switch_on": (0, 1),
    "set_switch_on_delay": (0, 300),
    "set_auto_switch_off": (0, 1),
    "set_switch_off_delay": (0, 300),
    "set_delay_timer": (0, 3600),
    "set_standby_timer": (0, 900),
    "set_standby_value": (0, 100),
    "set_off_value": (0, 100),
    "set_slave_offset": (0, 100),
}
COMMAND_TO_REQUEST = {
    "set_switch_on_value": REQUEST_SWITCH_ON_VALUE,
    "set_max_lux": REQUEST_MAX_LUX,
    "set_maintained_lux": REQUEST_MAINTAINED_LUX,
    "set_auto_switch_on": REQUEST_AUTO_SWITCH_ON,
    "set_switch_on_delay": REQUEST_SWITCH_ON_DELAY,
    "set_auto_switch_off": REQUEST_AUTO_SWITCH_OFF,
    "set_switch_off_delay": REQUEST_SWITCH_OFF_DELAY,
    "set_delay_timer": REQUEST_DELAY_TIMER,
    "set_standby_timer": REQUEST_STANDBY_TIMER,
    "set_standby_value": REQUEST_STANDBY_VALUE,
    "set_off_value": REQUEST_OFF_VALUE,
    "set_slave_offset": REQUEST_SLAVE_OFFSET,
    "set_state": REQUEST_STATE,
    "set_centralized_lux": REQUEST_CENTRALIZED_LUX,
    "activate_profile": REQUEST_STATE,
}
NUMBER_ENTITY_DESCRIPTIONS = {
    REQUEST_SWITCH_ON_VALUE: {
        "name": "Switch-on value",
        "icon": "mdi:brightness-percent",
        "native_min_value": 1,
        "native_max_value": 100,
        "native_step": 1,
        "native_unit": "%",
    },
    REQUEST_MAX_LUX: {
        "name": "Max lux",
        "icon": "mdi:brightness-6",
        "native_min_value": 1,
        "native_max_value": 2000,
        "native_step": 1,
        "native_unit": "lx",
    },
    REQUEST_MAINTAINED_LUX: {
        "name": "Maintained lux",
        "icon": "mdi:brightness-5",
        "native_min_value": 0,
        "native_max_value": 2000,
        "native_step": 1,
        "native_unit": "lx",
    },
    REQUEST_SWITCH_ON_DELAY: {
        "name": "Switch-on delay",
        "icon": "mdi:timer-play-outline",
        "native_min_value": 0,
        "native_max_value": 300,
        "native_step": 1,
        "native_unit": "s",
    },
    REQUEST_SWITCH_OFF_DELAY: {
        "name": "Switch-off delay",
        "icon": "mdi:timer-stop-outline",
        "native_min_value": 0,
        "native_max_value": 300,
        "native_step": 1,
        "native_unit": "s",
    },
    REQUEST_DELAY_TIMER: {
        "name": "Delay timer",
        "icon": "mdi:timer-sand",
        "native_min_value": 0,
        "native_max_value": 3600,
        "native_step": 1,
        "native_unit": "s",
    },
    REQUEST_STANDBY_TIMER: {
        "name": "Standby timer",
        "icon": "mdi:sleep",
        "native_min_value": 0,
        "native_max_value": 900,
        "native_step": 1,
        "native_unit": "s",
    },
    REQUEST_STANDBY_VALUE: {
        "name": "Standby value",
        "icon": "mdi:brightness-4",
        "native_min_value": 0,
        "native_max_value": 100,
        "native_step": 1,
        "native_unit": "%",
    },
    REQUEST_OFF_VALUE: {
        "name": "Off value",
        "icon": "mdi:brightness-3",
        "native_min_value": 0,
        "native_max_value": 100,
        "native_step": 1,
        "native_unit": "%",
    },
    REQUEST_SLAVE_OFFSET: {
        "name": "Slave offset",
        "icon": "mdi:tune-variant",
        "native_min_value": 0,
        "native_max_value": 100,
        "native_step": 1,
        "native_unit": "%",
    },
}
SCALAR_OPERATION_TO_DIMENSION = {
    "set_switch_on_value": 1,
    "set_max_lux": 2,
    "set_maintained_lux": 3,
    "set_auto_switch_on": 4,
    "set_switch_on_delay": 5,
    "set_auto_switch_off": 6,
    "set_switch_off_delay": 7,
    "set_delay_timer": 8,
    "set_standby_timer": 9,
    "set_standby_value": 10,
    "set_off_value": 11,
    "set_slave_offset": 12,
}

LIGHT_MANAGEMENT_RESPONSE_RE = re.compile(
    r"^\*#24\*(?P<where>[^*]+)\*(?P<dimension>17|18|1[0-2]|[1-9])\*(?P<body>.+)##$"
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_where(where: str | int | None) -> str:
    if where is None:
        raise ValueError("Missing lighting management WHERE.")
    where = str(where).strip()
    if not where or "*" in where:
        raise ValueError("Invalid lighting management WHERE.")
    return where


def _normalize_int(
    value: int | str | float | None,
    name: str,
    minimum: int,
    maximum: int,
) -> int:
    if value is None:
        raise ValueError(f"Missing lighting management {name}.")
    value = int(round(float(value)))
    if value < minimum or value > maximum:
        raise ValueError(
            f"Invalid lighting management {name} {value}; expected {minimum}..{maximum}."
        )
    return value


def mode_option_from_code(code: int | None) -> str | None:
    if code is None:
        return None
    return MODE_NAMES.get(int(code), f"mode_{int(code)}")


def mode_code_from_option(option: str | None) -> int:
    if option is None:
        raise ValueError("Missing lighting management mode.")
    normalized = str(option).strip().lower()
    for code, label in MODE_NAMES.items():
        if label == normalized:
            return int(code)
    raise ValueError(f"Unsupported lighting management mode `{option}`.")


def exit_condition_option_from_code(code: int | None) -> str | None:
    if code is None:
        return None
    return EXIT_CONDITION_NAMES.get(int(code), f"exit_{int(code)}")


def exit_condition_code_from_option(option: str | None) -> int:
    if option is None:
        raise ValueError("Missing lighting management exit condition.")
    normalized = str(option).strip().lower()
    for code, label in EXIT_CONDITION_NAMES.items():
        if label == normalized:
            return int(code)
    raise ValueError(
        f"Unsupported lighting management exit condition `{option}`."
    )


def _request_messages(
    request: str,
    where: str,
    *,
    sensor_address: str | int | None = None,
) -> list[str]:
    if request == REQUEST_ALL:
        messages = [
            f"*#24*{where}*{REQUEST_TO_DIMENSION[name]}##"
            for name in (
                REQUEST_SWITCH_ON_VALUE,
                REQUEST_MAX_LUX,
                REQUEST_MAINTAINED_LUX,
                REQUEST_AUTO_SWITCH_ON,
                REQUEST_SWITCH_ON_DELAY,
                REQUEST_AUTO_SWITCH_OFF,
                REQUEST_SWITCH_OFF_DELAY,
                REQUEST_DELAY_TIMER,
                REQUEST_STANDBY_TIMER,
                REQUEST_STANDBY_VALUE,
                REQUEST_OFF_VALUE,
                REQUEST_SLAVE_OFFSET,
                REQUEST_STATE,
            )
        ]
        if sensor_address is not None:
            messages.append(f"*#24*{where}*18*{sensor_address}##")
        return messages

    if request == REQUEST_CENTRALIZED_LUX:
        if sensor_address is None:
            raise ValueError("centralized_lux request requires sensor_address.")
        return [f"*#24*{where}*18*{sensor_address}##"]

    return [f"*#24*{where}*{REQUEST_TO_DIMENSION[request]}##"]


def build_light_management_request(
    request: str,
    where: str | int,
    *,
    sensor_address: str | int | None = None,
) -> str | list[str]:
    """Build a WHO=24 lighting management request."""
    request = str(request)
    if request not in SUPPORTED_REQUESTS:
        raise ValueError(f"Unsupported lighting management request `{request}`.")
    where = _normalize_where(where)
    return _request_messages(
        request,
        where,
        sensor_address=None if sensor_address is None else str(sensor_address).strip(),
    )


def build_light_management_command(
    operation: str,
    where: str | int,
    *,
    value: int | str | float | None = None,
    enabled: bool | int | str | None = None,
    profile: int | str | None = None,
    mode: int | str | None = None,
    exit_condition: int | str | None = None,
    hours: int | str | None = None,
    minutes: int | str | None = None,
    seconds: int | str | None = None,
    sensor_address: str | int | None = None,
    lux: int | str | None = None,
    error: int | str | None = None,
) -> str:
    """Build a WHO=24 lighting management command."""
    operation = str(operation)
    where = _normalize_where(where)

    if operation in SCALAR_OPERATION_TO_DIMENSION:
        dimension = SCALAR_OPERATION_TO_DIMENSION[operation]
        minimum, maximum = SCALAR_RANGES[operation]
        if operation in {"set_auto_switch_on", "set_auto_switch_off"} and enabled is not None:
            value = 1 if bool(enabled) else 0
        return (
            f"*#24*{where}*#{dimension}*"
            f"{_normalize_int(value, operation, minimum, maximum)}##"
        )

    if operation == "activate_profile":
        profile = _normalize_int(profile, "profile", 1, 255)
        return f"*24*1#{profile}*{where}##"

    if operation == "enable_slave_offset":
        return f"*24*2#1*{where}##"
    if operation == "disable_slave_offset":
        return f"*24*2#0*{where}##"

    if operation == "set_state":
        mode = _normalize_int(mode, "mode", 0, 2)
        exit_condition = _normalize_int(exit_condition, "exit_condition", 1, 5)
        hours = _normalize_int(hours, "hours", 0, 23)
        minutes = _normalize_int(minutes, "minutes", 0, 59)
        seconds = _normalize_int(seconds, "seconds", 0, 59)
        return (
            f"*#24*{where}*#17*{mode}*{exit_condition}*"
            f"{hours}*{minutes}*{seconds}##"
        )

    if operation == "set_centralized_lux":
        sensor_address = str(sensor_address).strip() if sensor_address is not None else None
        if not sensor_address:
            raise ValueError("Missing lighting management sensor_address.")
        lux = _normalize_int(lux, "lux", 0, 10000)
        error = _normalize_int(error, "error", 0, 2)
        return f"*#24*{where}*#18*{sensor_address}*{lux}*{error}##"

    raise ValueError(f"Unsupported lighting management operation `{operation}`.")


def parse_light_management_frame(raw_message: str) -> dict | None:
    """Parse a WHO=24 raw response or event frame into structured data."""
    raw_message = str(raw_message).strip()
    match = LIGHT_MANAGEMENT_RESPONSE_RE.match(raw_message)
    if match is None:
        return None

    where = match.group("where")
    dimension = int(match.group("dimension"))
    request = DIMENSION_TO_REQUEST.get(dimension)
    parts = [part for part in match.group("body").split("*") if part != ""]

    if request in SCALAR_REQUESTS and len(parts) == 1:
        value = int(parts[0])
        parsed = {
            "kind": request,
            "where": where,
            "dimension": dimension,
            "value": value,
        }
        if request in BOOLEAN_REQUESTS:
            parsed["enabled"] = value == 1
        return parsed

    if request == REQUEST_STATE and len(parts) == 5:
        mode = int(parts[0])
        exit_condition = int(parts[1])
        hours = int(parts[2])
        minutes = int(parts[3])
        seconds = int(parts[4])
        return {
            "kind": REQUEST_STATE,
            "where": where,
            "dimension": dimension,
            "mode": mode,
            "mode_name": MODE_NAMES.get(mode, f"mode_{mode}"),
            "exit_condition": exit_condition,
            "exit_condition_name": EXIT_CONDITION_NAMES.get(
                exit_condition,
                f"exit_{exit_condition}",
            ),
            "hours": hours,
            "minutes": minutes,
            "seconds": seconds,
            "time_value": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
        }

    if request == REQUEST_CENTRALIZED_LUX and len(parts) == 3:
        error = int(parts[2])
        return {
            "kind": REQUEST_CENTRALIZED_LUX,
            "where": where,
            "dimension": dimension,
            "sensor_address": parts[0],
            "lux": int(parts[1]),
            "error": error,
            "error_name": CENTRALIZED_LUX_ERROR_NAMES.get(error, f"error_{error}"),
        }

    return None


@dataclass
class _LightManagementZoneState:
    where: str
    switch_on_value: int | None = None
    max_lux: int | None = None
    maintained_lux: int | None = None
    auto_switch_on: bool | None = None
    switch_on_delay: int | None = None
    auto_switch_off: bool | None = None
    switch_off_delay: int | None = None
    delay_timer: int | None = None
    standby_timer: int | None = None
    standby_value: int | None = None
    off_value: int | None = None
    slave_offset: int | None = None
    mode: int | None = None
    mode_name: str | None = None
    exit_condition: int | None = None
    exit_condition_name: str | None = None
    state_hours: int | None = None
    state_minutes: int | None = None
    state_seconds: int | None = None
    state_time: str | None = None
    sensor_address: str | None = None
    lux: int | None = None
    error: int | None = None
    error_name: str | None = None
    last_kind: str | None = None
    last_update: str | None = None


class MyHOMELightManagementState:
    """Track the latest WHO=24 state seen for each LM WHERE."""

    def __init__(self) -> None:
        self._zones: dict[str, _LightManagementZoneState] = {}

    def handle_feedback(self, data: dict) -> None:
        where = str(data.get("where"))
        zone = self._zones.setdefault(where, _LightManagementZoneState(where=where))
        zone.last_kind = data.get("kind")
        zone.last_update = _utcnow()

        kind = data.get("kind")
        if kind in SCALAR_FIELD_MAP:
            field = SCALAR_FIELD_MAP[kind]
            if kind in BOOLEAN_REQUESTS:
                setattr(zone, field, bool(data.get("enabled")))
            else:
                setattr(zone, field, int(data.get("value")))
            return

        if kind == REQUEST_STATE:
            zone.mode = int(data.get("mode"))
            zone.mode_name = data.get("mode_name")
            zone.exit_condition = int(data.get("exit_condition"))
            zone.exit_condition_name = data.get("exit_condition_name")
            zone.state_hours = int(data.get("hours"))
            zone.state_minutes = int(data.get("minutes"))
            zone.state_seconds = int(data.get("seconds"))
            zone.state_time = data.get("time_value")
            return

        if kind == REQUEST_CENTRALIZED_LUX:
            zone.sensor_address = str(data.get("sensor_address"))
            zone.lux = int(data.get("lux"))
            zone.error = int(data.get("error"))
            zone.error_name = data.get("error_name")

    def zone_snapshot(self, where: str | int) -> dict | None:
        zone = self._zones.get(str(where))
        return None if zone is None else asdict(zone)

    def all_snapshots(self) -> dict[str, dict]:
        return {
            where: asdict(state)
            for where, state in sorted(self._zones.items(), key=lambda item: item[0])
        }


def build_light_management_response(
    request: str,
    raw_frames: list[str],
    *,
    where: str | int | None = None,
) -> dict:
    """Build a structured response from collected WHO=24 raw frames."""
    state = MyHOMELightManagementState()
    updates: list[dict] = []

    for frame in raw_frames:
        parsed = parse_light_management_frame(frame)
        if parsed is None:
            continue
        updates.append(parsed)
        state.handle_feedback(parsed)

    result = {
        "request": str(request),
        "raw_frames": raw_frames,
        "updates": updates,
    }
    if where is not None:
        result["where"] = str(where)
        result["state"] = state.zone_snapshot(where)
    else:
        result["states"] = state.all_snapshots()
    return result
