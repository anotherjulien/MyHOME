from __future__ import annotations

import pytest

from tests._module_loader import load_module


scenario = load_module("scenario")


def test_build_scenario_activate_command():
    assert scenario.build_scenario_command(1, "activate", 2) == "*0*2*01##"


def test_build_scenario_erase_all_command():
    assert scenario.build_scenario_command("01#4#3", "erase_all") == "*0*42*01#4#03##"


def test_invalid_scenario_where_is_rejected():
    with pytest.raises(ValueError):
        scenario.build_scenario_command("0", "activate", 1)
