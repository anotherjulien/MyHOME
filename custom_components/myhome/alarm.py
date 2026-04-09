"""Helpers for MyHOME burglar alarm and WHO=9 auxiliary commands."""

from __future__ import annotations

from homeassistant.components.alarm_control_panel.const import AlarmControlPanelState
from homeassistant.const import CONF_NAME

from .const import (
    CONF_DEVICE_MODEL,
    CONF_ENTITIES,
    CONF_ENTITY_NAME,
    CONF_MANUFACTURER,
    CONF_PLATFORMS,
    CONF_WHO,
)

ATTR_ARM_CHANNEL = "arm_channel"
ATTR_CHANNEL = "channel"
ATTR_CONTROL_CHANNEL = "control_channel"
ATTR_DISARM_CHANNEL = "disarm_channel"
ATTR_STATE_CODE = "state_code"
ATTR_STATE_NAME = "state_name"

SERVICE_AUX_COMMAND = "aux_command"

AUX_OPERATION_TO_CODE = {
    "off": 0,
    "on": 1,
    "toggle": 2,
    "stop": 3,
    "up": 4,
    "down": 5,
    "enable": 6,
    "disable": 7,
    "reset_general": 8,
    "reset_burglar": 9,
    "reset_tamper": 10,
}

DEFAULT_ALARM_CONTROL_CHANNEL = 1
SYNTHETIC_ALARM_DEVICE_ID = "gateway_alarm_panel"


def build_aux_command(channel: int | str, operation: str) -> str:
    """Build a WHO=9 auxiliary command frame."""
    try:
        channel = int(channel)
    except (TypeError, ValueError) as err:
        raise ValueError("Invalid auxiliary channel.") from err

    if channel < 1 or channel > 255:
        raise ValueError("Auxiliary channel must be between 1 and 255.")

    try:
        what = AUX_OPERATION_TO_CODE[str(operation)]
    except KeyError as err:
        raise ValueError(f"Unsupported auxiliary operation `{operation}`.") from err

    return f"*9*{what}*{channel}##"


def ensure_alarm_platform_config(gateway_config: dict) -> None:
    """Inject a synthetic alarm panel when the gateway exposes WHO=25 sensors."""
    platforms = gateway_config.setdefault(CONF_PLATFORMS, {})
    binary_sensors = platforms.get("binary_sensor", {})
    has_alarm_sensors = any(
        device_config.get(CONF_WHO) == "25"
        for device_config in binary_sensors.values()
        if isinstance(device_config, dict)
    )

    alarm_platform = platforms.get("alarm_control_panel")
    if alarm_platform is not None:
        for device_config in alarm_platform.values():
            device_config.setdefault(CONF_ENTITIES, {})
            device_config.setdefault(CONF_ENTITY_NAME, None)
            device_config.setdefault(CONF_DEVICE_MODEL, None)
        return

    if not has_alarm_sensors:
        return

    platforms["alarm_control_panel"] = {
        SYNTHETIC_ALARM_DEVICE_ID: {
        CONF_NAME: "Alarm panel",
        CONF_ENTITY_NAME: None,
        ATTR_CONTROL_CHANNEL: DEFAULT_ALARM_CONTROL_CHANNEL,
        ATTR_ARM_CHANNEL: None,
        ATTR_DISARM_CHANNEL: None,
        CONF_MANUFACTURER: "BTicino S.p.A.",
        CONF_DEVICE_MODEL: "MyHOME Burglar Alarm",
        CONF_ENTITIES: {},
        }
    }


def map_alarm_state(
    state_code: int | None,
    current_state: AlarmControlPanelState | None,
    engaged: bool,
) -> tuple[AlarmControlPanelState | None, bool]:
    """Map a WHO=5 event code to an alarm control panel state."""
    if state_code is None:
        return current_state, engaged

    if state_code in {12, 15, 16, 17, 31}:
        return AlarmControlPanelState.TRIGGERED, engaged

    if state_code == 1:
        return AlarmControlPanelState.ARMING, True

    if state_code in {3, 8, 11}:
        return AlarmControlPanelState.ARMED_AWAY, True

    if state_code in {2, 9}:
        return AlarmControlPanelState.DISARMED, False

    if state_code == 13:
        return (
            AlarmControlPanelState.ARMED_AWAY
            if engaged
            else AlarmControlPanelState.DISARMED,
            engaged,
        )

    return current_state, engaged
