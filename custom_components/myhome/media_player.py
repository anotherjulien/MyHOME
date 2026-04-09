"""Native MyHOME WHO=22 media players."""

from __future__ import annotations

from homeassistant.components.media_player import (
    DOMAIN as PLATFORM,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
)
from homeassistant.components.media_player.const import (
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.restore_state import RestoreEntity

from .audio import (
    PRESET_ID_TO_NAME,
    SOURCE_ID_TO_NAME,
    build_audio_source_command,
    build_audio_zone_command,
    preset_label_from_value,
    preset_value_from_label,
)
from .const import (
    CONF_DEVICE_MODEL,
    CONF_ENTITIES,
    CONF_ENTITY,
    CONF_MANUFACTURER,
    CONF_PLATFORMS,
    DOMAIN,
)

ATTR_AREA = "area"
ATTR_POINT = "point"

DEVICE_ID_PREFIX = "audio-zone-"
DEFAULT_AUDIO_MEDIA_PLAYER_MODEL = "MyHOME Sound Diffusion Speaker"
DEFAULT_AUDIO_MEDIA_PLAYER_NAME = "Audio area {area} point {point}"
AUDIO_SOUND_MODE_LIST = [
    PRESET_ID_TO_NAME[preset_id]
    for preset_id in sorted(PRESET_ID_TO_NAME)
]


def _audio_zone_device_id(area: int | str, point: int | str) -> str:
    return f"{DEVICE_ID_PREFIX}{int(area)}_{int(point)}"


def _default_audio_zone_name(area: int | str, point: int | str) -> str:
    return DEFAULT_AUDIO_MEDIA_PLAYER_NAME.format(area=int(area), point=int(point))


def ensure_media_player_platform_config(gateway_config: dict) -> None:
    """Inject the dynamic media_player platform into the gateway config."""
    gateway_config.setdefault(CONF_PLATFORMS, {}).setdefault(PLATFORM, {})


def ensure_audio_zone_media_player_config(
    gateway_config: dict,
    area: int | str,
    point: int | str,
    *,
    name: str | None = None,
) -> tuple[str, dict]:
    """Ensure the synthetic media_player config entry exists for an audio zone."""
    area = int(area)
    point = int(point)
    platform_config = gateway_config.setdefault(CONF_PLATFORMS, {}).setdefault(
        PLATFORM,
        {},
    )
    device_id = _audio_zone_device_id(area, point)
    device_config = platform_config.setdefault(
        device_id,
        {
            CONF_NAME: name or _default_audio_zone_name(area, point),
            ATTR_AREA: area,
            ATTR_POINT: point,
            CONF_MANUFACTURER: "BTicino S.p.A.",
            CONF_DEVICE_MODEL: DEFAULT_AUDIO_MEDIA_PLAYER_MODEL,
            CONF_ENTITIES: {},
        },
    )
    device_config.setdefault(CONF_NAME, name or _default_audio_zone_name(area, point))
    device_config.setdefault(ATTR_AREA, area)
    device_config.setdefault(ATTR_POINT, point)
    device_config.setdefault(CONF_MANUFACTURER, "BTicino S.p.A.")
    device_config.setdefault(CONF_DEVICE_MODEL, DEFAULT_AUDIO_MEDIA_PLAYER_MODEL)
    device_config.setdefault(CONF_ENTITIES, {})
    return device_id, device_config


def restore_media_player_platform_config(
    gateway_config: dict,
    entity_entries: list,
    gateway_mac: str,
) -> None:
    """Re-seed dynamic audio media players from the entity registry."""
    gateway_mac = str(gateway_mac).lower()
    prefix = f"{gateway_mac}-{DEVICE_ID_PREFIX}"

    for entry in entity_entries:
        if entry.platform != DOMAIN or entry.domain != PLATFORM:
            continue
        if not entry.unique_id or not str(entry.unique_id).startswith(prefix):
            continue

        suffix = str(entry.unique_id)[len(prefix) :]
        try:
            area, point = suffix.split("_", 1)
            ensure_audio_zone_media_player_config(
                gateway_config,
                int(area),
                int(point),
            )
        except (TypeError, ValueError):
            continue


async def async_setup_entry(hass, config_entry, async_add_entities):
    gateway_data = hass.data[DOMAIN][config_entry.data[CONF_MAC]]
    gateway_handler = gateway_data[CONF_ENTITY]
    configured_entities = gateway_data[CONF_PLATFORMS].setdefault(PLATFORM, {})

    manager = MyHOMEAudioMediaPlayerManager(
        hass=hass,
        gateway=gateway_handler,
        gateway_data=gateway_data,
        async_add_entities=async_add_entities,
    )
    gateway_data["audio_media_player_manager"] = manager

    initial_entities = []
    for device_id, device_config in configured_entities.items():
        entity = manager.get_or_create_entity(
            device_id=device_id,
            device_config=device_config,
        )
        if entity is not None:
            initial_entities.append(entity)

    if initial_entities:
        async_add_entities(initial_entities)

    manager.async_start()
    return True


async def async_unload_entry(hass, config_entry):
    gateway_data = hass.data[DOMAIN][config_entry.data[CONF_MAC]]
    manager = gateway_data.pop("audio_media_player_manager", None)
    if manager is not None:
        manager.async_unload()
    return True


class MyHOMEAudioMediaPlayerManager:
    """Create and update synthetic WHO=22 media players from bus state."""

    def __init__(self, hass, gateway, gateway_data: dict, async_add_entities) -> None:
        self._hass = hass
        self._gateway_handler = gateway
        self._gateway_data = gateway_data
        self._async_add_entities = async_add_entities
        self._entities: dict[str, MyHOMEAudioZoneMediaPlayer] = {}
        self._unsubs: list = []

    def get_or_create_entity(
        self,
        *,
        device_id: str,
        device_config: dict,
    ) -> MyHOMEAudioZoneMediaPlayer | None:
        if device_id in self._entities:
            return self._entities[device_id]

        area = device_config.get(ATTR_AREA)
        point = device_config.get(ATTR_POINT)
        if area is None or point is None:
            return None

        entity = MyHOMEAudioZoneMediaPlayer(
            hass=self._hass,
            gateway=self._gateway_handler,
            device_id=device_id,
            name=device_config.get(CONF_NAME),
            area=area,
            point=point,
            manufacturer=device_config.get(CONF_MANUFACTURER),
            model=device_config.get(CONF_DEVICE_MODEL),
        )
        self._entities[device_id] = entity
        return entity

    @callback
    def async_start(self) -> None:
        self._unsubs.append(
            self._hass.bus.async_listen(
                "myhome_audio_feedback_event",
                self._handle_feedback_event,
            )
        )
        self._unsubs.append(
            self._hass.bus.async_listen(
                "myhome_audio_command_event",
                self._handle_command_event,
            )
        )

    @callback
    def async_unload(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @callback
    def _handle_feedback_event(self, event) -> None:
        data = dict(event.data)
        if data.get("gateway_mac") != self._gateway_handler.mac:
            return

        self._gateway_handler.audio.handle_feedback(data)
        self._process_audio_event(data)

    @callback
    def _handle_command_event(self, event) -> None:
        data = dict(event.data)
        if data.get("gateway_mac") != self._gateway_handler.mac:
            return

        self._gateway_handler.audio.handle_command(data)
        self._process_audio_event(data)

    @callback
    def _process_audio_event(self, data: dict) -> None:
        if data.get("area") is not None and data.get("point") is not None:
            entity = self._ensure_entity(data["area"], data["point"])
            entity.async_refresh_from_cache()
            return

        if data.get("kind") == "area_source":
            area = int(data["area"])
            for entity in self._entities.values():
                if entity.area == area:
                    entity.async_refresh_from_cache()
            return

        if data.get("kind", "").startswith("source_"):
            source_id = int(data["source_id"])
            for entity in self._entities.values():
                snapshot = self._gateway_handler.audio.zone_snapshot(
                    entity.area,
                    entity.point,
                )
                if snapshot and snapshot.get("source_id") == source_id:
                    entity.async_refresh_from_cache()

    def _ensure_entity(
        self,
        area: int | str,
        point: int | str,
    ) -> MyHOMEAudioZoneMediaPlayer:
        device_id = _audio_zone_device_id(area, point)
        if device_id in self._entities:
            return self._entities[device_id]

        device_id, device_config = ensure_audio_zone_media_player_config(
            self._gateway_data,
            area,
            point,
        )
        entity = self.get_or_create_entity(
            device_id=device_id,
            device_config=device_config,
        )
        self._async_add_entities([entity])
        return entity


class MyHOMEAudioZoneMediaPlayer(MediaPlayerEntity, RestoreEntity):
    """Represent a synthetic WHO=22 speaker zone as a native media player."""

    def __init__(
        self,
        hass,
        gateway,
        device_id: str,
        name: str | None,
        area: int | str,
        point: int | str,
        manufacturer: str | None,
        model: str | None,
    ) -> None:
        self._hass = hass
        self._gateway_handler = gateway
        self._platform = PLATFORM
        self._device_id = device_id
        self._area = int(area)
        self._point = int(point)
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._model = model or DEFAULT_AUDIO_MEDIA_PLAYER_MODEL

        self._attr_has_entity_name = False
        self._attr_name = name or _default_audio_zone_name(area, point)
        self._attr_unique_id = f"{gateway.mac}-{device_id}"
        self._attr_should_poll = False
        self._attr_device_class = MediaPlayerDeviceClass.SPEAKER
        self._attr_supported_features = (
            MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.SELECT_SOUND_MODE
            | MediaPlayerEntityFeature.NEXT_TRACK
            | MediaPlayerEntityFeature.PREVIOUS_TRACK
        )
        self._attr_source_list = list(SOURCE_ID_TO_NAME.values())
        self._attr_sound_mode_list = AUDIO_SOUND_MODE_LIST
        self._attr_state = MediaPlayerState.OFF
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{gateway.mac}-{device_id}")},
            "name": self._attr_name,
            "manufacturer": self._manufacturer,
            "model": self._model,
            "via_device": (DOMAIN, self._gateway_handler.unique_id),
        }
        self._attr_extra_state_attributes = {
            ATTR_AREA: self._area,
            ATTR_POINT: self._point,
        }

    @property
    def area(self) -> int:
        return self._area

    @property
    def point(self) -> int:
        return self._point

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._platform] = self
        self._sync_from_cache()

        if self._gateway_handler.audio.zone_snapshot(self._area, self._point) is None:
            if (last_state := await self.async_get_last_state()) is not None:
                try:
                    self._attr_state = MediaPlayerState(last_state.state)
                except ValueError:
                    self._attr_state = MediaPlayerState.OFF
                self._attr_source = last_state.attributes.get("source")
                self._attr_volume_level = last_state.attributes.get("volume_level")
                self._attr_media_title = last_state.attributes.get("media_title")
                self._attr_sound_mode = last_state.attributes.get("sound_mode")
                self._attr_extra_state_attributes = {
                    k: v
                    for k, v in last_state.attributes.items()
                    if k
                    not in {
                        "friendly_name",
                        "supported_features",
                        "entity_picture",
                        "icon",
                        "source",
                        "source_list",
                        "volume_level",
                        "media_title",
                        "sound_mode",
                        "sound_mode_list",
                    }
                }

    async def async_will_remove_from_hass(self) -> None:
        if (
            self._platform
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES][self._platform]

    @callback
    def async_refresh_from_cache(self) -> None:
        self._sync_from_cache()
        self.async_write_ha_state()

    def _sync_from_cache(self) -> None:
        snapshot = self._gateway_handler.audio.zone_snapshot(self._area, self._point)
        if snapshot is None:
            return

        source_snapshot = None
        source_id = snapshot.get("source_id")
        if source_id is not None:
            source_snapshot = (
                self._gateway_handler.audio.radio_snapshot()
                if int(source_id) == 1
                else self._gateway_handler.audio.source_snapshot(source_id)
            )

        is_on = snapshot.get("is_on")
        if is_on is True:
            self._attr_state = (
                MediaPlayerState.PLAYING
                if snapshot.get("source_id") is not None
                else MediaPlayerState.ON
            )
        elif is_on is False:
            self._attr_state = MediaPlayerState.OFF

        volume_raw = snapshot.get("volume_raw")
        self._attr_volume_level = (
            int(volume_raw) / 31 if volume_raw is not None else None
        )
        self._attr_source = snapshot.get("source")
        self._attr_sound_mode = preset_label_from_value(snapshot.get("preset"))
        self._attr_media_title = self._build_media_title(snapshot, source_snapshot)
        self._attr_extra_state_attributes = {
            ATTR_AREA: self._area,
            ATTR_POINT: self._point,
            "zone_key": snapshot.get("zone_key"),
            "device_state": snapshot.get("device_state"),
            "mmtype": snapshot.get("mmtype"),
            "source_id": snapshot.get("source_id"),
            "volume_raw": volume_raw,
            "volume_ui": snapshot.get("volume_ui"),
            "high_tones": snapshot.get("high_tones"),
            "mid_tones": snapshot.get("mid_tones"),
            "low_tones": snapshot.get("low_tones"),
            "balance": snapshot.get("balance"),
            "three_d": snapshot.get("three_d"),
            "preset": snapshot.get("preset"),
            "loudness": snapshot.get("loudness"),
            "equalization_1": snapshot.get("equalization_1"),
            "equalization_2": snapshot.get("equalization_2"),
            "equalization_3": snapshot.get("equalization_3"),
            "last_update": snapshot.get("last_update"),
        }
        if source_snapshot is not None:
            self._attr_extra_state_attributes.update(
                {
                    "source_state": source_snapshot.get("state"),
                    "source_area": source_snapshot.get("area"),
                    "modulation": source_snapshot.get("modulation"),
                    "band": source_snapshot.get("band"),
                    "frequency": source_snapshot.get("frequency"),
                    "frequency_label": source_snapshot.get("frequency_label"),
                    "station": source_snapshot.get("station"),
                    "rds_text": source_snapshot.get("rds_text"),
                    "rds_segments": source_snapshot.get("rds_segments"),
                }
            )

    def _build_media_title(
        self,
        snapshot: dict,
        source_snapshot: dict | None,
    ) -> str | None:
        if not source_snapshot:
            return snapshot.get("source")

        if source_snapshot.get("rds_text"):
            return source_snapshot.get("rds_text")
        if source_snapshot.get("frequency_label"):
            return source_snapshot.get("frequency_label")
        if source_snapshot.get("station") is not None:
            return f"Station {source_snapshot['station']}"
        return snapshot.get("source")

    async def async_turn_on(self) -> None:
        source_id = self._attr_extra_state_attributes.get("source_id") or 1
        await self._gateway_handler.send(
            build_audio_zone_command(
                self._area,
                self._point,
                "on",
                source_id=source_id,
            )
        )
        self._gateway_handler.audio.handle_command(
            {
                "kind": "audio_source_command",
                "area": self._area,
                "point": self._point,
                "source_id": int(source_id),
                "mmtype": 4,
            }
        )
        self.async_refresh_from_cache()

    async def async_turn_off(self) -> None:
        await self._gateway_handler.send(
            build_audio_zone_command(
                self._area,
                self._point,
                "off",
            )
        )
        self._gateway_handler.audio.handle_command(
            {
                "kind": "audio_off_command",
                "area": self._area,
                "point": self._point,
                "mmtype": 4,
            }
        )
        self.async_refresh_from_cache()

    async def async_select_source(self, source: str) -> None:
        source_id = next(
            (
                configured_source_id
                for configured_source_id, configured_source_name in SOURCE_ID_TO_NAME.items()
                if configured_source_name == source
            ),
            None,
        )
        if source_id is None:
            raise ValueError(f"Unsupported source `{source}`.")

        await self._gateway_handler.send(
            build_audio_zone_command(
                self._area,
                self._point,
                "set_source",
                source_id=source_id,
            )
        )
        self._gateway_handler.audio.handle_command(
            {
                "kind": "audio_source_command",
                "area": self._area,
                "point": self._point,
                "source_id": int(source_id),
                "mmtype": 4,
            }
        )
        self.async_refresh_from_cache()

    async def async_set_volume_level(self, volume: float) -> None:
        volume_ui = max(1, min(32, int(round(float(volume) * 31)) + 1))
        await self._gateway_handler.send(
            build_audio_zone_command(
                self._area,
                self._point,
                "set_volume",
                volume=volume_ui,
            )
        )
        self._gateway_handler.audio.handle_command(
            {
                "kind": "audio_volume_set",
                "area": self._area,
                "point": self._point,
                "volume": volume_ui - 1,
            }
        )
        self.async_refresh_from_cache()

    async def async_volume_up(self) -> None:
        await self._gateway_handler.send(
            build_audio_zone_command(
                self._area,
                self._point,
                "volume_up",
                step=1,
            )
        )
        self._gateway_handler.audio.handle_command(
            {
                "kind": "audio_volume_up",
                "area": self._area,
                "point": self._point,
                "step": 1,
            }
        )
        self.async_refresh_from_cache()

    async def async_volume_down(self) -> None:
        await self._gateway_handler.send(
            build_audio_zone_command(
                self._area,
                self._point,
                "volume_down",
                step=1,
            )
        )
        self._gateway_handler.audio.handle_command(
            {
                "kind": "audio_volume_down",
                "area": self._area,
                "point": self._point,
                "step": 1,
            }
        )
        self.async_refresh_from_cache()

    async def async_media_next_track(self) -> None:
        source_id = int(self._attr_extra_state_attributes.get("source_id") or 1)
        operation = "next_station" if source_id == 1 else "next_track"
        await self._gateway_handler.send(
            build_audio_source_command(
                operation,
                source_id=source_id,
            )
        )

    async def async_media_previous_track(self) -> None:
        source_id = int(self._attr_extra_state_attributes.get("source_id") or 1)
        operation = "previous_station" if source_id == 1 else "previous_track"
        await self._gateway_handler.send(
            build_audio_source_command(
                operation,
                source_id=source_id,
            )
        )

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        preset = preset_value_from_label(sound_mode)
        await self._gateway_handler.send(
            build_audio_zone_command(
                self._area,
                self._point,
                "set_preset",
                value=preset,
            )
        )
        self._gateway_handler.audio.handle_feedback(
            {
                "kind": "speaker_preset",
                "area": self._area,
                "point": self._point,
                "value": preset,
            }
        )
        self.async_refresh_from_cache()
