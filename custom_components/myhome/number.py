"""Support for MyHome numbers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .gateway import MyHOMEGatewayHandler

from homeassistant.components.number import (
    DOMAIN as PLATFORM,
    NumberEntity,
    NumberMode,
    RestoreNumber,
)
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER
from homeassistant.components.switch import DOMAIN as SWITCH
from homeassistant.core import callback
from homeassistant.const import (
    CONF_ENTITIES,
    CONF_MAC,
    CONF_NAME,
    EntityCategory,
    UnitOfTime,
)

from .const import (
    CONF_DEVICE_MODEL,
    CONF_ENTITY,
    CONF_ENTITY_NAME,
    CONF_MANUFACTURER,
    CONF_OPERATION,
    CONF_PLATFORMS,
    CONF_WHO,
    CONF_WHERE,
    DOMAIN,
)
from .light_management import (
    EVENT_LIGHT_MANAGEMENT,
    NUMBER_ENTITY_DESCRIPTIONS,
    build_light_management_command,
    build_light_management_request,
)
from .media_player import ATTR_AREA as AUDIO_AREA_ATTR, ATTR_POINT as AUDIO_POINT_ATTR
from .audio import build_audio_zone_command
from .myhome_device import MyHOMEEntity


_AUDIO_NUMBER_ENTITY_DEFINITIONS = {
    "high_tones": {
        "name": "High tones",
        "icon": "mdi:tune-vertical",
        "native_min_value": 0,
        "native_max_value": 63,
        "native_step": 1,
        "query_operation": "query_high_tones",
        "set_operation": "set_high_tones",
        "snapshot_field": "high_tones",
    },
    "mid_tones": {
        "name": "Mid tones",
        "icon": "mdi:tune",
        "native_min_value": 0,
        "native_max_value": 63,
        "native_step": 1,
        "query_operation": "query_mid_tones",
        "set_operation": "set_mid_tones",
        "snapshot_field": "mid_tones",
    },
    "low_tones": {
        "name": "Low tones",
        "icon": "mdi:tune-variant",
        "native_min_value": 0,
        "native_max_value": 63,
        "native_step": 1,
        "query_operation": "query_low_tones",
        "set_operation": "set_low_tones",
        "snapshot_field": "low_tones",
    },
    "balance": {
        "name": "Balance",
        "icon": "mdi:compare-horizontal",
        "native_min_value": 1,
        "native_max_value": 63,
        "native_step": 1,
        "query_operation": "query_balance",
        "set_operation": "set_balance",
        "snapshot_field": "balance",
    },
    "three_d": {
        "name": "3D",
        "icon": "mdi:surround-sound",
        "native_min_value": 0,
        "native_max_value": 10,
        "native_step": 1,
        "query_operation": "query_3d",
        "set_operation": "set_3d",
        "snapshot_field": "three_d",
    },
}


def _ensure_audio_number_configs(gateway_data: dict) -> None:
    number_config = gateway_data.setdefault(CONF_PLATFORMS, {}).setdefault(PLATFORM, {})
    media_players = gateway_data.get(CONF_PLATFORMS, {}).get(MEDIA_PLAYER, {})

    for media_player_id, media_player_config in media_players.items():
        area = media_player_config.get(AUDIO_AREA_ATTR)
        point = media_player_config.get(AUDIO_POINT_ATTR)
        if area is None or point is None:
            continue

        for operation, definition in _AUDIO_NUMBER_ENTITY_DEFINITIONS.items():
            device_id = f"{media_player_id}-{operation}"
            number_config.setdefault(
                device_id,
                {
                    CONF_WHO: "22",
                    CONF_WHERE: f"{int(area)}#{int(point)}",
                    CONF_NAME: media_player_config.get(CONF_NAME, f"Audio area {area} point {point}"),
                    CONF_ENTITY_NAME: definition["name"],
                    CONF_OPERATION: operation,
                    CONF_MANUFACTURER: media_player_config.get(CONF_MANUFACTURER, "BTicino S.p.A."),
                    CONF_DEVICE_MODEL: media_player_config.get(CONF_DEVICE_MODEL),
                    CONF_ENTITIES: {},
                },
            )


async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    gateway_data = hass.data[DOMAIN][config_entry.data[CONF_MAC]]
    _ensure_audio_number_configs(gateway_data)

    numbers = []
    configured_numbers = gateway_data[CONF_PLATFORMS][PLATFORM]
    configured_switches = gateway_data[CONF_PLATFORMS].get(SWITCH, {})

    for switch_id, switch_config in configured_switches.items():
        if switch_config[CONF_WHO] != "18":
            continue

        configured_numbers.setdefault(
            switch_id,
            {
                CONF_WHO: switch_config[CONF_WHO],
                CONF_WHERE: switch_config[CONF_WHERE],
                CONF_NAME: switch_config[CONF_NAME],
                CONF_MANUFACTURER: switch_config[CONF_MANUFACTURER],
                CONF_DEVICE_MODEL: switch_config[CONF_DEVICE_MODEL],
                CONF_ENTITIES: {},
            },
        )

    for number_id, number_config in configured_numbers.items():
        if number_config[CONF_WHO] == "18":
            number_cls = MyHOMELoadForceDurationNumber
        elif number_config[CONF_WHO] == "24":
            number_cls = MyHOMELightManagementNumber
        elif number_config[CONF_WHO] == "22":
            number_cls = MyHOMEAudioControlNumber
        else:
            continue

        numbers.append(
            number_cls(
                hass=hass,
                device_id=number_id,
                who=number_config[CONF_WHO],
                where=number_config[CONF_WHERE],
                name=number_config[CONF_NAME],
                entity_name=number_config.get(CONF_ENTITY_NAME),
                operation=number_config.get(CONF_OPERATION),
                manufacturer=number_config[CONF_MANUFACTURER],
                model=number_config[CONF_DEVICE_MODEL],
                gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
            )
        )
    async_add_entities(numbers)


async def async_unload_entry(hass, config_entry):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    configured_numbers = hass.data[DOMAIN][config_entry.data[CONF_MAC]][
        CONF_PLATFORMS
    ][PLATFORM]

    for number in configured_numbers.keys():
        del hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM][
            number
        ]


class MyHOMELoadForceDurationNumber(MyHOMEEntity, RestoreNumber):
    """Store the preferred custom force duration for a load-control actuator."""

    def __init__(
        self,
        hass,
        name: str,
        device_id: str,
        who: str,
        where: str,
        entity_name: str | None,
        operation: str | None,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        del entity_name
        del operation
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model or "F522",
            gateway=gateway,
        )

        self._entity_specific_id = "load-force-duration"
        self._attr_name = "Force duration"
        self._attr_unique_id = f"{gateway.mac}-{self._device_id}-{self._entity_specific_id}"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_icon = "mdi:timer-cog-outline"
        self._attr_native_min_value = 10
        self._attr_native_max_value = 2540
        self._attr_native_step = 10
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_mode = NumberMode.BOX
        self._attr_native_value = 10
        self._attr_extra_state_attributes = {
            "load": self._where[1:] if self._where.startswith("7") else self._where,
        }

    async def async_added_to_hass(self):
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._entity_specific_id] = self

        last_data = await self.async_get_last_number_data()
        if last_data is not None and last_data.native_value is not None:
            self._attr_native_value = last_data.native_value

    async def async_will_remove_from_hass(self):
        if (
            self._entity_specific_id
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES][self._entity_specific_id]

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = int(value)
        self.async_schedule_update_ha_state()


class MyHOMELightManagementNumber(MyHOMEEntity, RestoreNumber):
    """Represent a WHO=24 scalar lighting-management parameter."""

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
    ):
        operation = str(operation)
        description = NUMBER_ENTITY_DESCRIPTIONS[operation]
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model or "MyHOME Light Management",
            gateway=gateway,
        )

        self._operation = operation
        self._attr_name = entity_name or description["name"]
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_icon = description["icon"]
        self._attr_native_min_value = description["native_min_value"]
        self._attr_native_max_value = description["native_max_value"]
        self._attr_native_step = description["native_step"]
        self._attr_native_unit_of_measurement = description["native_unit"]
        self._attr_mode = NumberMode.BOX
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "where": self._where,
            "lm_operation": self._operation,
            "last_update": None,
        }

    async def async_added_to_hass(self):
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._platform] = self
        self.async_on_remove(
            self._hass.bus.async_listen(
                EVENT_LIGHT_MANAGEMENT,
                self._handle_light_management_event,
            )
        )

        last_data = await self.async_get_last_number_data()
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
        value = snapshot.get(self._operation)
        if value is None:
            return
        self._attr_native_value = float(value)
        self._attr_extra_state_attributes["last_update"] = snapshot.get("last_update")

    async def async_update(self):
        await self._gateway_handler.send_status_request_collect(
            build_light_management_request(self._operation, self._where)
        )
        self._apply_snapshot(
            self._gateway_handler.light_management.zone_snapshot(self._where)
        )
        self.async_schedule_update_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        await self._gateway_handler.send(
            build_light_management_command(
                f"set_{self._operation}",
                self._where,
                value=int(round(value)),
            )
        )
        await self.async_update()

    @callback
    def _handle_light_management_event(self, event) -> None:
        data = dict(event.data)
        if data.get("gateway_mac") != self._gateway_handler.mac:
            return
        if str(data.get("where")) != self._where:
            return
        if data.get("kind") != self._operation:
            return
        self._apply_snapshot(
            self._gateway_handler.light_management.zone_snapshot(self._where)
        )
        self.async_write_ha_state()


class MyHOMEAudioControlNumber(MyHOMEEntity, RestoreNumber):
    """Represent WHO=22 advanced audio controls as native numbers."""

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
    ):
        operation = str(operation)
        definition = _AUDIO_NUMBER_ENTITY_DEFINITIONS[operation]
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

        self._operation = operation
        self._definition = definition
        area_text, point_text = str(where).split("#", 1)
        self._area = int(area_text)
        self._point = int(point_text)
        self._attr_name = entity_name or definition["name"]
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_icon = definition["icon"]
        self._attr_native_min_value = definition["native_min_value"]
        self._attr_native_max_value = definition["native_max_value"]
        self._attr_native_step = definition["native_step"]
        self._attr_mode = NumberMode.BOX
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "area": self._area,
            "point": self._point,
            "audio_operation": self._operation,
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

        last_data = await self.async_get_last_number_data()
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
        value = snapshot.get(self._definition["snapshot_field"])
        if value is None:
            return
        self._attr_native_value = float(value)
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

    async def async_set_native_value(self, value: float) -> None:
        await self._gateway_handler.send(
            build_audio_zone_command(
                self._area,
                self._point,
                self._definition["set_operation"],
                value=int(round(value)),
            )
        )
        await self.async_update()

    @callback
    def _handle_audio_feedback_event(self, event) -> None:
        data = dict(event.data)
        if data.get("gateway_mac") != self._gateway_handler.mac:
            return
        if int(data.get("area", -1)) != self._area:
            return
        if int(data.get("point", -1)) != self._point:
            return
        expected_kind = f"speaker_{self._operation}"
        if data.get("kind") != expected_kind:
            return
        self._apply_snapshot(
            self._gateway_handler.audio.zone_snapshot(self._area, self._point)
        )
        self.async_write_ha_state()
