from __future__ import annotations

from tests._module_loader import load_module


gateway_info = load_module("gateway_info")


def test_build_gateway_request_all_expands_to_all_supported_requests():
    frames = gateway_info.build_gateway_request(gateway_info.REQUEST_ALL)

    assert isinstance(frames, list)
    assert len(frames) == len(gateway_info.REQUEST_ORDER)
    assert frames[0] == "*#13**0##"
    assert frames[-1] == "*#13**24##"


def test_build_gateway_request_single_dimension():
    assert gateway_info.build_gateway_request("device_type") == "*#13**15##"


def test_build_gateway_response_parses_device_type_and_firmware():
    response = gateway_info.build_gateway_response(
        ["*#13**15*200##", "*#13**16*2*0*51##"]
    )

    assert response["device_type"] == "F454"
    assert response["firmware_version"] == "2.0.51"
    assert [item["request"] for item in response["items"]] == [
        "device_type",
        "firmware_version",
    ]
