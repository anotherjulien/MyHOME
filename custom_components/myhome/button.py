"""Support for MyHome switches (light modules used for controlled outlets, relays)."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .gateway import MyHOMEGatewayHandler

from homeassistant.components.button import (
    DOMAIN as PLATFORM,
    ButtonEntity,
)
from homeassistant.components.camera import DOMAIN as CAMERA
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER
from homeassistant.components.number import DOMAIN as NUMBER
from homeassistant.components.switch import DOMAIN as SWITCH

from homeassistant.const import (
    CONF_NAME,
    CONF_MAC,
    CONF_ENTITIES,
    EntityCategory,
)

from .const import (
    CONF_PLATFORMS,
    CONF_ENTITY,
    CONF_WHO,
    CONF_WHERE,
    CONF_OPERATION,
    CONF_BUS_INTERFACE,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_ENTITY_NAME,
    DOMAIN,
)
from .myhome_device import MyHOMEEntity
from .audio import build_audio_radio_command
from .scene_programmer import build_scene_programmer_command
from .av import build_video_command

_GATEWAY_VIDEO_CONTROL_SENTINEL = "__gateway_video_controls__"
_AUDIO_RADIO_CONTROL_SENTINEL = "__audio_radio_controls__"
_GATEWAY_VIDEO_CONTROL_OPERATIONS = {
    "receive_video": {
        "name": "Receive video",
        "icon": "mdi:video-wireless",
    },
    "close_video": {
        "name": "Close video",
        "icon": "mdi:video-off",
    },
    "zoom_in": {
        "name": "Zoom in",
        "icon": "mdi:magnify-plus-outline",
    },
    "zoom_out": {
        "name": "Zoom out",
        "icon": "mdi:magnify-minus-outline",
    },
    "x_up": {
        "name": "Pan left",
        "icon": "mdi:pan-left",
    },
    "x_down": {
        "name": "Pan right",
        "icon": "mdi:pan-right",
    },
    "y_up": {
        "name": "Tilt up",
        "icon": "mdi:pan-up",
    },
    "y_down": {
        "name": "Tilt down",
        "icon": "mdi:pan-down",
    },
    "brightness_up": {
        "name": "Brightness up",
        "icon": "mdi:brightness-7",
    },
    "brightness_down": {
        "name": "Brightness down",
        "icon": "mdi:brightness-5",
    },
    "contrast_up": {
        "name": "Contrast up",
        "icon": "mdi:contrast",
    },
    "contrast_down": {
        "name": "Contrast down",
        "icon": "mdi:contrast-box",
    },
    "color_up": {
        "name": "Color up",
        "icon": "mdi:palette-outline",
    },
    "color_down": {
        "name": "Color down",
        "icon": "mdi:palette",
    },
    "quality_up": {
        "name": "Quality up",
        "icon": "mdi:image-plus",
    },
    "quality_down": {
        "name": "Quality down",
        "icon": "mdi:image-minus",
    },
}
_AUDIO_RADIO_CONTROL_OPERATIONS = {
    "query_status": {
        "name": "Radio query status",
        "icon": "mdi:radio-search",
    },
    "query_rds": {
        "name": "Radio query RDS",
        "icon": "mdi:text-box-search-outline",
    },
    "frequency_up": {
        "name": "Radio frequency up",
        "icon": "mdi:radio-handheld",
    },
    "frequency_down": {
        "name": "Radio frequency down",
        "icon": "mdi:radio-handheld",
    },
    "next_station": {
        "name": "Radio next station",
        "icon": "mdi:skip-next",
    },
    "previous_station": {
        "name": "Radio previous station",
        "icon": "mdi:skip-previous",
    },
}


def _ensure_gateway_video_button_configs(gateway_data: dict) -> None:
    button_config = gateway_data.setdefault(CONF_PLATFORMS, {}).setdefault(PLATFORM, {})
    camera_devices = gateway_data.get(CONF_PLATFORMS, {}).get(CAMERA, {})

    for camera_device_id, camera_config in camera_devices.items():
        where = str(camera_config.get(CONF_WHERE, "0"))
        device_id = f"{camera_device_id}-controls"
        button_config.setdefault(
            device_id,
            {
                CONF_WHO: "7",
                CONF_WHERE: where,
                CONF_NAME: camera_config.get(CONF_NAME, "Gateway camera"),
                CONF_ENTITY_NAME: "Controls",
                CONF_OPERATION: _GATEWAY_VIDEO_CONTROL_SENTINEL,
                CONF_MANUFACTURER: camera_config.get(CONF_MANUFACTURER, "BTicino S.p.A."),
                CONF_DEVICE_MODEL: camera_config.get(CONF_DEVICE_MODEL),
                CONF_ENTITIES: {},
            },
        )


def _ensure_audio_radio_button_configs(gateway_data: dict) -> None:
    button_config = gateway_data.setdefault(CONF_PLATFORMS, {}).setdefault(PLATFORM, {})
    media_players = gateway_data.get(CONF_PLATFORMS, {}).get(MEDIA_PLAYER, {})
    if not media_players:
        return

    first_media_player = next(iter(media_players.values()))
    button_config.setdefault(
        "audio-radio-controls",
        {
            CONF_WHO: "22",
            CONF_WHERE: "1",
            CONF_NAME: "Audio radio",
            CONF_ENTITY_NAME: "Controls",
            CONF_OPERATION: _AUDIO_RADIO_CONTROL_SENTINEL,
            CONF_MANUFACTURER: first_media_player.get(
                CONF_MANUFACTURER,
                "BTicino S.p.A.",
            ),
            CONF_DEVICE_MODEL: first_media_player.get(CONF_DEVICE_MODEL),
            CONF_ENTITIES: {},
        },
    )


async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    gateway_data = hass.data[DOMAIN][config_entry.data[CONF_MAC]]
    _ensure_gateway_video_button_configs(gateway_data)
    _ensure_audio_radio_button_configs(gateway_data)

    _buttons = []
    _configured_buttons = gateway_data[CONF_PLATFORMS][PLATFORM]

    for _button in _configured_buttons.keys():
        _button_config = _configured_buttons[_button]
        _common_kwargs = {
            "hass": hass,
            "platform": PLATFORM,
            "device_id": _button,
            "who": _button_config[CONF_WHO],
            "where": _button_config.get(CONF_WHERE, ""),
            "interface": (
                _button_config[CONF_BUS_INTERFACE]
                if CONF_BUS_INTERFACE in _button_config
                else None
            ),
            "name": _button_config[CONF_NAME],
            "entity_name": _button_config.get(CONF_ENTITY_NAME),
            "manufacturer": _button_config[CONF_MANUFACTURER],
            "model": _button_config[CONF_DEVICE_MODEL],
            "gateway": hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
        }

        if _button_config[CONF_WHO] == "18":
            _buttons.append(LoadEnableActuatorButtonEntity(**_common_kwargs))
            _buttons.append(LoadForceDefaultTimeButtonEntity(**_common_kwargs))
            _buttons.append(LoadForceForDurationButtonEntity(**_common_kwargs))
            _buttons.append(LoadEndForcedButtonEntity(**_common_kwargs))
            _buttons.append(LoadResetTotalizerButtonEntity(totalizer=1, **_common_kwargs))
            _buttons.append(LoadResetTotalizerButtonEntity(totalizer=2, **_common_kwargs))
        elif _button_config[CONF_WHO] == "17":
            _buttons.append(
                SceneProgrammerButtonEntity(
                    operation=_button_config[CONF_OPERATION],
                    **_common_kwargs,
                )
            )
        elif _button_config[CONF_WHO] == "7":
            if _button_config[CONF_OPERATION] == _GATEWAY_VIDEO_CONTROL_SENTINEL:
                for operation, definition in _GATEWAY_VIDEO_CONTROL_OPERATIONS.items():
                    _gateway_video_kwargs = dict(_common_kwargs)
                    _gateway_video_kwargs["entity_name"] = definition["name"]
                    _buttons.append(
                        GatewayVideoControlButtonEntity(
                            operation=operation,
                            icon=definition["icon"],
                            **_gateway_video_kwargs,
                        )
                    )
            else:
                _buttons.append(
                    VideoCommandButtonEntity(
                        operation=_button_config[CONF_OPERATION],
                        **_common_kwargs,
                    )
                )
        elif _button_config[CONF_WHO] == "22":
            if _button_config[CONF_OPERATION] == _AUDIO_RADIO_CONTROL_SENTINEL:
                for operation, definition in _AUDIO_RADIO_CONTROL_OPERATIONS.items():
                    _audio_radio_kwargs = dict(_common_kwargs)
                    _audio_radio_kwargs["entity_name"] = definition["name"]
                    _buttons.append(
                        AudioRadioControlButtonEntity(
                            operation=operation,
                            icon=definition["icon"],
                            **_audio_radio_kwargs,
                        )
                    )
        else:
            _buttons.append(DisableCommandButtonEntity(**_common_kwargs))
            _buttons.append(EnableCommandButtonEntity(**_common_kwargs))

    async_add_entities(_buttons)


async def async_unload_entry(hass, config_entry):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    _configured_buttons = hass.data[DOMAIN][config_entry.data[CONF_MAC]][
        CONF_PLATFORMS
    ][PLATFORM]

    for _button in _configured_buttons.keys():
        del hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM][
            _button
        ]


class DisableCommandButtonEntity(ButtonEntity, MyHOMEEntity):
    def __init__(
        self,
        hass,
        platform: str,
        name: str,
        entity_name: str | None,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        super().__init__(
            hass=hass,
            name=name,
            platform=platform,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )
        self._attr_name = "Lock"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:lock-alert"

        self._attr_entity_category = EntityCategory.CONFIG

        self._attr_unique_id = f"{gateway.mac}-{self._device_id}-disable"
        self._interface = interface
        self._full_where = (
            f"{self._where}#4#{self._interface}"
            if self._interface is not None
            else self._where
        )

        self._attr_extra_state_attributes = {
            "A": where[: len(where) // 2],
            "PL": where[len(where) // 2 :],
        }
        if self._interface is not None:
            self._attr_extra_state_attributes["Int"] = self._interface

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES]["disable"] = self

    async def async_will_remove_from_hass(self):
        """When entity is removed from hass."""
        if (
            "disable"
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]["disable"]

    async def async_press(self) -> None:
        """Press the button."""
        await self._gateway_handler.send(f"*14*0*{self._full_where}##")


class EnableCommandButtonEntity(ButtonEntity, MyHOMEEntity):
    def __init__(
        self,
        hass,
        platform: str,
        name: str,
        entity_name: str | None,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        super().__init__(
            hass=hass,
            name=name,
            platform=platform,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )
        self._attr_name = "Unlock"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:lock-open-variant-outline"

        self._attr_entity_category = EntityCategory.CONFIG

        self._attr_unique_id = f"{gateway.mac}-{self._device_id}-enable"
        self._interface = interface
        self._full_where = (
            f"{self._where}#4#{self._interface}"
            if self._interface is not None
            else self._where
        )

        self._attr_extra_state_attributes = {
            "A": where[: len(where) // 2],
            "PL": where[len(where) // 2 :],
        }
        if self._interface is not None:
            self._attr_extra_state_attributes["Int"] = self._interface

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES]["enable"] = self

    async def async_will_remove_from_hass(self):
        """When entity is removed from hass."""
        if (
            "enable"
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]["enable"]

    async def async_press(self) -> None:
        """Press the button."""
        await self._gateway_handler.send(f"*14*1*{self._full_where}##")


class LoadControlButtonEntity(ButtonEntity, MyHOMEEntity):
    def __init__(
        self,
        hass,
        platform: str,
        name: str,
        entity_name: str | None,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        del interface
        super().__init__(
            hass=hass,
            name=name,
            platform=platform,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model or "F522",
            gateway=gateway,
        )
        self._attr_has_entity_name = True
        self._full_where = f"{self._where}#0" if self._where.startswith("7") else self._where

    async def _register_entity(self, entity_key: str):
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][entity_key] = self

    async def _remove_entity(self, entity_key: str):
        if (
            entity_key
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES][entity_key]

    def _load_switch_entity(self):
        switch_config = self._hass.data[DOMAIN][self._gateway_handler.mac][
            CONF_PLATFORMS
        ].get(SWITCH, {}).get(self._device_id, {})
        return switch_config.get(CONF_ENTITIES, {}).get(SWITCH)

    def _load_force_duration_minutes(self) -> int:
        number_config = self._hass.data[DOMAIN][self._gateway_handler.mac][
            CONF_PLATFORMS
        ].get(NUMBER, {}).get(self._device_id, {})
        number_entity = number_config.get(CONF_ENTITIES, {}).get("load-force-duration")
        if number_entity is None or getattr(number_entity, "native_value", None) is None:
            return 10
        return int(number_entity.native_value)


class LoadEnableActuatorButtonEntity(LoadControlButtonEntity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._attr_name = "Enable actuator"
        self._attr_icon = "mdi:power-plug"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_unique_id = f"{self._gateway_handler.mac}-{self._device_id}-load-enable"

    async def async_added_to_hass(self):
        await self._register_entity("load-enable")

    async def async_will_remove_from_hass(self):
        await self._remove_entity("load-enable")

    async def async_press(self) -> None:
        switch_entity = self._load_switch_entity()
        if switch_entity is not None:
            await switch_entity.enable_actuator()
            return
        await self._gateway_handler.send(f"*18*71*{self._full_where}##")


class LoadForceDefaultTimeButtonEntity(LoadControlButtonEntity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._attr_name = "Force default time"
        self._attr_icon = "mdi:timer-play-outline"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_unique_id = f"{self._gateway_handler.mac}-{self._device_id}-load-force-default"

    async def async_added_to_hass(self):
        await self._register_entity("load-force-default")

    async def async_will_remove_from_hass(self):
        await self._remove_entity("load-force-default")

    async def async_press(self) -> None:
        switch_entity = self._load_switch_entity()
        if switch_entity is not None:
            await switch_entity.force_default_time()
            return
        await self._gateway_handler.send(f"*18*73*{self._full_where}##")


class LoadForceForDurationButtonEntity(LoadControlButtonEntity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._attr_name = "Force custom time"
        self._attr_icon = "mdi:timer-cog-outline"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_unique_id = (
            f"{self._gateway_handler.mac}-{self._device_id}-load-force-for-duration"
        )

    async def async_added_to_hass(self):
        await self._register_entity("load-force-for-duration")

    async def async_will_remove_from_hass(self):
        await self._remove_entity("load-force-for-duration")

    async def async_press(self) -> None:
        switch_entity = self._load_switch_entity()
        if switch_entity is not None:
            await switch_entity.force_for_duration(self._load_force_duration_minutes())
            return
        await self._gateway_handler.send(
            f"*18*73#{self._load_force_duration_minutes() // 10}*{self._full_where}##"
        )


class LoadEndForcedButtonEntity(LoadControlButtonEntity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._attr_name = "End forced mode"
        self._attr_icon = "mdi:timer-stop-outline"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_unique_id = f"{self._gateway_handler.mac}-{self._device_id}-load-end-forced"

    async def async_added_to_hass(self):
        await self._register_entity("load-end-forced")

    async def async_will_remove_from_hass(self):
        await self._remove_entity("load-end-forced")

    async def async_press(self) -> None:
        switch_entity = self._load_switch_entity()
        if switch_entity is not None:
            await switch_entity.end_forced()
            return
        await self._gateway_handler.send(f"*18*74*{self._full_where}##")


class LoadResetTotalizerButtonEntity(LoadControlButtonEntity):
    def __init__(self, totalizer: int, **kwargs):
        super().__init__(**kwargs)
        self._totalizer = int(totalizer)
        self._attr_name = f"Reset totalizer {self._totalizer}"
        self._attr_icon = "mdi:counter"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_entity_registry_enabled_default = False
        self._attr_unique_id = (
            f"{self._gateway_handler.mac}-{self._device_id}-load-reset-totalizer-{self._totalizer}"
        )

    async def async_added_to_hass(self):
        await self._register_entity(f"load-reset-totalizer-{self._totalizer}")

    async def async_will_remove_from_hass(self):
        await self._remove_entity(f"load-reset-totalizer-{self._totalizer}")

    async def async_press(self) -> None:
        switch_entity = self._load_switch_entity()
        if switch_entity is not None:
            await switch_entity.reset_totalizer(self._totalizer)
            return
        await self._gateway_handler.send(f"*18*75#{self._totalizer}*{self._full_where}##")


class SceneProgrammerButtonEntity(ButtonEntity, MyHOMEEntity):
    def __init__(
        self,
        hass,
        platform: str,
        name: str,
        entity_name: str | None,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
        operation: str,
    ):
        del interface
        super().__init__(
            hass=hass,
            name=name,
            platform=platform,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model or "MyHOME Scene Programmer",
            gateway=gateway,
        )
        self._operation = str(operation)
        self._attr_name = entity_name or self._operation.replace("_", " ").title()
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:play-circle-outline"
        self._attr_extra_state_attributes = {
            "operation": self._operation,
            "where": int(self._where),
        }

    async def async_press(self) -> None:
        await self._gateway_handler.send(
            build_scene_programmer_command(self._where, self._operation)
        )


class VideoCommandButtonEntity(ButtonEntity, MyHOMEEntity):
    def __init__(
        self,
        hass,
        platform: str,
        name: str,
        entity_name: str | None,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
        operation: str,
    ):
        del interface
        super().__init__(
            hass=hass,
            name=name,
            platform=platform,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model or "MyHOME Video Command",
            gateway=gateway,
        )
        self._operation = str(operation)
        self._attr_name = entity_name or self._operation.replace("_", " ").title()
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:cctv"
        self._attr_extra_state_attributes = {
            "operation": self._operation,
        }
        if self._where != "":
            self._attr_extra_state_attributes["where"] = int(self._where)

    async def async_press(self) -> None:
        await self._gateway_handler.send(
            build_video_command(
                self._operation,
                where=self._where if self._where != "" else None,
            )
        )


class GatewayVideoControlButtonEntity(ButtonEntity, MyHOMEEntity):
    def __init__(
        self,
        hass,
        platform: str,
        name: str,
        entity_name: str | None,
        icon: str,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
        operation: str,
    ):
        del interface
        super().__init__(
            hass=hass,
            name=name,
            platform=platform,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model or "MyHOME Video Gateway Controls",
            gateway=gateway,
        )
        self._operation = str(operation)
        self._entity_specific_id = f"video-{self._operation}"
        self._attr_name = entity_name or self._operation.replace("_", " ").title()
        self._attr_has_entity_name = True
        self._attr_icon = icon or "mdi:cctv"
        self._attr_unique_id = (
            f"{gateway.mac}-{self._device_id}-{self._entity_specific_id}"
        )
        self._attr_extra_state_attributes = {
            "operation": self._operation,
            "where": int(self._where),
        }

    async def async_added_to_hass(self):
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._entity_specific_id] = self

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

    async def async_press(self) -> None:
        await self._gateway_handler.send(
            build_video_command(
                self._operation,
                where=self._where if self._where != "" else None,
            )
        )


class AudioRadioControlButtonEntity(ButtonEntity, MyHOMEEntity):
    def __init__(
        self,
        hass,
        platform: str,
        name: str,
        entity_name: str | None,
        icon: str,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
        operation: str,
    ):
        del interface
        super().__init__(
            hass=hass,
            name=name,
            platform=platform,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model or "MyHOME Audio Radio Controls",
            gateway=gateway,
        )
        self._operation = str(operation)
        self._entity_specific_id = f"audio-radio-{self._operation}"
        self._attr_name = entity_name or self._operation.replace("_", " ").title()
        self._attr_has_entity_name = True
        self._attr_icon = icon or "mdi:radio"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_unique_id = (
            f"{gateway.mac}-{self._device_id}-{self._entity_specific_id}"
        )
        self._attr_extra_state_attributes = {
            "operation": self._operation,
            "source_id": 1,
        }

    async def async_added_to_hass(self):
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._entity_specific_id] = self

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

    async def async_press(self) -> None:
        message = build_audio_radio_command(self._operation)
        if isinstance(message, list):
            for frame in message:
                await self._gateway_handler.send_status_request_collect(frame)
            return

        if self._operation.startswith("query"):
            await self._gateway_handler.send_status_request_collect(message)
            return

        await self._gateway_handler.send(message)
