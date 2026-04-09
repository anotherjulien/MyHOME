from __future__ import annotations

import pytest

from tests._module_loader import load_module


cen = load_module("cen")


def test_build_cen_command():
    assert cen.build_cen_command("0001", 1, "press") == "*15*01*0001##"


def test_build_cenplus_command():
    assert cen.build_cenplus_command("33", 1, "short_press") == "*25*21#1*233##"


def test_invalid_cenplus_operation_is_rejected():
    with pytest.raises(ValueError):
        cen.build_cenplus_command("33", 1, "invalid")
