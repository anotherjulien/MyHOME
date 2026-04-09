"""Support for MyHome switches (light modules used for controlled outlets, relays)."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from datetime import timedelta

from homeassistant.components.switch import (
    DOMAIN as PLATFORM,
    SwitchDeviceClass,
    SwitchEntity,
)
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR
from homeassistant.components.sensor import DOMAIN as SENSOR
from homeassistant.core import callback
from homeassistant.helpers import entity_platform
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_NAME,
    CONF_MAC,
)
from voluptuous import (
    All,
    Coerce,
    Optional,
    Range,
    Invalid,
)

from OWNd.message import (
    MESSAGE_TYPE_ACTIVE_POWER,
    OWNCommand,
    OWNEnergyEvent,
    OWNLightingEvent,
    OWNLightingCommand,
    OWNSceneEvent,
)

from .const import (
    CONF_PLATFORMS,
    CONF_ENTITY,
    CONF_ENTITIES,
    CONF_ENTITY_NAME,
    CONF_OPERATION,
    CONF_ICON,
    CONF_ICON_ON,
    CONF_WHO,
    CONF_WHERE,
    CONF_BUS_INTERFACE,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_CLASS,
    DOMAIN,
    LOGGER,
)
from .myhome_device import MyHOMEEntity
from .gateway import MyHOMEGatewayHandler
from .media_player import ATTR_AREA as AUDIO_AREA_ATTR, ATTR_POINT as AUDIO_POINT_ATTR
from .audio import build_audio_zone_command
from .light_management import (
    EVENT_LIGHT_MANAGEMENT,
    build_light_management_command,
    build_light_management_request,
)
from .scene_programmer import (
    SCENE_ACTIVE_ROLE,
    SCENE_ENABLED_ROLE,
    build_scene_programmer_command,
    parse_scene_programmer_frames,
)

LOAD_CONTROL_STATUS_RE = re.compile(
    r"^\*#18\*(?P<where>\d+)(?:#0)?\*71\*(?P<disabled>[01])\*(?P<forcing>[01])\*(?P<threshold>[01])\*(?P<protection>[01])\*(?P<phase>[01])\*(?P<advanced>[12])##$"
)
LOAD_CONTROL_TOTALIZER_RE = re.compile(
    r"^\*#18\*(?P<where>\d+)(?:#0)?\*72#(?P<totalizer>[12])\*(?P<energy>\d+)\*(?P<day>\d+)\*(?P<month>\d+)\*(?P<year>\d+)\*(?P<hour>\d+)\*(?P<minute>\d+)##$"
)
LOAD_CONTROL_DIFFERENTIAL_LEVEL_RE = re.compile(
    r"^\*#18\*(?P<where>\d+)(?:#0)?\*73\*(?P<level>[1-3])##$"
)

SERVICE_ENABLE_ACTUATOR = "enable_actuator"
SERVICE_FORCE_DEFAULT_TIME = "force_default_time"
SERVICE_FORCE_FOR_DURATION = "force_for_duration"
SERVICE_END_FORCED = "end_forced"
SERVICE_RESET_TOTALIZER = "reset_totalizer"

ATTR_DURATION_MINUTES = "duration_minutes"
ATTR_TOTALIZER = "totalizer"

SCAN_INTERVAL = timedelta(seconds=60)


def _ensure_audio_switch_configs(gateway_data: dict) -> None:
    switch_config = gateway_data.setdefault(CONF_PLATFORMS, {}).setdefault(PLATFORM, {})
    media_players = gateway_data.get(CONF_PLATFORMS, {}).get(MEDIA_PLAYER, {})

    for media_player_id, media_player_config in media_players.items():
        area = media_player_config.get(AUDIO_AREA_ATTR)
        point = media_player_config.get(AUDIO_POINT_ATTR)
        if area is None or point is None:
            continue

        device_id = f"{media_player_id}-loudness"
        switch_config.setdefault(
            device_id,
            {
                CONF_WHO: "22",
                CONF_WHERE: f"{int(area)}#{int(point)}",
                CONF_NAME: media_player_config.get(CONF_NAME, f"Audio area {area} point {point}"),
                CONF_ENTITY_NAME: "Loudness",
                CONF_OPERATION: "loudness",
                CONF_MANUFACTURER: media_player_config.get(CONF_MANUFACTURER, "BTicino S.p.A."),
                CONF_DEVICE_MODEL: media_player_config.get(CONF_DEVICE_MODEL),
                CONF_ENTITIES: {},
            },
        )


def _build_own_command(raw_message: str):
    command = OWNCommand.parse(raw_message)
    return command if command is not None and command.is_valid else raw_message


def _validate_duration_minutes(value: int) -> int:
    value = int(value)
    if value < 10 or value > 2540:
        raise Invalid("Duration must be between 10 and 2540 minutes.")
    if value % 10 != 0:
        raise Invalid("Duration must be a multiple of 10 minutes.")
    return value


def _format_totalizer_reset(day: str, month: str, year: str, hour: str, minute: str) -> str:
    year_value = int(year)
    if year_value < 100:
        year_value += 2000
    return datetime(
        year=year_value,
        month=int(month),
        day=int(day),
        hour=int(hour),
        minute=int(minute),
    ).isoformat(timespec="minutes")


def _iter_load_switches(hass, entity_ids: list[str] | None = None):
    for gateway_data in hass.data[DOMAIN].values():
        platforms = gateway_data.get(CONF_PLATFORMS, {})
        for device_data in platforms.get(PLATFORM, {}).values():
            entity = device_data.get(CONF_ENTITIES, {}).get(PLATFORM)
            if not isinstance(entity, MyHOMELoadControlSwitch):
                continue
            if entity_ids is None or entity.entity_id in entity_ids:
                yield entity


async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    gateway_data = hass.data[DOMAIN][config_entry.data[CONF_MAC]]
    _ensure_audio_switch_configs(gateway_data)

    hass.data[DOMAIN][config_entry.data[CONF_MAC]]["switch_platform_loaded"] = True

    _switches = []
    _configured_switches = gateway_data[CONF_PLATFORMS][PLATFORM]

    for _switch in _configured_switches.keys():
        _switch_config = _configured_switches[_switch]
        if _switch_config[CONF_WHO] == "18":
            _switch_cls = MyHOMELoadControlSwitch
        elif _switch_config[CONF_WHO] == "17":
            _switch_cls = MyHOMESceneSwitch
        elif _switch_config[CONF_WHO] == "22":
            _switch_cls = MyHOMEAudioLoudnessSwitch
        elif _switch_config[CONF_WHO] == "24":
            _switch_cls = MyHOMELightManagementSwitch
        else:
            _switch_cls = MyHOMESwitch
        _switches.append(
            _switch_cls(
                hass=hass,
                device_id=_switch,
                who=_switch_config[CONF_WHO],
                where=_switch_config[CONF_WHERE],
                icon=_switch_config.get(CONF_ICON),
                icon_on=_switch_config.get(CONF_ICON_ON),
                interface=_switch_config[CONF_BUS_INTERFACE] if CONF_BUS_INTERFACE in _switch_config else None,
                name=_switch_config[CONF_NAME],
                entity_name=_switch_config[CONF_ENTITY_NAME],
                operation=_switch_config.get(CONF_OPERATION),
                device_class=_switch_config.get(
                    CONF_DEVICE_CLASS,
                    SwitchDeviceClass.SWITCH,
                ),
                manufacturer=_switch_config[CONF_MANUFACTURER],
                model=_switch_config[CONF_DEVICE_MODEL],
                gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
            )
        )

    if any(config[CONF_WHO] == "18" for config in _configured_switches.values()):
        platform = entity_platform.current_platform.get()
        platform.async_register_entity_service(
            SERVICE_ENABLE_ACTUATOR,
            {},
            "enable_actuator",
        )
        platform.async_register_entity_service(
            SERVICE_FORCE_DEFAULT_TIME,
            {},
            "force_default_time",
        )
        platform.async_register_entity_service(
            SERVICE_FORCE_FOR_DURATION,
            {
                Optional(ATTR_DURATION_MINUTES): All(
                    Coerce(int),
                    Range(min=10, max=2540),
                    _validate_duration_minutes,
                )
            },
            "force_for_duration",
        )
        platform.async_register_entity_service(
            SERVICE_END_FORCED,
            {},
            "end_forced",
        )
        platform.async_register_entity_service(
            SERVICE_RESET_TOTALIZER,
            {
                Optional(ATTR_TOTALIZER, default=1): All(
                    Coerce(int),
                    Range(min=1, max=2),
                )
            },
            "reset_totalizer",
        )

        async def handle_enable_actuator(call):
            entity_ids = call.data.get(ATTR_ENTITY_ID)
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]
            for entity in _iter_load_switches(hass, entity_ids):
                await entity.enable_actuator()

        async def handle_force_default_time(call):
            entity_ids = call.data.get(ATTR_ENTITY_ID)
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]
            for entity in _iter_load_switches(hass, entity_ids):
                await entity.force_default_time()

        async def handle_force_for_duration(call):
            entity_ids = call.data.get(ATTR_ENTITY_ID)
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]
            duration_minutes = call.data.get(ATTR_DURATION_MINUTES, 10)
            for entity in _iter_load_switches(hass, entity_ids):
                await entity.force_for_duration(duration_minutes)

        async def handle_end_forced(call):
            entity_ids = call.data.get(ATTR_ENTITY_ID)
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]
            for entity in _iter_load_switches(hass, entity_ids):
                await entity.end_forced()

        async def handle_reset_totalizer(call):
            entity_ids = call.data.get(ATTR_ENTITY_ID)
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]
            totalizer = call.data.get(ATTR_TOTALIZER, 1)
            for entity in _iter_load_switches(hass, entity_ids):
                await entity.reset_totalizer(totalizer)

        if not hass.services.has_service(DOMAIN, "load_enable_actuator"):
            hass.services.async_register(
                DOMAIN, "load_enable_actuator", handle_enable_actuator
            )
        if not hass.services.has_service(DOMAIN, "load_force_default_time"):
            hass.services.async_register(
                DOMAIN, "load_force_default_time", handle_force_default_time
            )
        if not hass.services.has_service(DOMAIN, "load_force_for_duration"):
            hass.services.async_register(
                DOMAIN, "load_force_for_duration", handle_force_for_duration
            )
        if not hass.services.has_service(DOMAIN, "load_end_forced"):
            hass.services.async_register(
                DOMAIN, "load_end_forced", handle_end_forced
            )
        if not hass.services.has_service(DOMAIN, "load_reset_totalizer"):
            hass.services.async_register(
                DOMAIN, "load_reset_totalizer", handle_reset_totalizer
            )

    async_add_entities(_switches)


async def async_unload_entry(hass, config_entry):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    _configured_switches = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM]

    for _switch in _configured_switches.keys():
        del hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM][_switch]


class MyHOMESwitch(MyHOMEEntity, SwitchEntity):
    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        icon: str,
        icon_on: str,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        operation: str | None,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        del operation
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._attr_name = entity_name

        self._interface = interface
        self._full_where = f"{self._where}#4#{self._interface}" if self._interface is not None else self._where

        self._attr_extra_state_attributes = {
            "A": where[: len(where) // 2],
            "PL": where[len(where) // 2 :],
        }
        if self._interface is not None:
            self._attr_extra_state_attributes["Int"] = self._interface

        self._attr_device_class = SwitchDeviceClass.OUTLET if device_class.lower() == "outlet" else SwitchDeviceClass.SWITCH

        self._on_icon = icon_on
        self._off_icon = icon

        if self._off_icon is not None:
            self._attr_icon = self._off_icon

        self._attr_is_on = None

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway_handler.send_status_request(OWNLightingCommand.status(self._where))

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Turn the device on."""
        await self._gateway_handler.send(OWNLightingCommand.switch_on(self._full_where))

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        """Turn the device off."""
        await self._gateway_handler.send(OWNLightingCommand.switch_off(self._full_where))

    def handle_event(self, message: OWNLightingEvent):
        """Handle an event message."""
        if self._attr_device_class == SwitchDeviceClass.SWITCH:
            LOGGER.info(
                "%s %s",
                self._gateway_handler.log_id,
                message.human_readable_log.replace("Light", "Switch"),
            )
        elif self._attr_device_class == SwitchDeviceClass.OUTLET:
            LOGGER.info(
                "%s %s",
                self._gateway_handler.log_id,
                message.human_readable_log.replace("Light", "Outlet"),
            )
        else:
            LOGGER.info(
                "%s %s",
                self._gateway_handler.log_id,
                message.human_readable_log,
            )
        self._attr_is_on = message.is_on
        if self._off_icon is not None and self._on_icon is not None:
            self._attr_icon = self._on_icon if self._attr_is_on else self._off_icon
        self.async_schedule_update_ha_state()


class MyHOMELoadControlSwitch(MyHOMEEntity, SwitchEntity):
    """Expose MyHOME load-control actuators as force/end-force switches."""

    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        icon: str,
        icon_on: str,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        operation: str | None,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        del interface
        del operation
        del device_class

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

        self._attr_name = entity_name
        self._full_where = f"{self._where}#0" if self._where.startswith("7") else self._where
        self._attr_device_class = SwitchDeviceClass.SWITCH
        self._on_icon = icon_on
        self._off_icon = icon
        if self._off_icon is not None:
            self._attr_icon = self._off_icon

        self._attr_is_on = None
        self._refresh_lock = asyncio.Lock()
        self._attr_extra_state_attributes = {
            "load": self._where[1:] if self._where.startswith("7") else self._where,
            "disabled": None,
            "enabled": None,
            "forcing": None,
            "below_threshold": None,
            "protection": None,
            "local_phase_disabled": None,
            "mode": None,
            "active_power_w": None,
            "differential_current_level": None,
            "totalizer_1_wh": None,
            "totalizer_1_last_reset": None,
            "totalizer_2_wh": None,
            "totalizer_2_last_reset": None,
        }

    def _sync_child_entities(self):
        for platform in (SENSOR, BINARY_SENSOR):
            platform_config = self._hass.data[DOMAIN][self._gateway_handler.mac][
                CONF_PLATFORMS
            ].get(platform, {})
            device_config = platform_config.get(self._device_id, {})
            for entity in device_config.get(CONF_ENTITIES, {}).values():
                if hasattr(entity, "apply_switch_attributes"):
                    entity.apply_switch_attributes(self._attr_extra_state_attributes)

    async def async_added_to_hass(self):
        """Register the entity without blocking platform setup on bus polling."""
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._platform] = self

    async def async_update(self):
        """Update the entity."""
        async with self._refresh_lock:
            for raw_message in (
                f"*#18*{self._full_where}*71##",
                f"*#18*{self._full_where}*113##",
                f"*#18*{self._full_where}*73##",
                f"*#18*{self._full_where}*72#1##",
            ):
                await self._gateway_handler.send_status_request(
                    _build_own_command(raw_message),
                    wait_for_completion=True,
                )

    async def async_refresh_totalizer(self, totalizer: int):
        """Refresh a single totalizer on demand."""
        async with self._refresh_lock:
            await self._gateway_handler.send_status_request(
                _build_own_command(f"*#18*{self._full_where}*72#{int(totalizer)}##"),
                wait_for_completion=True,
            )

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Force the actuator for its default configured time."""
        await self.force_default_time()

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        """End actuator forcing and return to automatic load control."""
        await self.end_forced()

    async def enable_actuator(self):
        """Enable the actuator if it was disabled by load control."""
        await self._gateway_handler.send(
            _build_own_command(f"*18*71*{self._full_where}##")
        )
        await self.async_update()

    async def force_default_time(self):
        """Force the actuator for the default configured time."""
        await self._gateway_handler.send(
            _build_own_command(f"*18*73*{self._full_where}##")
        )
        await self.async_update()

    async def force_for_duration(self, duration_minutes: int = 10):
        """Force the actuator for an explicit duration."""
        duration_minutes = _validate_duration_minutes(duration_minutes)
        await self._gateway_handler.send(
            _build_own_command(
                f"*18*73#{duration_minutes // 10}*{self._full_where}##"
            )
        )
        await self.async_update()

    async def end_forced(self):
        """End actuator forcing and return to automatic load control."""
        await self._gateway_handler.send(
            _build_own_command(f"*18*74*{self._full_where}##")
        )
        await self.async_update()

    async def reset_totalizer(self, totalizer: int = 1):
        """Reset one of the actuator totalizers."""
        await self._gateway_handler.send(
            _build_own_command(f"*18*75#{int(totalizer)}*{self._full_where}##")
        )
        await self.async_update()

    def handle_event(self, message: OWNEnergyEvent):
        """Handle WHO=18 load-control actuator status frames."""
        _raw_message = str(message)
        _match = LOAD_CONTROL_STATUS_RE.match(_raw_message)
        if _match is not None:
            disabled = _match.group("disabled") == "1"
            forcing = _match.group("forcing") == "1"
            below_threshold = _match.group("threshold") == "1"
            protection = _match.group("protection") == "1"
            local_phase_disabled = _match.group("phase") == "1"
            mode = "advanced" if _match.group("advanced") == "1" else "basic"

            LOGGER.info(
                "%s Load control actuator %s status: forcing=%s disabled=%s threshold_below=%s protection=%s.",
                self._gateway_handler.log_id,
                self._where,
                forcing,
                disabled,
                below_threshold,
                protection,
            )

            self._attr_is_on = forcing
            self._attr_extra_state_attributes.update(
                {
                    "disabled": disabled,
                    "enabled": not disabled,
                    "forcing": forcing,
                    "below_threshold": below_threshold,
                    "protection": protection,
                    "local_phase_disabled": local_phase_disabled,
                    "mode": mode,
                }
            )
            if self._off_icon is not None and self._on_icon is not None:
                self._attr_icon = self._on_icon if self._attr_is_on else self._off_icon
            self._sync_child_entities()
            self.async_schedule_update_ha_state()
            return True

        _match = LOAD_CONTROL_TOTALIZER_RE.match(_raw_message)
        if _match is not None:
            totalizer = _match.group("totalizer")
            try:
                last_reset = _format_totalizer_reset(
                    _match.group("day"),
                    _match.group("month"),
                    _match.group("year"),
                    _match.group("hour"),
                    _match.group("minute"),
                )
            except ValueError:
                last_reset = None

            self._attr_extra_state_attributes.update(
                {
                    f"totalizer_{totalizer}_wh": int(_match.group("energy")),
                    f"totalizer_{totalizer}_last_reset": last_reset,
                }
            )
            self._sync_child_entities()
            self.async_schedule_update_ha_state()
            return True

        _match = LOAD_CONTROL_DIFFERENTIAL_LEVEL_RE.match(_raw_message)
        if _match is not None:
            self._attr_extra_state_attributes["differential_current_level"] = int(
                _match.group("level")
            )
            self._sync_child_entities()
            self.async_schedule_update_ha_state()
            return True

        if message.message_type == MESSAGE_TYPE_ACTIVE_POWER:
            self._attr_extra_state_attributes["active_power_w"] = message.active_power
            self._sync_child_entities()
            self.async_schedule_update_ha_state()
            return True

        return True


class MyHOMESceneSwitch(MyHOMEEntity, SwitchEntity):
    """Represent a WHO=17 scene state as a native switch."""

    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        icon: str,
        icon_on: str,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        operation: str | None,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        del icon
        del icon_on
        del interface
        del device_class
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model or "MyHOME Scene Programmer",
            gateway=gateway,
        )

        self._scene = int(where)
        self._scene_role = str(operation or SCENE_ACTIVE_ROLE)
        self._attr_name = entity_name or (
            "Enabled" if self._scene_role == SCENE_ENABLED_ROLE else "Active"
        )
        self._attr_device_class = SwitchDeviceClass.SWITCH
        self._attr_is_on = None
        self._attr_extra_state_attributes = {
            "scene": self._scene,
            "scene_role": self._scene_role,
            "active_state": None,
            "active_state_code": None,
            "enabled_state": None,
            "enabled_state_code": None,
            "is_enabled": None,
            "last_update_via": None,
        }

    async def async_added_to_hass(self):
        """Register the entity and populate the initial state from the bus."""
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._platform] = self
        self.async_on_remove(
            self._hass.bus.async_listen(
                "myhome_scene_event",
                self._handle_scene_event,
            )
        )
        await self.async_update()

    async def async_update(self):
        """Refresh the current scene state from the scene programmer."""
        collected = await self._gateway_handler.send_status_request_collect(
            build_scene_programmer_command(self._scene, "query_status")
        )
        state = parse_scene_programmer_frames(collected["raw_frames"], self._scene)
        self._apply_scene_state(state, source="query")

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Start or enable the scene."""
        operation = "enable" if self._scene_role == SCENE_ENABLED_ROLE else "start"
        await self._gateway_handler.send(
            build_scene_programmer_command(self._scene, operation)
        )
        await self.async_update()

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        """Stop or disable the scene."""
        operation = "disable" if self._scene_role == SCENE_ENABLED_ROLE else "stop"
        await self._gateway_handler.send(
            build_scene_programmer_command(self._scene, operation)
        )
        await self.async_update()

    def _apply_scene_state(self, state: dict | None, *, source: str) -> None:
        if not state:
            return

        scene_state = (state.get("scenes") or {}).get(self._scene, state)
        if not isinstance(scene_state, dict):
            return

        if self._scene_role == SCENE_ENABLED_ROLE:
            if scene_state.get("is_enabled") is not None:
                self._attr_is_on = scene_state.get("is_enabled")
        else:
            if scene_state.get("is_on") is not None:
                self._attr_is_on = scene_state.get("is_on")

        if scene_state.get("active_state") is not None:
            self._attr_extra_state_attributes["active_state"] = scene_state.get(
                "active_state"
            )
        if scene_state.get("active_state_code") is not None:
            self._attr_extra_state_attributes["active_state_code"] = scene_state.get(
                "active_state_code"
            )
        if scene_state.get("enabled_state") is not None:
            self._attr_extra_state_attributes["enabled_state"] = scene_state.get(
                "enabled_state"
            )
        if scene_state.get("enabled_state_code") is not None:
            self._attr_extra_state_attributes["enabled_state_code"] = scene_state.get(
                "enabled_state_code"
            )
        if scene_state.get("is_enabled") is not None:
            self._attr_extra_state_attributes["is_enabled"] = scene_state.get(
                "is_enabled"
            )
        self._attr_extra_state_attributes["last_update_via"] = source

    def handle_event(self, message: OWNSceneEvent):
        """Handle WHO=17 scene events."""
        if int(message.scenario) != self._scene:
            return

        self._apply_scene_state(
            {
                "where": self._scene,
                "is_on": message.is_on,
                "is_enabled": message.is_enabled,
                "active_state_code": message.state if message.is_on is not None else None,
                "active_state": (
                    "started"
                    if message.state == 1
                    else "stopped"
                    if message.state == 2
                    else None
                ),
                "enabled_state_code": (
                    message.state if message.is_enabled is not None else None
                ),
                "enabled_state": (
                    "enabled"
                    if message.state == 3
                    else "disabled"
                    if message.state == 4
                    else None
                ),
            },
            source="event",
        )
        self.async_schedule_update_ha_state()

    @callback
    def _handle_scene_event(self, event) -> None:
        data = dict(event.data)
        if data.get("gateway_mac") != self._gateway_handler.mac:
            return
        if int(data.get("scene", -1)) != self._scene:
            return

        self._apply_scene_state(
            {
                "where": self._scene,
                "is_on": data.get("is_on"),
                "is_enabled": data.get("is_enabled"),
                "active_state_code": (
                    data.get("state") if data.get("is_on") is not None else None
                ),
                "active_state": (
                    "started"
                    if data.get("state") == 1
                    else "stopped"
                    if data.get("state") == 2
                    else None
                ),
                "enabled_state_code": (
                    data.get("state")
                    if data.get("is_enabled") is not None
                    else None
                ),
                "enabled_state": (
                    "enabled"
                    if data.get("state") == 3
                    else "disabled"
                    if data.get("state") == 4
                    else None
                ),
            },
            source="event",
        )
        self.async_write_ha_state()


class MyHOMELightManagementSwitch(MyHOMEEntity, SwitchEntity):
    """Represent a WHO=24 boolean lighting-management parameter."""

    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        icon: str,
        icon_on: str,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        operation: str | None,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        del interface
        del device_class
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

        self._operation = str(operation or "auto_switch_on")
        self._attr_name = entity_name or self._operation.replace("_", " ").title()
        self._attr_device_class = SwitchDeviceClass.SWITCH
        self._on_icon = icon_on or "mdi:toggle-switch"
        self._off_icon = icon or "mdi:toggle-switch-off-outline"
        self._attr_icon = self._off_icon
        self._attr_is_on = None
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
        await self.async_update()

    async def async_update(self):
        await self._gateway_handler.send_status_request_collect(
            build_light_management_request(self._operation, self._where)
        )
        self._apply_snapshot(
            self._gateway_handler.light_management.zone_snapshot(self._where)
        )
        self.async_schedule_update_ha_state()

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        await self._gateway_handler.send(
            build_light_management_command(
                f"set_{self._operation}",
                self._where,
                enabled=True,
            )
        )
        await self.async_update()

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        await self._gateway_handler.send(
            build_light_management_command(
                f"set_{self._operation}",
                self._where,
                enabled=False,
            )
        )
        await self.async_update()

    def _apply_snapshot(self, snapshot: dict | None) -> None:
        if not snapshot:
            return
        state = snapshot.get(self._operation)
        if state is None:
            return
        self._attr_is_on = bool(state)
        self._attr_icon = self._on_icon if self._attr_is_on else self._off_icon
        self._attr_extra_state_attributes["last_update"] = snapshot.get("last_update")

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


class MyHOMEAudioLoudnessSwitch(MyHOMEEntity, SwitchEntity):
    """Represent WHO=22 loudness as a native switch."""

    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        icon: str,
        icon_on: str,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        operation: str | None,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        del interface
        del operation
        del device_class
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
        self._area = int(area_text)
        self._point = int(point_text)
        self._attr_name = entity_name or "Loudness"
        self._attr_device_class = SwitchDeviceClass.SWITCH
        self._on_icon = icon_on or "mdi:volume-high"
        self._off_icon = icon or "mdi:volume-medium"
        self._attr_icon = self._off_icon
        self._attr_is_on = None
        self._attr_extra_state_attributes = {
            "area": self._area,
            "point": self._point,
            "audio_operation": "loudness",
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
        await self.async_update()

    async def async_update(self):
        await self._gateway_handler.send_status_request_collect(
            build_audio_zone_command(
                self._area,
                self._point,
                "query_loudness",
            )
        )
        self._apply_snapshot(
            self._gateway_handler.audio.zone_snapshot(self._area, self._point)
        )
        self.async_schedule_update_ha_state()

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        await self._gateway_handler.send(
            build_audio_zone_command(
                self._area,
                self._point,
                "set_loudness",
                value=1,
            )
        )
        await self.async_update()

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        await self._gateway_handler.send(
            build_audio_zone_command(
                self._area,
                self._point,
                "set_loudness",
                value=0,
            )
        )
        await self.async_update()

    def _apply_snapshot(self, snapshot: dict | None) -> None:
        if not snapshot or snapshot.get("loudness") is None:
            return
        self._attr_is_on = bool(snapshot.get("loudness"))
        self._attr_icon = self._on_icon if self._attr_is_on else self._off_icon
        self._attr_extra_state_attributes["last_update"] = snapshot.get("last_update")

    @callback
    def _handle_audio_feedback_event(self, event) -> None:
        data = dict(event.data)
        if data.get("gateway_mac") != self._gateway_handler.mac:
            return
        if int(data.get("area", -1)) != self._area:
            return
        if int(data.get("point", -1)) != self._point:
            return
        if data.get("kind") != "speaker_loudness":
            return
        self._apply_snapshot(
            self._gateway_handler.audio.zone_snapshot(self._area, self._point)
        )
        self.async_write_ha_state()
