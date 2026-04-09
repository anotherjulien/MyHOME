from __future__ import annotations

from tests._module_loader import load_module


alarm_request = load_module("alarm_request")


def test_build_alarm_request_zone():
    assert alarm_request.build_alarm_request("zone", 3) == "*#5*#3##"


def test_parse_general_alarm_frame():
    parsed = alarm_request.parse_alarm_frame("*5*15*##")

    assert parsed["kind"] == "alarm"
    assert parsed["state_code"] == 15
    assert parsed["state_name"] == "intrusion alarm"
    assert parsed["is_alarm"] is True


def test_build_alarm_response_groups_zones_and_auxiliaries():
    response = alarm_request.build_alarm_response(
        [
            "*5*15*##",
            "*9*1*1##",
        ]
    )

    assert response["central"]["state_code"] == 15
    assert response["auxiliaries"]["1"]["is_on"] is True
