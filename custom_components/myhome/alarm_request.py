"""Helpers for MyHOME burglar alarm status requests."""

from __future__ import annotations

import re

from OWNd.message import OWNAlarmEvent, OWNAuxEvent, OWNMessage

ATTR_REQUEST = "request"
ATTR_ZONE = "zone"

SERVICE_ALARM_REQUEST = "alarm_request"

_GENERAL_ALARM_FRAME_RE = re.compile(r"^\*5\*(?P<what>\d+)\*##$")
_ALARM_STATE_NAMES = {
    0: "maintenance",
    1: "activation",
    2: "deactivation",
    3: "delay end",
    4: "system battery fault",
    5: "battery ok",
    6: "no network",
    7: "network present",
    8: "engage",
    9: "disengage",
    10: "battery unloads",
    11: "active zone",
    12: "technical alarm",
    13: "reset technical alarm",
    14: "no reception",
    15: "intrusion alarm",
    16: "tampering",
    17: "anti-panic alarm",
    18: "non-active zone",
    26: "start programming",
    27: "stop programming",
    31: "silent alarm",
}


def _alarm_flags(state_code: int) -> tuple[bool, bool, bool]:
    return (
        state_code in {12, 15, 16, 17, 31},
        state_code in {1, 11},
        state_code == 8,
    )


def parse_alarm_frame(raw_frame: str) -> dict | None:
    """Parse one raw alarm-related frame into a structured payload."""
    normalized = str(raw_frame).strip()
    parsed = OWNMessage.parse(normalized)

    if isinstance(parsed, OWNAlarmEvent):
        return {
            "kind": "alarm",
            "raw_message": str(parsed),
            "state_code": getattr(parsed, "_state_code", None),
            "state_name": getattr(parsed, "_state", None),
            "general": parsed.general,
            "zone": parsed.zone,
            "sensor": parsed.sensor,
            "is_alarm": parsed.is_alarm,
            "is_active": parsed.is_active,
            "is_engaged": parsed.is_engaged,
        }

    if isinstance(parsed, OWNAuxEvent):
        return {
            "kind": "auxiliary",
            "raw_message": str(parsed),
            "channel": parsed.channel,
            "state_code": parsed.state_code,
            "is_on": parsed.is_on,
        }

    match = _GENERAL_ALARM_FRAME_RE.match(normalized)
    if match is None:
        return None

    state_code = int(match.group("what"))
    is_alarm, is_active, is_engaged = _alarm_flags(state_code)
    return {
        "kind": "alarm",
        "raw_message": normalized,
        "state_code": state_code,
        "state_name": _ALARM_STATE_NAMES.get(state_code, f"unknown ({state_code})"),
        "general": True,
        "zone": None,
        "sensor": None,
        "is_alarm": is_alarm,
        "is_active": is_active,
        "is_engaged": is_engaged,
    }


def build_alarm_request(request: str, zone: int | str | None = None) -> str:
    """Build a burglar-alarm status request."""
    normalized = str(request).lower()

    if normalized == "central":
        return "*#5##"
    if normalized == "central_direct":
        return "*#5*0##"
    if normalized == "zone":
        if zone is None:
            raise ValueError("Alarm zone request requires a zone.")
        zone_value = int(zone)
        if zone_value < 1 or zone_value > 8:
            raise ValueError("Alarm zone must be between 1 and 8.")
        return f"*#5*#{zone_value}##"
    if normalized == "auxiliaries":
        return "*#9##"

    raise ValueError(f"Unsupported alarm request `{request}`.")


def build_alarm_response(raw_frames: list[str]) -> dict:
    """Parse alarm and auxiliary raw frames into a structured response."""
    result: dict = {
        "events": [],
        "zones": {},
        "auxiliaries": {},
    }

    for raw_frame in raw_frames:
        item = parse_alarm_frame(str(raw_frame))
        if item is None:
            continue

        result["events"].append(item)
        if item["kind"] == "alarm":
            if item["general"] or item["zone"] is None:
                result["central"] = item
            if item["zone"] is not None:
                result["zones"][str(item["zone"])] = item
        elif item["kind"] == "auxiliary":
            result["auxiliaries"][str(item["channel"])] = item

    return result
