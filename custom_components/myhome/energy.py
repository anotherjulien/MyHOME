"""Helpers for MyHOME WHO=18 energy requests and raw frame parsing."""

from __future__ import annotations

from datetime import date
import re

from OWNd.message import OWNEnergyCommand

ATTR_DATE = "date"
ATTR_MONTH = "month"
ATTR_REQUEST = "request"
ATTR_WHERE = "where"
ATTR_YEAR = "year"

EVENT_ENERGY = "myhome_energy_event"
SERVICE_ENERGY_REQUEST = "energy_request"

REQUEST_ACTIVE_POWER = "active_power"
REQUEST_DAILY_HISTORY = "daily_history"
REQUEST_HOURLY_HISTORY = "hourly_history"
REQUEST_MONTHLY_AVERAGE_HOURLY = "monthly_average_hourly"
REQUEST_MONTHLY_HISTORY = "monthly_history"
REQUEST_PARTIAL_DAILY = "partial_daily"
REQUEST_PARTIAL_MONTHLY = "partial_monthly"
REQUEST_TOTAL = "total"

SUPPORTED_REQUESTS = {
    REQUEST_ACTIVE_POWER,
    REQUEST_DAILY_HISTORY,
    REQUEST_HOURLY_HISTORY,
    REQUEST_MONTHLY_AVERAGE_HOURLY,
    REQUEST_MONTHLY_HISTORY,
    REQUEST_PARTIAL_DAILY,
    REQUEST_PARTIAL_MONTHLY,
    REQUEST_TOTAL,
}

_ACTIVE_POWER_RE = re.compile(
    r"^\*#18\*(?P<where>\d+(?:#0)?)\*113\*(?P<value>\d+)##$"
)
_TOTAL_RE = re.compile(r"^\*#18\*(?P<where>\d+(?:#0)?)\*51\*(?P<value>\d+)##$")
_PARTIAL_MONTH_RE = re.compile(
    r"^\*#18\*(?P<where>\d+(?:#0)?)\*53\*(?P<value>\d+)##$"
)
_PARTIAL_DAY_RE = re.compile(
    r"^\*#18\*(?P<where>\d+(?:#0)?)\*54\*(?P<value>\d+)##$"
)
_MONTHLY_RE = re.compile(
    r"^\*#18\*(?P<where>\d+(?:#0)?)\*52#(?P<year>\d{2})#(?P<month>\d{1,2})\*(?P<value>\d+)##$"
)
_HOURLY_RE = re.compile(
    r"^\*#18\*(?P<where>\d+(?:#0)?)\*511#(?P<month>\d{1,2})#(?P<day>\d{1,2})\*(?P<tag>\d{1,2})\*(?P<value>\d+)##$"
)
_MONTHLY_AVERAGE_RE = re.compile(
    r"^\*#18\*(?P<where>\d+(?:#0)?)\*512#(?P<month>\d{1,2})\*(?P<tag>\d{1,2})\*(?P<value>\d+)##$"
)
_DAILY_RE = re.compile(
    r"^\*#18\*(?P<where>\d+(?:#0)?)\*(?P<dimension>513|514)#(?P<month>\d{1,2})\*(?P<day>\d{1,2})\*(?P<value>\d+)##$"
)


def _normalize_where(where: str) -> str:
    where = str(where)
    if where.startswith("7") and not where.endswith("#0"):
        return f"{where}#0"
    return where


def _default_previous_month() -> tuple[int, int]:
    today = date.today()
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


def _coerce_date(value: str | date | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _coerce_year_month(
    year: int | str | None,
    month: int | str | None,
    *,
    previous_month_default: bool = False,
) -> tuple[int, int]:
    if year is None and month is None and previous_month_default:
        return _default_previous_month()

    today = date.today()
    return (
        int(year) if year is not None else today.year,
        int(month) if month is not None else today.month,
    )


def build_energy_request(
    request: str,
    where: str,
    *,
    date_value: str | date | None = None,
    year: int | str | None = None,
    month: int | str | None = None,
):
    """Build a WHO=18 energy request."""
    request = str(request)
    if request not in SUPPORTED_REQUESTS:
        raise ValueError(f"Unsupported energy request `{request}`.")

    where = _normalize_where(where)

    if request == REQUEST_ACTIVE_POWER:
        return f"*#18*{where}*113##"
    if request == REQUEST_TOTAL:
        return OWNEnergyCommand.get_total_consumption(where)
    if request == REQUEST_PARTIAL_MONTHLY:
        return OWNEnergyCommand.get_partial_monthly_consumption(where)
    if request == REQUEST_PARTIAL_DAILY:
        return OWNEnergyCommand.get_partial_daily_consumption(where)
    if request == REQUEST_HOURLY_HISTORY:
        target_date = _coerce_date(date_value)
        message = OWNEnergyCommand.get_hourly_consumption(where, target_date)
        if message is None:
            raise ValueError(f"Hourly history request out of range for {target_date}.")
        return message
    if request == REQUEST_DAILY_HISTORY:
        target_year, target_month = _coerce_year_month(year, month)
        message = OWNEnergyCommand.get_daily_consumption(
            where, target_year, target_month
        )
        if message is None:
            raise ValueError(
                f"Daily history request out of range for {target_year}-{target_month:02d}."
            )
        return message
    if request == REQUEST_MONTHLY_HISTORY:
        target_year, target_month = _coerce_year_month(
            year,
            month,
            previous_month_default=True,
        )
        return f"*#18*{where}*52#{str(target_year)[2:]}#{target_month}##"

    target_year, target_month = _coerce_year_month(year, month)
    if target_year != date.today().year:
        raise ValueError(
            "monthly_average_hourly only supports the current year in OpenWebNet."
        )
    return f"*18*58#{target_month}*{where}##"


def _resolve_day(month: int, day: int, *, years_back: int = 0) -> date | None:
    today = date.today()
    base_year = today.year - years_back

    try:
        resolved = date(base_year, month, day)
    except ValueError:
        return None

    if resolved > today:
        try:
            resolved = date(base_year - 1, month, day)
        except ValueError:
            return None
    return resolved


def parse_energy_frame(raw_message: str) -> dict | None:
    """Parse a raw WHO=18 energy frame into structured data."""
    raw_message = str(raw_message).strip()

    match = _ACTIVE_POWER_RE.match(raw_message)
    if match:
        return {
            "kind": REQUEST_ACTIVE_POWER,
            "where": match.group("where"),
            "value_w": int(match.group("value")),
        }

    match = _TOTAL_RE.match(raw_message)
    if match:
        return {
            "kind": REQUEST_TOTAL,
            "where": match.group("where"),
            "value_wh": int(match.group("value")),
        }

    match = _PARTIAL_MONTH_RE.match(raw_message)
    if match:
        return {
            "kind": REQUEST_PARTIAL_MONTHLY,
            "where": match.group("where"),
            "value_wh": int(match.group("value")),
        }

    match = _PARTIAL_DAY_RE.match(raw_message)
    if match:
        return {
            "kind": REQUEST_PARTIAL_DAILY,
            "where": match.group("where"),
            "value_wh": int(match.group("value")),
        }

    match = _MONTHLY_RE.match(raw_message)
    if match:
        year = 2000 + int(match.group("year"))
        month = int(match.group("month"))
        return {
            "kind": REQUEST_MONTHLY_HISTORY,
            "where": match.group("where"),
            "date": f"{year:04d}-{month:02d}-01",
            "value_wh": int(match.group("value")),
        }

    match = _HOURLY_RE.match(raw_message)
    if match:
        resolved = _resolve_day(
            int(match.group("month")),
            int(match.group("day")),
        )
        if resolved is None:
            return None

        tag = int(match.group("tag"))
        if tag == 25:
            return {
                "kind": REQUEST_HOURLY_HISTORY,
                "where": match.group("where"),
                "date": resolved.isoformat(),
                "daily_total_wh": int(match.group("value")),
            }

        if 1 <= tag <= 24:
            return {
                "kind": REQUEST_HOURLY_HISTORY,
                "where": match.group("where"),
                "date": resolved.isoformat(),
                "hour": tag - 1,
                "value_wh": int(match.group("value")),
            }
        return None

    match = _MONTHLY_AVERAGE_RE.match(raw_message)
    if match:
        tag = int(match.group("tag"))
        month = int(match.group("month"))
        if tag == 25:
            return {
                "kind": REQUEST_MONTHLY_AVERAGE_HOURLY,
                "where": match.group("where"),
                "month": month,
                "average_total_wh": int(match.group("value")),
            }

        if 1 <= tag <= 24:
            return {
                "kind": REQUEST_MONTHLY_AVERAGE_HOURLY,
                "where": match.group("where"),
                "month": month,
                "hour": tag - 1,
                "value_wh": int(match.group("value")),
            }
        return None

    match = _DAILY_RE.match(raw_message)
    if match:
        resolved = _resolve_day(
            int(match.group("month")),
            int(match.group("day")),
            years_back=1 if match.group("dimension") == "514" else 0,
        )
        if resolved is None:
            return None

        return {
            "kind": REQUEST_DAILY_HISTORY,
            "where": match.group("where"),
            "date": resolved.isoformat(),
            "value_wh": int(match.group("value")),
            "comparison_year": "previous"
            if match.group("dimension") == "514"
            else "current",
        }

    return None


def build_energy_response(request: str, raw_frames: list[str]) -> dict:
    """Shape raw WHO=18 replies into a stable service response."""
    parsed_frames = []
    for frame in raw_frames:
        parsed = parse_energy_frame(frame)
        if parsed is not None:
            parsed_frames.append(parsed)

    response = {
        "request": request,
        "raw_frames": raw_frames,
        "parsed_frames": parsed_frames,
    }

    if request in {
        REQUEST_ACTIVE_POWER,
        REQUEST_TOTAL,
        REQUEST_PARTIAL_DAILY,
        REQUEST_PARTIAL_MONTHLY,
        REQUEST_MONTHLY_HISTORY,
    }:
        response["record"] = parsed_frames[-1] if parsed_frames else None
        return response

    if request == REQUEST_HOURLY_HISTORY:
        samples = sorted(
            (
                item
                for item in parsed_frames
                if "hour" in item and "value_wh" in item
            ),
            key=lambda item: item["hour"],
        )
        totals = [
            item for item in parsed_frames if "daily_total_wh" in item
        ]
        response["date"] = (
            samples[-1]["date"]
            if samples
            else totals[-1]["date"]
            if totals
            else None
        )
        response["records"] = samples
        if samples:
            response["latest_hour"] = samples[-1]["hour"]
            response["latest_value_wh"] = samples[-1]["value_wh"]
        if totals:
            response["daily_total_wh"] = totals[-1]["daily_total_wh"]
        return response

    if request == REQUEST_DAILY_HISTORY:
        records = sorted(
            (
                item
                for item in parsed_frames
                if "date" in item and "value_wh" in item
            ),
            key=lambda item: item["date"],
        )
        response["records"] = records
        if records:
            response["latest_date"] = records[-1]["date"]
            response["latest_value_wh"] = records[-1]["value_wh"]
        return response

    if request == REQUEST_MONTHLY_AVERAGE_HOURLY:
        records = sorted(
            (
                item
                for item in parsed_frames
                if "hour" in item and "value_wh" in item
            ),
            key=lambda item: item["hour"],
        )
        totals = [
            item for item in parsed_frames if "average_total_wh" in item
        ]
        response["month"] = (
            records[-1]["month"]
            if records
            else totals[-1]["month"]
            if totals
            else None
        )
        response["records"] = records
        if totals:
            response["average_total_wh"] = totals[-1]["average_total_wh"]
        return response

    return response
