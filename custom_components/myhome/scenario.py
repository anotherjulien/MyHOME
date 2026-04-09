"""Helpers for MyHOME WHO=0 scenario commands."""

from __future__ import annotations

import re

ATTR_OPERATION = "operation"
ATTR_SCENARIO = "scenario"
ATTR_WHERE = "where"

SERVICE_SCENARIO_COMMAND = "scenario_command"

_SCENARIO_WHERE_RE = re.compile(r"^(?P<where>\d{1,2})(?:#4#(?P<interface>\d{1,2}))?$")


def _normalize_scenario_where(where: int | str | None) -> str:
    if where is None:
        raise ValueError("Missing scenario WHERE.")

    if isinstance(where, int):
        if where < 1 or where > 99:
            raise ValueError("Scenario WHERE must be between 1 and 99.")
        return f"{where:02d}"

    normalized = str(where).strip()
    match = _SCENARIO_WHERE_RE.fullmatch(normalized)
    if match is None:
        raise ValueError("Invalid scenario WHERE.")

    where_value = int(match.group("where"))
    if where_value < 1 or where_value > 99:
        raise ValueError("Scenario WHERE must be between 1 and 99.")

    interface = match.group("interface")
    if interface is None:
        return f"{where_value:02d}"
    interface_value = int(interface)
    if interface_value < 0 or interface_value > 15:
        raise ValueError("Scenario interface must be between 00 and 15.")
    return f"{where_value:02d}#4#{interface_value:02d}"


def _normalize_scenario_id(scenario: int | str | None) -> int:
    if scenario is None:
        raise ValueError("Missing scenario id.")
    scenario_id = int(scenario)
    if scenario_id < 1 or scenario_id > 20:
        raise ValueError("Scenario id must be between 1 and 20.")
    return scenario_id


def build_scenario_command(
    where: int | str,
    operation: str,
    scenario: int | str | None = None,
) -> str:
    """Build a WHO=0 scenario command."""
    normalized_where = _normalize_scenario_where(where)
    normalized = str(operation).lower()

    if normalized == "activate":
        return f"*0*{_normalize_scenario_id(scenario)}*{normalized_where}##"
    if normalized == "start_recording":
        return f"*0*40#{_normalize_scenario_id(scenario)}*{normalized_where}##"
    if normalized == "stop_recording":
        return f"*0*41#{_normalize_scenario_id(scenario)}*{normalized_where}##"
    if normalized == "erase_all":
        return f"*0*42*{normalized_where}##"
    if normalized == "erase_scenario":
        return f"*0*42#{_normalize_scenario_id(scenario)}*{normalized_where}##"
    if normalized == "lock":
        return f"*0*43*{normalized_where}##"
    if normalized == "unlock":
        return f"*0*44*{normalized_where}##"

    raise ValueError(f"Unsupported scenario operation `{operation}`.")
