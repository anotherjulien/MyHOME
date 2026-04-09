"""Support for MyHome text entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .gateway import MyHOMEGatewayHandler

from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER
from homeassistant.components.text import (
    DOMAIN as PLATFORM,
    RestoreText,
    TextMode,
)
from homeassistant.const import (
    CONF_MAC,
    CONF_NAME,
    EntityCategory,
)
from homeassistant.core import callback

from .audio import build_audio_zone_command, normalize_equalization_bands
from .const import (
    CONF_DEVICE_MODEL,
    CONF_ENTITY,
    CONF_ENTITIES,
    CONF_ENTITY_NAME,
    CONF_MANUFACTURER,
    CONF_OPERATION,
    CONF_PLATFORMS,
    CONF_WHERE,
    CONF_WHO,
    DOMAIN,
)
from .media_player import ATTR_AREA as AUDIO_AREA_ATTR, ATTR_POINT as AUDIO_POINT_ATTR
from .myhome_device import MyHOMEEntity


def _equalization_pattern(band_count: int) -> str:
    return rf"^-?\d+\s*(?:[,;*]\s*-?\d+\s*){{{band_count - 1}}}$"


_AUDIO_TEXT_ENTITY_DEFINITIONS = {
    "equalization_1": {
        "name": "Equalization 1 bands",
        "icon": "mdi:equalizer",
        "equalization": 1,
        "query_operation": "query_equalization_1",
        "set_operation": "set_equalization_1",
        "snapshot_field": "equalization_1",
        "pattern": _equalization_pattern(3),
    },
    "equalization_2": {
        "name": "Equalization 2 bands",
        "icon": "mdi:equalizer-outline",
        "equalization": 2,
        "query_operation": "query_equalization_2",
        "set_operation": "set_equalization_2",
        "snapshot_field": "equalization_2",
        "pattern": _equalization_pattern(3),
    },
    "equalization_3": {
        "name": "Equalization 3 bands",
        "icon": "mdi:equalizer-outline",
        "equalization": 3,
        "query_operation": "query_equalization_3",
        "set_operation": "set_equalization_3",
        "snapshot_field": "equalization_3",
        "pattern": _equalization_pattern(2),
    },
}


def _ensure_audio_text_configs(gateway_data: dict) -> None:
    text_config = gateway_data.setdefault(CONF_PLATFORMS, {}).setdefault(PLATFORM, {})
    media_players = gateway_data.get(CONF_PLATFORMS, {}).get(MEDIA_PLAYER, {})

    for media_player_id, media_player_config in media_players.items():
        area = media_player_config.get(AUDIO_AREA_ATTR)
        point = media_player_config.get(AUDIO_POINT_ATTR)
        if area is None or point is None:
            continue

        for operation, definition in _AUDIO_TEXT_ENTITY_DEFINITIONS.items():
            device_id = f"{media_player_id}-{operation}-text"
            text_config.setdefault(
                device_id,
                {
                    CONF_WHO: "22",
                    CONF_WHERE: f"{int(area)}#{int(point)}",
                    CONF_NAME: media_player_config.get(
                        CONF_NAME,
                        f"Audio area {area} point {point}",
                    ),
                    CONF_ENTITY_NAME: definition["name"],
                    CONF_OPERATION: operation,
                    CONF_MANUFACTURER: media_player_config.get(
                        CONF_MANUFACTURER,
                        "BTicino S.p.A.",
                    ),
                    CONF_DEVICE_MODEL: media_player_config.get(CONF_DEVICE_MODEL),
                    CONF_ENTITIES: {},
                },
            )


async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    gateway_data = hass.data[DOMAIN][config_entry.data[CONF_MAC]]
    _ensure_audio_text_configs(gateway_data)

    texts = []
    configured_texts = gateway_data[CONF_PLATFORMS][PLATFORM]

    for text_id, text_config in configured_texts.items():
        if text_config.get(CONF_WHO) != "22":
            continue

        texts.append(
            MyHOMEAudioEqualizationText(
                hass=hass,
                device_id=text_id,
                who=text_config[CONF_WHO],
                where=text_config[CONF_WHERE],
                name=text_config[CONF_NAME],
                entity_name=text_config.get(CONF_ENTITY_NAME),
                operation=text_config.get(CONF_OPERATION),
                manufacturer=text_config[CONF_MANUFACTURER],
                model=text_config[CONF_DEVICE_MODEL],
                gateway=gateway_data[CONF_ENTITY],
            )
        )
    async_add_entities(texts)


async def async_unload_entry(hass, config_entry):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    configured_texts = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][
        PLATFORM
    ]
    for text in configured_texts.keys():
        del hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM][
            text
        ]


class MyHOMEAudioEqualizationText(MyHOMEEntity, RestoreText):
    """Represent WHO=22 equalization groups as native text entities."""

    def __init__(
        self,
        hass,
        name: str,
        entity_name: str | None,
        device_id: str,
        who: str,
        where: str,
        operation: str | None,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ) -> None:
        operation = str(operation)
        definition = _AUDIO_TEXT_ENTITY_DEFINITIONS[operation]
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model or "MyHOME Audio Control",
            gateway=gateway,
        )

        area_text, point_text = str(where).split("#", 1)
        self._operation = operation
        self._definition = definition
        self._area = int(area_text)
        self._point = int(point_text)
        self._equalization = int(definition["equalization"])
        self._attr_name = entity_name or definition["name"]
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_icon = definition["icon"]
        self._attr_mode = TextMode.TEXT
        self._attr_native_min = 1
        self._attr_native_max = 64
        self._attr_pattern = definition["pattern"]
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "area": self._area,
            "point": self._point,
            "audio_operation": self._operation,
            "equalization": self._equalization,
            "bands": None,
            "last_update": None,
        }

    async def async_added_to_hass(self):
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._platform] = self
        self.async_on_remove(
            self._hass.bus.async_listen(
                "myhome_audio_feedback_event",
                self._handle_audio_feedback_event,
            )
        )

        last_data = await self.async_get_last_text_data()
        if last_data is not None and last_data.native_value is not None:
            self._attr_native_value = last_data.native_value

        await self.async_update()

    async def async_will_remove_from_hass(self):
        if (
            self._platform
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES][self._platform]

    def _apply_snapshot(self, snapshot: dict | None) -> None:
        if not snapshot:
            return

        bands = snapshot.get(self._definition["snapshot_field"])
        if bands is None:
            return

        normalized_bands = [str(band) for band in bands]
        self._attr_native_value = ", ".join(normalized_bands)
        self._attr_extra_state_attributes["bands"] = normalized_bands
        self._attr_extra_state_attributes["last_update"] = snapshot.get("last_update")

    async def async_update(self):
        await self._gateway_handler.send_status_request_collect(
            build_audio_zone_command(
                self._area,
                self._point,
                self._definition["query_operation"],
            )
        )
        self._apply_snapshot(
            self._gateway_handler.audio.zone_snapshot(self._area, self._point)
        )
        self.async_schedule_update_ha_state()

    async def async_set_value(self, value: str) -> None:
        bands = normalize_equalization_bands(self._equalization, value)
        message = build_audio_zone_command(
            self._area,
            self._point,
            self._definition["set_operation"],
            bands=bands,
        )
        await self._gateway_handler.send(message)

        feedback = {
            "kind": "speaker_equalization",
            "area": self._area,
            "point": self._point,
            "zone_key": f"{self._area}_{self._point}",
            "equalization": self._equalization,
            "bands": bands,
            "gateway": str(self._gateway_handler.gateway.host),
            "gateway_mac": self._gateway_handler.mac,
            "raw_message": message,
        }
        self._gateway_handler.audio.handle_feedback(feedback)
        self._hass.bus.async_fire("myhome_audio_feedback_event", feedback)
        self._apply_snapshot(
            self._gateway_handler.audio.zone_snapshot(self._area, self._point)
        )
        self.async_write_ha_state()

    @callback
    def _handle_audio_feedback_event(self, event) -> None:
        data = dict(event.data)
        if data.get("gateway_mac") != self._gateway_handler.mac:
            return
        if int(data.get("area", -1)) != self._area:
            return
        if int(data.get("point", -1)) != self._point:
            return
        if data.get("kind") != "speaker_equalization":
            return
        if int(data.get("equalization", -1)) != self._equalization:
            return
        self._apply_snapshot(
            self._gateway_handler.audio.zone_snapshot(self._area, self._point)
        )
        self.async_write_ha_state()
