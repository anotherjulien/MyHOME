"""Helpers and state cache for MyHOME WHO=22 audio."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

ATTR_AREA = "area"
ATTR_BANDS = "bands"
ATTR_MM_TYPE = "mmtype"
ATTR_OPERATION = "operation"
ATTR_POINT = "point"
ATTR_QUERY_AFTER = "query_after"
ATTR_SOURCE = "source"
ATTR_SOURCE_ID = "source_id"
ATTR_STEP = "step"
ATTR_STATION = "station"
ATTR_VALUE = "value"
ATTR_VOLUME = "volume"
ATTR_ZONE_KEY = "zone_key"

SERVICE_AUDIO_GENERAL_COMMAND = "audio_general_command"
SERVICE_AUDIO_RADIO_COMMAND = "audio_radio_command"
SERVICE_AUDIO_SOURCE_COMMAND = "audio_source_command"
SERVICE_AUDIO_ZONE_COMMAND = "audio_zone_command"

RADIO_MODULATION_NAMES = {
    1: "FM",
    2: "AM-LW",
    3: "AM-MW",
    4: "AM-SW",
}
PRESET_ID_TO_NAME = {
    2: "Normal",
    3: "Dance",
    4: "Pop",
    5: "Rock",
    6: "Classic",
    7: "Techno",
    8: "Party",
    9: "Soft",
    10: "Full bass",
    11: "Full treble",
    **{value: f"User {value - 15}" for value in range(16, 26)},
}
PRESET_NAME_TO_ID = {
    name.lower(): preset_id for preset_id, name in PRESET_ID_TO_NAME.items()
}
SOURCE_ID_TO_NAME = {
    1: "Radio",
    2: "Touch",
    3: "RCA stereo",
    4: "RCA TV",
}
SOURCE_NAME_TO_ID = {name.lower(): source_id for source_id, name in SOURCE_ID_TO_NAME.items()}
EQUALIZATION_BAND_COUNTS = {
    1: 3,
    2: 3,
    3: 2,
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_source_id(source_id: int | str | None, source: str | None = None) -> int:
    if source_id is not None:
        source_id = int(source_id)
    elif source is not None:
        source_id = SOURCE_NAME_TO_ID.get(str(source).strip().lower())

    if source_id not in SOURCE_ID_TO_NAME:
        raise ValueError("Invalid or missing audio source.")
    return int(source_id)


def _normalize_ui_volume(volume: int | str | float | None) -> int:
    if volume is None:
        raise ValueError("Missing audio volume.")
    volume = int(round(float(volume)))
    return max(1, min(32, volume))


def _normalize_step(step: int | str | float | None) -> int:
    if step is None:
        return 1
    step = int(round(float(step)))
    return max(1, min(31, step))


def _normalize_audio_value(
    value: int | str | float | None,
    *,
    minimum: int = 0,
    maximum: int = 63,
) -> int:
    if value is None:
        raise ValueError("Missing audio value.")
    value = int(round(float(value)))
    if value < minimum or value > maximum:
        raise ValueError(f"Invalid audio value {value}.")
    return value


def _normalize_equalization_bands(
    bands: str | list[str] | tuple[str, ...] | None,
    *,
    expected_count: int,
) -> list[str]:
    if bands is None:
        raise ValueError("Missing equalization bands.")

    if isinstance(bands, str):
        normalized = str(bands).strip().replace(",", "*").replace(";", "*")
        parts = [part.strip() for part in normalized.split("*") if part.strip() != ""]
    else:
        parts = [str(part).strip() for part in bands if str(part).strip() != ""]

    if len(parts) != expected_count:
        raise ValueError(
            f"Invalid equalization band count {len(parts)}; expected {expected_count}."
        )

    for part in parts:
        int(part)
    return parts


def normalize_equalization_bands(
    equalization: int | str,
    bands: str | list[str] | tuple[str, ...] | None,
) -> list[str]:
    """Normalize a WHO=22 equalization payload for the requested slot."""
    equalization = int(equalization)
    if equalization not in EQUALIZATION_BAND_COUNTS:
        raise ValueError(f"Unsupported equalization slot `{equalization}`.")
    return _normalize_equalization_bands(
        bands,
        expected_count=EQUALIZATION_BAND_COUNTS[equalization],
    )


def _normalize_source_mmtype(mmtype: int | str | None) -> int:
    if mmtype is None:
        return 4
    mmtype = int(mmtype)
    if mmtype not in {1, 2, 3, 4, 11}:
        raise ValueError("Invalid audio mmtype.")
    return mmtype


def _normalize_area(area: int | str | None) -> int:
    if area is None:
        raise ValueError("Missing audio area.")
    area = int(area)
    if area < 0 or area > 10:
        raise ValueError("Invalid audio area.")
    return area


def _normalize_station(station: int | str | None) -> int:
    if station is None:
        raise ValueError("Missing audio station.")
    station = int(station)
    if station < 1 or station > 99:
        raise ValueError("Invalid audio station.")
    return station


def _zone_key(area: int | str, point: int | str) -> str:
    return f"{int(area)}_{int(point)}"


def format_radio_frequency(modulation: int | None, frequency: int | None) -> str | None:
    if modulation is None or frequency is None:
        return None
    if int(modulation) == 1:
        return f"{int(frequency) / 100:.2f} MHz"
    return f"{int(frequency)} kHz"


def preset_label_from_value(preset: int | None) -> str | None:
    if preset is None:
        return None
    return PRESET_ID_TO_NAME.get(int(preset), f"Preset {int(preset)}")


def preset_value_from_label(label: str | None) -> int:
    if label is None:
        raise ValueError("Missing preset label.")
    normalized = str(label).strip().lower()
    if normalized in PRESET_NAME_TO_ID:
        return PRESET_NAME_TO_ID[normalized]
    if normalized.startswith("preset "):
        return _normalize_audio_value(normalized.split(" ", 1)[1], minimum=2, maximum=25)
    raise ValueError(f"Unsupported audio preset `{label}`.")


def build_audio_zone_command(
    area: int | str,
    point: int | str,
    operation: str,
    *,
    source_id: int | str | None = None,
    source: str | None = None,
    volume: int | str | float | None = None,
    step: int | str | float | None = None,
    mmtype: int | str | None = None,
    value: int | str | float | None = None,
    bands: str | list[str] | tuple[str, ...] | None = None,
) -> str | list[str]:
    """Build a WHO=22 speaker-zone command."""
    area = int(area)
    point = int(point)
    operation = str(operation)

    if operation in {"on", "set_source"}:
        source_id = _normalize_source_id(source_id, source)
        return f"*22*35#4#{area}#{source_id}*3#{area}#{point}##"
    if operation == "follow_me":
        return f"*22*34#{_normalize_source_mmtype(mmtype)}#{area}*3#{area}#{point}##"
    if operation == "off":
        mmtype = 4 if mmtype is None else int(mmtype)
        return f"*22*0#{mmtype}#{area}*3#{area}#{point}##"
    if operation == "set_volume":
        volume_ui = _normalize_ui_volume(volume)
        return f"*#22*3#{area}#{point}*#1*{volume_ui - 1}##"
    if operation == "volume_up":
        return f"*22*3#{_normalize_step(step)}*3#{area}#{point}##"
    if operation == "volume_down":
        return f"*22*4#{_normalize_step(step)}*3#{area}#{point}##"
    if operation == "query_state":
        return [
            f"*#22*3#{area}#{point}*12##",
            f"*#22*3#{area}#{point}*1##",
        ]
    if operation == "query_device_state":
        return f"*#22*3#{area}#{point}*12##"
    if operation == "query_volume":
        return f"*#22*3#{area}#{point}*1##"
    if operation == "query_high_tones":
        return f"*#22*3#{area}#{point}*2##"
    if operation == "query_mid_tones":
        return f"*#22*3#{area}#{point}*3##"
    if operation == "query_low_tones":
        return f"*#22*3#{area}#{point}*4##"
    if operation == "query_balance":
        return f"*#22*3#{area}#{point}*17##"
    if operation == "query_3d":
        return f"*#22*3#{area}#{point}*18##"
    if operation == "query_preset":
        return f"*#22*3#{area}#{point}*19##"
    if operation == "query_loudness":
        return f"*#22*3#{area}#{point}*20##"
    if operation == "query_equalization_1":
        return f"*#22*5#3#{area}#{point}*21#1##"
    if operation == "query_equalization_2":
        return f"*#22*5#3#{area}#{point}*21#2##"
    if operation == "query_equalization_3":
        return f"*#22*5#3#{area}#{point}*21#3##"
    if operation == "set_equalization_1":
        return (
            f"*#22*5#3#{area}#{point}*#21#1*"
            f"{'*'.join(normalize_equalization_bands(1, bands))}##"
        )
    if operation == "set_equalization_2":
        return (
            f"*#22*5#3#{area}#{point}*#21#2*"
            f"{'*'.join(normalize_equalization_bands(2, bands))}##"
        )
    if operation == "set_equalization_3":
        return (
            f"*#22*5#3#{area}#{point}*#21#3*"
            f"{'*'.join(normalize_equalization_bands(3, bands))}##"
        )
    if operation == "set_high_tones":
        return f"*#22*3#{area}#{point}*#2*{_normalize_audio_value(value)}##"
    if operation == "set_mid_tones":
        return f"*#22*3#{area}#{point}*#3*{_normalize_audio_value(value)}##"
    if operation == "set_low_tones":
        return f"*#22*3#{area}#{point}*#4*{_normalize_audio_value(value)}##"
    if operation == "set_device_state":
        return (
            f"*#22*3#{area}#{point}*#12*"
            f"{_normalize_audio_value(value, minimum=0, maximum=2)}*{_normalize_source_mmtype(mmtype)}##"
        )
    if operation == "set_balance":
        return f"*#22*3#{area}#{point}*#17*{_normalize_audio_value(value, minimum=1, maximum=63)}##"
    if operation == "set_3d":
        return f"*#22*3#{area}#{point}*#18*{_normalize_audio_value(value, minimum=0, maximum=10)}##"
    if operation == "set_preset":
        return f"*#22*3#{area}#{point}*#19*{_normalize_audio_value(value, minimum=2, maximum=25)}##"
    if operation == "set_loudness":
        return f"*#22*3#{area}#{point}*#20*{_normalize_audio_value(value, minimum=0, maximum=1)}##"
    if operation == "low_tones_up":
        return f"*22*36#{_normalize_audio_value(value, minimum=1, maximum=63)}*3#{area}#{point}##"
    if operation == "low_tones_down":
        return f"*22*37#{_normalize_audio_value(value, minimum=1, maximum=63)}*3#{area}#{point}##"
    if operation == "mid_tones_up":
        return f"*22*38#{_normalize_audio_value(value, minimum=1, maximum=63)}*3#{area}#{point}##"
    if operation == "mid_tones_down":
        return f"*22*39#{_normalize_audio_value(value, minimum=1, maximum=63)}*3#{area}#{point}##"
    if operation == "high_tones_up":
        return f"*22*40#{_normalize_audio_value(value, minimum=1, maximum=63)}*3#{area}#{point}##"
    if operation == "high_tones_down":
        return f"*22*41#{_normalize_audio_value(value, minimum=1, maximum=63)}*3#{area}#{point}##"
    if operation == "balance_left":
        return f"*22*42#{_normalize_audio_value(value, minimum=1, maximum=63)}*3#{area}#{point}##"
    if operation == "balance_right":
        return f"*22*43#{_normalize_audio_value(value, minimum=1, maximum=63)}*3#{area}#{point}##"
    if operation == "next_preset":
        return f"*22*55##3#{area}#{point}##"
    if operation == "previous_preset":
        return f"*22*56##3#{area}#{point}##"

    raise ValueError(f"Unsupported audio zone operation `{operation}`.")


def build_audio_general_command(
    operation: str,
    *,
    source_id: int | str | None = None,
    source: str | None = None,
    step: int | str | float | None = None,
) -> str:
    """Build a general WHO=22 command."""
    operation = str(operation)

    if operation in {"on", "set_source"}:
        source_id = _normalize_source_id(source_id, source)
        return f"*22*22#4#0*2#{source_id}##"
    if operation == "off":
        return "*22*0#4#0*4#0##"
    if operation == "volume_up":
        return f"*22*3#{_normalize_step(step)}*4#0##"
    if operation == "volume_down":
        return f"*22*4#{_normalize_step(step)}*4#0##"

    raise ValueError(f"Unsupported audio general operation `{operation}`.")


def build_audio_source_command(
    operation: str,
    *,
    source_id: int | str,
    area: int | str | None = None,
    mmtype: int | str | None = None,
    step: int | str | float | None = None,
    station: int | str | None = None,
) -> str | list[str]:
    """Build a WHO=22 source command or request."""
    operation = str(operation)
    source_id = _normalize_source_id(source_id)

    if operation == "on":
        return (
            f"*22*1#{_normalize_source_mmtype(mmtype)}#{_normalize_area(area)}"
            f"*2#{source_id}##"
        )
    if operation == "off":
        return (
            f"*22*0#{_normalize_source_mmtype(mmtype)}#{_normalize_area(area)}"
            f"*2#{source_id}##"
        )
    if operation == "goto_area":
        return (
            f"*22*22#{_normalize_source_mmtype(mmtype)}#{_normalize_area(area)}"
            f"*2#{source_id}##"
        )
    if operation == "frequency_up":
        return f"*22*5#{_normalize_step(step)}*2#{source_id}##"
    if operation == "frequency_down":
        return f"*22*6#{_normalize_step(step)}*2#{source_id}##"
    if operation == "next_station":
        return f"*22*9#*2#{source_id}##"
    if operation == "previous_station":
        return f"*22*10#*2#{source_id}##"
    if operation == "next_track":
        return f"*22*11#{_normalize_step(step)}*2#{source_id}##"
    if operation == "previous_track":
        return f"*22*12#{_normalize_step(step)}*2#{source_id}##"
    if operation == "start_rds":
        return f"*22*31#{source_id}##"
    if operation == "stop_rds":
        return f"*22*32#{source_id}##"
    if operation == "store_station":
        return f"*22*33#{_normalize_station(station)}*2#{source_id}##"
    if operation == "query_state":
        return f"*#22*2#{source_id}##"
    if operation == "query_frequency":
        return f"*#22*5#2#{source_id}*5##"
    if operation == "query_station":
        return f"*#22*5#2#{source_id}*6##"
    if operation == "query_memorized_station":
        return f"*#22*5#2#{source_id}*11##"
    if operation == "query_device_state":
        return f"*#22*5#2#{source_id}*12##"
    if operation == "query_rds":
        return f"*#22*2#{source_id}*10##"
    if operation == "query_status":
        return [
            f"*#22*2#{source_id}##",
            f"*#22*5#2#{source_id}*5##",
            f"*#22*5#2#{source_id}*6##",
            f"*#22*5#2#{source_id}*11##",
            f"*#22*5#2#{source_id}*12##",
            f"*#22*2#{source_id}*10##",
        ]

    raise ValueError(f"Unsupported audio source operation `{operation}`.")


def build_audio_radio_command(operation: str) -> str | list[str]:
    """Build a radio-source WHO=22 command."""
    operation = str(operation)
    if operation == "query_status":
        return build_audio_source_command("query_status", source_id=1)
    if operation == "query_rds":
        return build_audio_source_command("query_rds", source_id=1)
    if operation == "frequency_up":
        return "*22*5#*2#1##"
    if operation == "frequency_down":
        return "*22*6#*2#1##"
    if operation == "next_station":
        return "*22*9#*2#1##"
    if operation == "previous_station":
        return "*22*10#*2#1##"
    raise ValueError(f"Unsupported audio radio operation `{operation}`.")


@dataclass
class AudioZoneState:
    area: int
    point: int
    zone_key: str
    is_on: bool | None = None
    state: str | None = None
    device_state: int | None = None
    mmtype: int | None = None
    source_id: int | None = None
    source: str | None = None
    volume_raw: int | None = None
    volume_ui: int | None = None
    high_tones: int | None = None
    mid_tones: int | None = None
    low_tones: int | None = None
    balance: int | None = None
    three_d: int | None = None
    preset: int | None = None
    loudness: bool | None = None
    equalization_1: list[str] | None = None
    equalization_2: list[str] | None = None
    equalization_3: list[str] | None = None
    last_update: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AudioRadioState:
    source_id: int = 1
    band: str | None = None
    modulation: int | None = None
    frequency: int | None = None
    frequency_label: str | None = None
    station: int | None = None
    rds_text: str | None = None
    rds_segments: list[str] | None = None
    last_update: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AudioSourceState:
    source_id: int
    is_on: bool | None = None
    state: str | None = None
    device_state: int | None = None
    mmtype: int | None = None
    area: int | None = None
    modulation: int | None = None
    band: str | None = None
    frequency: int | None = None
    frequency_label: str | None = None
    station: int | None = None
    rds_text: str | None = None
    rds_segments: list[str] | None = None
    last_update: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class MyHOMEAudioState:
    """Cache the last known WHO=22 state seen on the bus."""

    def __init__(self) -> None:
        self.zones: dict[str, AudioZoneState] = {}
        self.radio = AudioRadioState()
        self.sources: dict[int, AudioSourceState] = {}

    def _ensure_zone(self, area: int | str, point: int | str) -> AudioZoneState:
        area = int(area)
        point = int(point)
        key = _zone_key(area, point)
        if key not in self.zones:
            self.zones[key] = AudioZoneState(area=area, point=point, zone_key=key)
        return self.zones[key]

    def _ensure_source(self, source_id: int | str) -> AudioSourceState:
        source_id = int(source_id)
        if source_id not in self.sources:
            self.sources[source_id] = AudioSourceState(source_id=source_id)
        return self.sources[source_id]

    def handle_feedback(self, data: dict | None) -> dict | None:
        if not data:
            return None

        kind = data.get("kind")
        timestamp = _utcnow()

        if kind == "speaker_state":
            zone = self._ensure_zone(data["area"], data["point"])
            zone.device_state = data.get("device_state")
            zone.mmtype = data.get("mmtype")
            zone.state = data.get("on_state")
            zone.is_on = data.get("on_state") == "on"
            zone.last_update = timestamp
            return zone.to_dict()

        if kind == "speaker_volume":
            zone = self._ensure_zone(data["area"], data["point"])
            volume_raw = int(data["volume"])
            zone.volume_raw = volume_raw
            zone.volume_ui = max(1, min(32, volume_raw + 1))
            zone.last_update = timestamp
            return zone.to_dict()

        if kind in {"speaker_high_tones", "speaker_mid_tones", "speaker_low_tones"}:
            zone = self._ensure_zone(data["area"], data["point"])
            if kind == "speaker_high_tones":
                zone.high_tones = int(data["value"])
            elif kind == "speaker_mid_tones":
                zone.mid_tones = int(data["value"])
            else:
                zone.low_tones = int(data["value"])
            zone.last_update = timestamp
            return zone.to_dict()

        if kind == "speaker_balance":
            zone = self._ensure_zone(data["area"], data["point"])
            zone.balance = int(data["value"])
            zone.last_update = timestamp
            return zone.to_dict()

        if kind == "speaker_3d":
            zone = self._ensure_zone(data["area"], data["point"])
            zone.three_d = int(data["value"])
            zone.last_update = timestamp
            return zone.to_dict()

        if kind == "speaker_preset":
            zone = self._ensure_zone(data["area"], data["point"])
            zone.preset = int(data["value"])
            zone.last_update = timestamp
            return zone.to_dict()

        if kind == "speaker_loudness":
            zone = self._ensure_zone(data["area"], data["point"])
            zone.loudness = int(data["value"]) == 1
            zone.last_update = timestamp
            return zone.to_dict()

        if kind == "speaker_equalization":
            zone = self._ensure_zone(data["area"], data["point"])
            equalization = int(data["equalization"])
            bands = [str(band) for band in data.get("bands", [])]
            if equalization == 1:
                zone.equalization_1 = bands
            elif equalization == 2:
                zone.equalization_2 = bands
            elif equalization == 3:
                zone.equalization_3 = bands
            zone.last_update = timestamp
            return zone.to_dict()

        if kind == "area_source":
            area = int(data["area"])
            source_id = int(data["source_id"])
            source_name = SOURCE_ID_TO_NAME.get(source_id, str(source_id))
            source_state = self._ensure_source(source_id)
            source_state.area = area
            source_state.last_update = timestamp
            updated = None
            for zone in self.zones.values():
                if zone.area != area:
                    continue
                zone.source_id = source_id
                zone.source = source_name
                zone.mmtype = data.get("mmtype", zone.mmtype)
                zone.last_update = timestamp
                updated = zone.to_dict()
            return updated or {
                "area": area,
                "source_id": source_id,
                "source": source_name,
                "last_update": timestamp,
            }

        if kind == "source_device_state":
            source_state = self._ensure_source(data["source_id"])
            source_state.device_state = int(data["device_state"])
            source_state.mmtype = int(data["mmtype"])
            source_state.is_on = source_state.device_state != 0
            source_state.state = "on" if source_state.is_on else "off"
            source_state.last_update = timestamp
            if source_state.source_id == self.radio.source_id:
                self.radio.last_update = timestamp
            return source_state.to_dict()

        if kind in {"source_frequency_station", "source_frequency"}:
            modulation = int(data["modulation"])
            frequency = int(data["frequency"])
            source_state = self._ensure_source(data["source_id"])
            source_state.modulation = modulation
            source_state.band = RADIO_MODULATION_NAMES.get(modulation, str(modulation))
            source_state.frequency = frequency
            source_state.frequency_label = format_radio_frequency(modulation, frequency)
            source_state.last_update = timestamp
            self.radio.modulation = modulation
            self.radio.band = RADIO_MODULATION_NAMES.get(modulation, str(modulation))
            self.radio.frequency = frequency
            self.radio.frequency_label = format_radio_frequency(modulation, frequency)
            self.radio.last_update = timestamp
            if "station" in data:
                source_state.station = int(data["station"])
                self.radio.station = int(data["station"])
            return source_state.to_dict()

        if kind == "source_station":
            source_state = self._ensure_source(data["source_id"])
            source_state.station = int(data["station"])
            source_state.last_update = timestamp
            self.radio.station = int(data["station"])
            self.radio.last_update = timestamp
            return source_state.to_dict()

        if kind == "source_rds":
            source_state = self._ensure_source(data["source_id"])
            source_state.rds_segments = list(data.get("segments", []))
            source_state.rds_text = data.get("text")
            source_state.last_update = timestamp
            if source_state.source_id == self.radio.source_id:
                self.radio.rds_segments = list(data.get("segments", []))
                self.radio.rds_text = data.get("text")
                self.radio.last_update = timestamp
            return source_state.to_dict()

        return None

    def handle_command(self, data: dict | None) -> dict | None:
        if not data:
            return None

        kind = data.get("kind")
        timestamp = _utcnow()

        if kind == "audio_source_command":
            zone = self._ensure_zone(data["area"], data["point"])
            source_id = int(data["source_id"])
            zone.source_id = source_id
            zone.source = SOURCE_ID_TO_NAME.get(source_id, str(source_id))
            zone.mmtype = data.get("mmtype", zone.mmtype)
            zone.is_on = True
            zone.state = "on"
            zone.last_update = timestamp
            return zone.to_dict()

        if kind == "audio_off_command":
            zone = self._ensure_zone(data["area"], data["point"])
            zone.is_on = False
            zone.state = "off"
            zone.mmtype = data.get("mmtype", zone.mmtype)
            zone.last_update = timestamp
            return zone.to_dict()

        if kind == "audio_volume_set":
            zone = self._ensure_zone(data["area"], data["point"])
            zone.volume_raw = int(data["volume"])
            zone.volume_ui = max(1, min(32, zone.volume_raw + 1))
            zone.last_update = timestamp
            return zone.to_dict()

        if kind in {"audio_volume_up", "audio_volume_down"}:
            zone = self._ensure_zone(data["area"], data["point"])
            if zone.volume_raw is not None:
                delta = int(data["step"])
                if kind == "audio_volume_down":
                    delta *= -1
                zone.volume_raw = max(0, min(31, zone.volume_raw + delta))
                zone.volume_ui = zone.volume_raw + 1
            zone.last_update = timestamp
            return zone.to_dict()

        return None

    def zone_snapshot(self, area: int | str, point: int | str) -> dict | None:
        zone = self.zones.get(_zone_key(area, point))
        return None if zone is None else zone.to_dict()

    def source_snapshot(self, source_id: int | str) -> dict | None:
        source = self.sources.get(int(source_id))
        return None if source is None else source.to_dict()

    def radio_snapshot(self) -> dict:
        snapshot = self.radio.to_dict()
        source_state = self.source_snapshot(self.radio.source_id)
        if source_state is not None:
            snapshot.update({k: v for k, v in source_state.items() if v is not None})
        return snapshot
