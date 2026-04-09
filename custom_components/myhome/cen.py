"""Helpers for MyHOME WHO=15 and WHO=25 CEN commands."""

from __future__ import annotations

import re

ATTR_OPERATION = "operation"
ATTR_PUSHBUTTON = "pushbutton"
ATTR_WHERE = "where"

SERVICE_CEN_COMMAND = "cen_command"
SERVICE_CENPLUS_COMMAND = "cenplus_command"

_CEN_WHERE_RE = re.compile(r"^\d+(?:#4#\d{1,2})?$")

CEN_OPERATION_TO_SUFFIX = {
    "press": "",
    "short_release": "#1",
    "long_release": "#2",
    "hold": "#3",
}
CENPLUS_OPERATION_TO_WHAT = {
    "short_press": 21,
    "start_hold": 22,
    "hold": 23,
    "long_release": 24,
    "slow_clockwise": 25,
    "fast_clockwise": 26,
    "slow_counterclockwise": 27,
    "fast_counterclockwise": 28,
}


def _normalize_pushbutton(pushbutton: int | str | None) -> int:
    if pushbutton is None:
        raise ValueError("Missing CEN pushbutton.")
    value = int(pushbutton)
    if value < 0 or value > 31:
        raise ValueError("CEN pushbutton must be between 0 and 31.")
    return value


def _normalize_cen_where(where: int | str | None) -> str:
    if where is None:
        raise ValueError("Missing CEN WHERE.")
    normalized = str(where).strip()
    if _CEN_WHERE_RE.fullmatch(normalized) is None:
        raise ValueError("Invalid CEN WHERE.")

    if "#4#" not in normalized:
        return normalized

    main, _, interface = normalized.partition("#4#")
    interface_value = int(interface)
    if interface_value < 0 or interface_value > 15:
        raise ValueError("CEN interface must be between 00 and 15.")
    return f"{main}#4#{interface_value:02d}"


def _normalize_cenplus_where(where: int | str | None) -> str:
    if where is None:
        raise ValueError("Missing CEN Plus object.")
    normalized = str(where).strip()
    if not normalized.isdigit():
        raise ValueError("Invalid CEN Plus object.")

    object_value = int(normalized[1:]) if normalized.startswith("2") else int(normalized)
    if object_value < 0 or object_value > 2047:
        raise ValueError("CEN Plus object must be between 0 and 2047.")
    return f"2{object_value}"


def build_cen_command(
    where: int | str,
    pushbutton: int | str,
    operation: str,
) -> str:
    """Build a WHO=15 CEN command."""
    normalized_where = _normalize_cen_where(where)
    button = _normalize_pushbutton(pushbutton)
    suffix = CEN_OPERATION_TO_SUFFIX.get(str(operation).lower())
    if suffix is None:
        raise ValueError(f"Unsupported CEN operation `{operation}`.")
    return f"*15*{button:02d}{suffix}*{normalized_where}##"


def build_cenplus_command(
    where: int | str,
    pushbutton: int | str,
    operation: str,
) -> str:
    """Build a WHO=25 CEN Plus command."""
    normalized_where = _normalize_cenplus_where(where)
    button = _normalize_pushbutton(pushbutton)
    what = CENPLUS_OPERATION_TO_WHAT.get(str(operation).lower())
    if what is None:
        raise ValueError(f"Unsupported CEN Plus operation `{operation}`.")
    return f"*25*{what}#{button}*{normalized_where}##"
