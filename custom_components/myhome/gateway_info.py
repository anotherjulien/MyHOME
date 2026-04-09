"""Helpers for MyHOME WHO=13 gateway requests and commands."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from OWNd.message import OWNMessage, OWNGatewayCommand, OWNGatewayEvent

ATTR_OPERATION = "operation"
ATTR_REQUEST = "request"
ATTR_TIME_ZONE = "time_zone"

SERVICE_GATEWAY_COMMAND = "gateway_command"
SERVICE_GATEWAY_REQUEST = "gateway_request"

REQUEST_TIME = "time"
REQUEST_DATE = "date"
REQUEST_IP_ADDRESS = "ip_address"
REQUEST_NETMASK = "netmask"
REQUEST_MAC_ADDRESS = "mac_address"
REQUEST_DEVICE_TYPE = "device_type"
REQUEST_FIRMWARE_VERSION = "firmware_version"
REQUEST_UPTIME = "uptime"
REQUEST_DATETIME = "datetime"
REQUEST_KERNEL_VERSION = "kernel_version"
REQUEST_DISTRIBUTION_VERSION = "distribution_version"
REQUEST_ALL = "all"

REQUEST_TO_DIMENSION = {
    REQUEST_TIME: 0,
    REQUEST_DATE: 1,
    REQUEST_IP_ADDRESS: 10,
    REQUEST_NETMASK: 11,
    REQUEST_MAC_ADDRESS: 12,
    REQUEST_DEVICE_TYPE: 15,
    REQUEST_FIRMWARE_VERSION: 16,
    REQUEST_UPTIME: 19,
    REQUEST_DATETIME: 22,
    REQUEST_KERNEL_VERSION: 23,
    REQUEST_DISTRIBUTION_VERSION: 24,
}
DIMENSION_TO_REQUEST = {value: key for key, value in REQUEST_TO_DIMENSION.items()}
REQUEST_ORDER = [
    REQUEST_TIME,
    REQUEST_DATE,
    REQUEST_IP_ADDRESS,
    REQUEST_NETMASK,
    REQUEST_MAC_ADDRESS,
    REQUEST_DEVICE_TYPE,
    REQUEST_FIRMWARE_VERSION,
    REQUEST_UPTIME,
    REQUEST_DATETIME,
    REQUEST_KERNEL_VERSION,
    REQUEST_DISTRIBUTION_VERSION,
]


def build_gateway_request(request: str) -> str | list[str]:
    """Build a WHO=13 gateway request."""
    normalized = str(request).lower()
    if normalized == REQUEST_ALL:
        return [build_gateway_request(item) for item in REQUEST_ORDER]

    dimension = REQUEST_TO_DIMENSION.get(normalized)
    if dimension is None:
        raise ValueError(f"Unsupported gateway request `{request}`.")
    return f"*#13**{dimension}##"


def build_gateway_command(operation: str, time_zone: str) -> OWNGatewayCommand:
    """Build a WHO=13 gateway write command."""
    normalized = str(operation).lower()
    if normalized == "set_datetime_now":
        return OWNGatewayCommand.set_datetime_to_now(time_zone)
    if normalized == "set_date_today":
        return OWNGatewayCommand.set_date_to_today(time_zone)
    if normalized == "set_time_now":
        return OWNGatewayCommand.set_time_to_now(time_zone)
    raise ValueError(f"Unsupported gateway operation `{operation}`.")


def _iso_date(value: date | None) -> str | None:
    return value.isoformat() if isinstance(value, date) else None


def _iso_time(value: time | None) -> str | None:
    return value.isoformat() if isinstance(value, time) else None


def _iso_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _gateway_item_from_message(message: OWNGatewayEvent | OWNGatewayCommand) -> dict | None:
    dimension = getattr(message, "dimension", None)
    if dimension is None:
        return None

    request = DIMENSION_TO_REQUEST.get(int(dimension), f"dimension_{int(dimension)}")
    item: dict = {
        "kind": request,
        "request": request,
        "dimension": int(dimension),
        "raw_message": str(message),
    }

    if int(dimension) == 0:
        item["time"] = _iso_time(getattr(message, "_time", None))
    elif int(dimension) == 1:
        item["date"] = _iso_date(getattr(message, "_date", None))
    elif int(dimension) == 10:
        item["ip_address"] = getattr(message, "_ip_address", None)
    elif int(dimension) == 11:
        item["netmask"] = getattr(message, "_netmask", None)
    elif int(dimension) == 12:
        item["mac_address"] = getattr(message, "_mac_address", None)
    elif int(dimension) == 15:
        item["device_type"] = getattr(message, "_device_type", None)
    elif int(dimension) == 16:
        item["firmware_version"] = getattr(message, "_firmware_version", None)
    elif int(dimension) == 19:
        uptime = getattr(message, "_uptime", None)
        if isinstance(uptime, timedelta):
            item["uptime"] = str(uptime)
            item["uptime_seconds"] = int(uptime.total_seconds())
    elif int(dimension) == 22:
        item["datetime"] = _iso_datetime(getattr(message, "_datetime", None))
    elif int(dimension) == 23:
        item["kernel_version"] = getattr(message, "_kernel_version", None)
    elif int(dimension) == 24:
        item["distribution_version"] = getattr(message, "_distribution_version", None)

    return item


def build_gateway_event_payload(message: OWNGatewayEvent | OWNGatewayCommand) -> dict | None:
    """Convert an incoming WHO=13 message into a bus-event payload."""
    return _gateway_item_from_message(message)


def build_gateway_response(raw_frames: list[str]) -> dict:
    """Build a structured response from WHO=13 raw frames."""
    result: dict = {"items": []}

    for raw_frame in raw_frames:
        parsed = OWNMessage.parse(str(raw_frame).strip())
        if not isinstance(parsed, (OWNGatewayEvent, OWNGatewayCommand)):
            continue

        item = _gateway_item_from_message(parsed)
        if item is None:
            continue

        result["items"].append(item)
        for key, value in item.items():
            if key in {"kind", "request", "dimension", "raw_message"}:
                continue
            result[key] = value

    return result
