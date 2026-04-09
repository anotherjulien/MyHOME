"""Helpers for MyHOME WHO=17 scene programmer."""

from __future__ import annotations

import re

from homeassistant.components.switch import DOMAIN as SWITCH
from homeassistant.const import CONF_NAME

from .const import (
    CONF_DEVICE_MODEL,
    CONF_ENTITIES,
    CONF_ENTITY_NAME,
    CONF_MANUFACTURER,
    CONF_OPERATION,
    CONF_PLATFORMS,
    CONF_WHERE,
    CONF_WHO,
    DOMAIN,
)

ATTR_OPERATION = "operation"
ATTR_WHERE = "where"

SERVICE_SCENE_PROGRAMMER_COMMAND = "scene_programmer_command"
SCENE_ACTIVE_ROLE = "active"
SCENE_ENABLED_ROLE = "enabled"
SCENE_SWITCH_ROLES = {SCENE_ACTIVE_ROLE, SCENE_ENABLED_ROLE}
SCENE_SWITCH_DEVICE_ID_PREFIX = "scene-"
DEFAULT_SCENE_MANUFACTURER = "BTicino S.p.A."
DEFAULT_SCENE_MODEL = "MyHOME Scene Programmer"

SCENE_OPERATION_TO_WHAT = {
    "start": 1,
    "stop": 2,
    "enable": 3,
    "disable": 4,
}
SCENE_STATE_NAMES = {
    1: "started",
    2: "stopped",
    3: "enabled",
    4: "disabled",
}

SCENE_FRAME_RE = re.compile(r"^\*17\*(?P<what>[1-4])\*(?P<where>\d+)##$")


def _normalize_scene_where(where: int | str | None) -> int:
    if where is None:
        raise ValueError("Missing scene WHERE.")
    where = int(where)
    if where < 0:
        raise ValueError("Invalid scene WHERE.")
    return where


def build_scene_programmer_command(where: int | str, operation: str) -> str:
    """Build a WHO=17 scene programmer command or status request."""
    where = _normalize_scene_where(where)
    operation = str(operation)

    if operation == "query_status":
        return f"*#17*{where}##"

    if operation not in SCENE_OPERATION_TO_WHAT:
        raise ValueError(f"Unsupported scene operation `{operation}`.")

    return f"*17*{SCENE_OPERATION_TO_WHAT[operation]}*{where}##"


def parse_scene_programmer_frames(
    raw_frames: list[str],
    where: int | str | None = None,
) -> dict | None:
    """Parse WHO=17 status frames into a structured scene state."""
    scene_where = _normalize_scene_where(where) if where is not None else None
    state = {
        "where": scene_where,
        "is_on": None,
        "is_enabled": None,
        "active_state_code": None,
        "active_state": None,
        "enabled_state_code": None,
        "enabled_state": None,
        "states": [],
        "scenes": {},
    }
    parsed = False

    for raw_frame in raw_frames:
        match = SCENE_FRAME_RE.match(str(raw_frame).strip())
        if match is None:
            continue

        parsed = True
        state_code = int(match.group("what"))
        frame_where = int(match.group("where"))
        state["states"].append(
            {
                "code": state_code,
                "name": SCENE_STATE_NAMES[state_code],
                "where": frame_where,
            }
        )
        scene_state = state["scenes"].setdefault(
            frame_where,
            {
                "where": frame_where,
                "is_on": None,
                "is_enabled": None,
                "active_state_code": None,
                "active_state": None,
                "enabled_state_code": None,
                "enabled_state": None,
            },
        )

        if state_code in {1, 2}:
            scene_state["active_state_code"] = state_code
            scene_state["active_state"] = SCENE_STATE_NAMES[state_code]
            scene_state["is_on"] = state_code == 1
        else:
            scene_state["enabled_state_code"] = state_code
            scene_state["enabled_state"] = SCENE_STATE_NAMES[state_code]
            scene_state["is_enabled"] = state_code == 3

        if scene_where not in {0, None} and frame_where != scene_where:
            continue
        if scene_where == 0:
            continue

        state["where"] = frame_where
        state["is_on"] = scene_state["is_on"]
        state["is_enabled"] = scene_state["is_enabled"]
        state["active_state_code"] = scene_state["active_state_code"]
        state["active_state"] = scene_state["active_state"]
        state["enabled_state_code"] = scene_state["enabled_state_code"]
        state["enabled_state"] = scene_state["enabled_state"]

    if scene_where == 0:
        state["scene_count"] = len(state["scenes"])

    return state if parsed else None


def _scene_switch_device_id(scene_id: int | str, role: str) -> str:
    scene_id = int(scene_id)
    if role not in SCENE_SWITCH_ROLES:
        raise ValueError(f"Unsupported scene switch role `{role}`.")
    return f"{SCENE_SWITCH_DEVICE_ID_PREFIX}{scene_id}-{role}"


def ensure_scene_switch_config(
    gateway_config: dict,
    scene_id: int | str,
    *,
    name: str | None = None,
) -> dict[str, dict]:
    """Ensure the synthetic switch entries exist for a scene."""
    scene_id = int(scene_id)
    switch_config = gateway_config.setdefault(CONF_PLATFORMS, {}).setdefault(
        SWITCH,
        {},
    )
    scene_name = name or f"Scene {scene_id}"
    created: dict[str, dict] = {}

    for role, entity_name in (
        (SCENE_ACTIVE_ROLE, "Active"),
        (SCENE_ENABLED_ROLE, "Enabled"),
    ):
        device_id = _scene_switch_device_id(scene_id, role)
        device_config = switch_config.setdefault(
            device_id,
            {
                CONF_NAME: scene_name,
                CONF_ENTITY_NAME: entity_name,
                CONF_WHO: "17",
                CONF_WHERE: str(scene_id),
                CONF_OPERATION: role,
                CONF_MANUFACTURER: DEFAULT_SCENE_MANUFACTURER,
                CONF_DEVICE_MODEL: DEFAULT_SCENE_MODEL,
                CONF_ENTITIES: {},
            },
        )
        device_config.setdefault(CONF_NAME, scene_name)
        device_config.setdefault(CONF_ENTITY_NAME, entity_name)
        device_config.setdefault(CONF_WHO, "17")
        device_config.setdefault(CONF_WHERE, str(scene_id))
        device_config.setdefault(CONF_OPERATION, role)
        device_config.setdefault(CONF_MANUFACTURER, DEFAULT_SCENE_MANUFACTURER)
        device_config.setdefault(CONF_DEVICE_MODEL, DEFAULT_SCENE_MODEL)
        device_config.setdefault(CONF_ENTITIES, {})
        created[device_id] = device_config

    return created


def restore_scene_switch_platform_config(
    gateway_config: dict,
    entity_entries: list,
    gateway_mac: str,
) -> None:
    """Re-seed synthetic scene switches from the entity registry."""
    gateway_mac = str(gateway_mac).lower()
    prefix = f"{gateway_mac}-{SCENE_SWITCH_DEVICE_ID_PREFIX}"

    for entry in entity_entries:
        if entry.platform != DOMAIN or entry.domain != SWITCH:
            continue
        unique_id = str(entry.unique_id or "")
        if not unique_id.startswith(prefix):
            continue

        suffix = unique_id[len(prefix) :]
        try:
            scene_text, role = suffix.rsplit("-", 1)
            if role not in SCENE_SWITCH_ROLES:
                continue
            ensure_scene_switch_config(gateway_config, int(scene_text))
        except (TypeError, ValueError):
            continue


def ensure_scene_switches_from_state(
    gateway_config: dict,
    state: dict | None,
) -> list[int]:
    """Create synthetic scene switches for all scenes present in a parsed state."""
    scenes = (state or {}).get("scenes", {})
    created: list[int] = []
    for scene_id in sorted(int(scene_key) for scene_key in scenes):
        ensure_scene_switch_config(gateway_config, scene_id)
        created.append(scene_id)
    return created
