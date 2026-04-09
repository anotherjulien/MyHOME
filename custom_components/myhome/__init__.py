""" MyHOME integration. """

import re
from datetime import date

import aiofiles
import yaml

from OWNd.message import OWNCommand, OWNGatewayCommand

from homeassistant.components.switch import DOMAIN as SWITCH
from homeassistant.components.camera import DOMAIN as CAMERA
from homeassistant.components.select import DOMAIN as SELECT
from homeassistant.components.text import DOMAIN as TEXT
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntry
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.components.event import DOMAIN as EVENT
from homeassistant.components.alarm_control_panel import DOMAIN as ALARM_CONTROL_PANEL
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.const import ATTR_ENTITY_ID, CONF_MAC

from .const import (
    ATTR_GATEWAY,
    ATTR_MESSAGE,
    CONF_PLATFORMS,
    CONF_ENTITY,
    CONF_ENTITIES,
    CONF_GATEWAY,
    CONF_WORKER_COUNT,
    CONF_FILE_PATH,
    CONF_GENERATE_EVENTS,
    CONF_WHO,
    DOMAIN,
    LOGGER,
)
from .validate import config_schema, format_mac
from .gateway import MyHOMEGatewayHandler
from .myhome_device import MyHOMEEntity
from .audio import (
    ATTR_AREA,
    ATTR_BANDS,
    ATTR_POINT,
    ATTR_QUERY_AFTER,
    ATTR_SOURCE,
    ATTR_SOURCE_ID,
    ATTR_STATION,
    ATTR_STEP,
    ATTR_VALUE,
    ATTR_VOLUME,
    SERVICE_AUDIO_GENERAL_COMMAND,
    SERVICE_AUDIO_RADIO_COMMAND,
    SERVICE_AUDIO_SOURCE_COMMAND,
    SERVICE_AUDIO_ZONE_COMMAND,
    build_audio_general_command,
    build_audio_radio_command,
    build_audio_source_command,
    build_audio_zone_command,
    normalize_equalization_bands,
)
from .camera import ensure_camera_platform_config
from .av import (
    ATTR_DIAL_COL,
    ATTR_DIAL_ROW,
    ATTR_OPERATION as ATTR_VIDEO_OPERATION,
    ATTR_WHERE as ATTR_VIDEO_WHERE,
    SERVICE_VIDEO_COMMAND,
    build_video_command,
)
from .alarm import (
    ATTR_CHANNEL,
    SERVICE_AUX_COMMAND,
    build_aux_command,
    ensure_alarm_platform_config,
)
from .alarm_request import (
    ATTR_REQUEST as ATTR_ALARM_REQUEST,
    ATTR_ZONE as ATTR_ALARM_ZONE,
    SERVICE_ALARM_REQUEST,
    build_alarm_request,
    build_alarm_response,
)
from .cen import (
    ATTR_OPERATION as ATTR_CEN_OPERATION,
    ATTR_PUSHBUTTON as ATTR_CEN_PUSHBUTTON,
    ATTR_WHERE as ATTR_CEN_WHERE,
    SERVICE_CEN_COMMAND,
    SERVICE_CENPLUS_COMMAND,
    build_cen_command,
    build_cenplus_command,
)
from .energy import (
    ATTR_DATE as ATTR_ENERGY_DATE,
    ATTR_MONTH as ATTR_ENERGY_MONTH,
    ATTR_REQUEST as ATTR_ENERGY_REQUEST,
    ATTR_WHERE as ATTR_ENERGY_WHERE,
    ATTR_YEAR as ATTR_ENERGY_YEAR,
    REQUEST_DAILY_HISTORY,
    REQUEST_HOURLY_HISTORY,
    REQUEST_MONTHLY_AVERAGE_HOURLY,
    REQUEST_MONTHLY_HISTORY,
    SERVICE_ENERGY_REQUEST,
    build_energy_request,
    build_energy_response,
)
from .event import ensure_event_platform_config
from .gateway_info import (
    ATTR_OPERATION as ATTR_GATEWAY_INFO_OPERATION,
    ATTR_REQUEST as ATTR_GATEWAY_INFO_REQUEST,
    ATTR_TIME_ZONE as ATTR_GATEWAY_INFO_TIME_ZONE,
    SERVICE_GATEWAY_COMMAND,
    SERVICE_GATEWAY_REQUEST,
    build_gateway_command,
    build_gateway_request,
    build_gateway_response,
)
from .light_management import (
    ATTR_ENABLED as ATTR_LM_ENABLED,
    ATTR_ERROR as ATTR_LM_ERROR,
    ATTR_EXIT_CONDITION as ATTR_LM_EXIT_CONDITION,
    ATTR_HOURS as ATTR_LM_HOURS,
    ATTR_LUX as ATTR_LM_LUX,
    ATTR_MINUTES as ATTR_LM_MINUTES,
    ATTR_MODE as ATTR_LM_MODE,
    ATTR_OPERATION as ATTR_LM_OPERATION,
    ATTR_PROFILE as ATTR_LM_PROFILE,
    ATTR_QUERY_AFTER as ATTR_LM_QUERY_AFTER,
    ATTR_REQUEST as ATTR_LM_REQUEST,
    ATTR_SECONDS as ATTR_LM_SECONDS,
    ATTR_SENSOR_ADDRESS as ATTR_LM_SENSOR_ADDRESS,
    ATTR_VALUE as ATTR_LM_VALUE,
    ATTR_WHERE as ATTR_LM_WHERE,
    SERVICE_LIGHT_MANAGEMENT_COMMAND,
    SERVICE_LIGHT_MANAGEMENT_REQUEST,
    build_light_management_command,
    build_light_management_request,
    build_light_management_response,
)
from .media_player import (
    ensure_media_player_platform_config,
    restore_media_player_platform_config,
)
from .scene_programmer import (
    ATTR_OPERATION as ATTR_SCENE_OPERATION,
    ATTR_WHERE as ATTR_SCENE_WHERE,
    SERVICE_SCENE_PROGRAMMER_COMMAND,
    build_scene_programmer_command,
    ensure_scene_switch_config,
    ensure_scene_switches_from_state,
    parse_scene_programmer_frames,
    restore_scene_switch_platform_config,
)
from .scenario import (
    ATTR_OPERATION as ATTR_SCENARIO_MODULE_OPERATION,
    ATTR_SCENARIO as ATTR_SCENARIO_ID,
    ATTR_WHERE as ATTR_SCENARIO_MODULE_WHERE,
    SERVICE_SCENARIO_COMMAND,
    build_scenario_command,
)
from .thermo import (
    ATTR_DATE,
    ATTR_DAYS,
    ATTR_FAN_MODE,
    ATTR_MODE_FAMILY,
    ATTR_OPERATION,
    ATTR_PROGRAM,
    ATTR_REQUEST,
    ATTR_SCENARIO,
    ATTR_SWING_MODE,
    ATTR_TEMPERATURE,
    ATTR_TIME,
    ATTR_WHERE,
    ATTR_ZONE,
    SERVICE_THERMO_CENTRAL_COMMAND,
    SERVICE_THERMO_REQUEST,
    SERVICE_THERMO_SPLIT_SET,
    SERVICE_THERMO_ZONE_COMMAND,
    build_central_command,
    build_request,
    build_split_set_command,
    build_zone_command,
)

PLATFORMS = [
    CAMERA,
    "light",
    "switch",
    "button",
    "number",
    SELECT,
    TEXT,
    "cover",
    "climate",
    "binary_sensor",
    "sensor",
    EVENT,
    ALARM_CONTROL_PANEL,
    MEDIA_PLAYER,
]
SUPPORTED_RAW_MESSAGE_RE = re.compile(r"^\*22\*(?:5|6|9|10)#\*2#\d+##$")


def _build_audio_equalization_feedback(
    gateway_handler: MyHOMEGatewayHandler,
    area: int | str,
    point: int | str,
    operation: str,
    bands: str | list[str] | tuple[str, ...] | None,
    raw_message: str | None = None,
) -> dict | None:
    if not str(operation).startswith("set_equalization_"):
        return None

    equalization = int(str(operation).rsplit("_", 1)[1])
    normalized_bands = normalize_equalization_bands(equalization, bands)
    feedback = {
        "kind": "speaker_equalization",
        "area": int(area),
        "point": int(point),
        "zone_key": f"{int(area)}_{int(point)}",
        "equalization": equalization,
        "bands": normalized_bands,
        "gateway": str(gateway_handler.gateway.host),
        "gateway_mac": gateway_handler.mac,
        "raw_message": raw_message,
    }
    gateway_handler.audio.handle_feedback(feedback)
    return feedback


def _primary_gateway_mac(hass: HomeAssistant) -> str | None:
    gateways = hass.data.get(DOMAIN, {})
    candidates = []
    for mac, gateway_data in gateways.items():
        handler = gateway_data.get(CONF_ENTITY)
        if handler is None:
            continue
        candidates.append(
            {
                "mac": mac,
                "has_platforms": bool(gateway_data.get(CONF_PLATFORMS)),
            }
        )

    if not candidates:
        return None

    primary = next((item for item in candidates if item["has_platforms"]), candidates[0])
    return primary["mac"]


def _select_gateway_for_send(hass: HomeAssistant, requested_gateway: str | None = None) -> str | None:
    gateways = hass.data.get(DOMAIN, {})
    if requested_gateway is not None:
        return requested_gateway if requested_gateway in gateways and CONF_ENTITY in gateways[requested_gateway] else None

    candidates = []
    for mac, gateway_data in gateways.items():
        handler = gateway_data.get(CONF_ENTITY)
        if handler is None:
            continue
        candidates.append(
            {
                "mac": mac,
                "pending": getattr(handler, "pending_messages", handler.send_buffer.qsize()),
                "has_platforms": bool(gateway_data.get(CONF_PLATFORMS)),
            }
        )

    if not candidates:
        return None

    primary = next((item for item in candidates if item["has_platforms"]), candidates[0])
    best = min(
        candidates,
        key=lambda item: (item["pending"], 0 if item["mac"] == primary["mac"] else 1),
    )
    selected = primary if primary["pending"] <= best["pending"] else best

    if selected["mac"] != primary["mac"]:
        LOGGER.debug(
            "Routing command to less busy gateway `%s` (pending=%s) instead of primary `%s` (pending=%s).",
            selected["mac"],
            selected["pending"],
            primary["mac"],
            primary["pending"],
        )

    return selected["mac"]


def _message_requires_listening_gateway(message: str | None) -> bool:
    if not message:
        return False
    return message.startswith("*#")


def _is_query_only_scene_gateway(
    gateway_data: dict,
    has_declared_platforms: bool,
) -> bool:
    if has_declared_platforms:
        return False

    configured_platforms = gateway_data.get(CONF_PLATFORMS, {})
    if set(configured_platforms) != {SWITCH}:
        return False

    switches = configured_platforms.get(SWITCH, {})
    return bool(switches) and all(
        device_config.get(CONF_WHO) == "17"
        for device_config in switches.values()
    )


async def _discover_scene_switches(gateway_handler, gateway_data: dict) -> list[int]:
    """Probe the scene programmer and create synthetic switches for discovered scenes."""
    collected = await gateway_handler.send_status_request_collect(
        build_scene_programmer_command(0, "query_status")
    )
    state = parse_scene_programmer_frames(collected["raw_frames"], 0)
    if not state or not state.get("scenes"):
        return []
    return ensure_scene_switches_from_state(gateway_data, state)


async def _async_refresh_load_switches(hass: HomeAssistant, gateway_mac: str) -> None:
    """Refresh WHO=18 switches after all entities have been registered."""
    gateway_data = hass.data.get(DOMAIN, {}).get(gateway_mac, {})
    for device_config in gateway_data.get(CONF_PLATFORMS, {}).get(SWITCH, {}).values():
        if device_config.get(CONF_WHO) != "18":
            continue

        switch_entity = device_config.get(CONF_ENTITIES, {}).get(SWITCH)
        if switch_entity is not None:
            await switch_entity.async_update()


def _normalize_entity_ids(entity_ids):
    if entity_ids is None:
        return None
    if isinstance(entity_ids, str):
        return [entity_ids]
    return list(entity_ids)


def _iter_thermo_climates(hass: HomeAssistant, entity_ids=None):
    entity_ids = _normalize_entity_ids(entity_ids)
    for gateway_data in hass.data.get(DOMAIN, {}).values():
        for device_config in gateway_data.get(CONF_PLATFORMS, {}).get("climate", {}).values():
            entity = device_config.get(CONF_ENTITIES, {}).get("climate")
            if entity is None:
                continue
            if entity_ids is None or entity.entity_id in entity_ids:
                yield entity


def _iter_energy_targets(hass: HomeAssistant, entity_ids=None):
    entity_ids = _normalize_entity_ids(entity_ids)
    seen = set()

    for gateway_data in hass.data.get(DOMAIN, {}).values():
        for platform_entities in gateway_data.get(CONF_PLATFORMS, {}).values():
            for device_config in platform_entities.values():
                if not isinstance(device_config, dict):
                    continue
                for entity in device_config.get(CONF_ENTITIES, {}).values():
                    if not isinstance(entity, MyHOMEEntity):
                        continue
                    if getattr(entity, "_who", None) != "18":
                        continue
                    if entity_ids is not None and entity.entity_id not in entity_ids:
                        continue

                    key = (entity._gateway_handler.mac, entity._where)  # noqa: SLF001
                    if key in seen:
                        continue
                    seen.add(key)
                    yield entity


def _resolve_gateway_mac(hass: HomeAssistant, gateway: str | None, response_oriented: bool = False) -> str | None:
    if gateway is not None:
        mac = format_mac(gateway)
        if mac is None:
            return None
        return mac
    if response_oriented:
        return _primary_gateway_mac(hass)
    return _select_gateway_for_send(hass)


async def _collect_status_requests(gateway_handler, messages: str | list[str]) -> dict:
    if isinstance(messages, str):
        messages = [messages]

    raw_frames: list[str] = []
    success = False
    acknowledged = False

    for message in messages:
        collected = await gateway_handler.send_status_request_collect(message)
        raw_frames.extend(collected["raw_frames"])
        success = success or collected["success"]
        acknowledged = acknowledged or collected["acknowledged"]

    return {
        "success": success,
        "acknowledged": acknowledged,
        "raw_frames": raw_frames,
    }


async def async_setup(hass, config):
    """Set up the MyHOME component."""
    hass.data[DOMAIN] = {}

    if DOMAIN not in config:
        return True

    LOGGER.error("configuration.yaml not supported for this component!")

    return False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up MyHOME from a config entry."""
    if entry.data[CONF_MAC] not in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.data[CONF_MAC]] = {}

    _config_file_path = (
        str(entry.options[CONF_FILE_PATH])
        if CONF_FILE_PATH in entry.options
        else "/config/myhome.yaml"
    )
    _generate_events = (
        entry.options[CONF_GENERATE_EVENTS]
        if CONF_GENERATE_EVENTS in entry.options
        else False
    )

    try:
        async with aiofiles.open(_config_file_path, mode="r") as yaml_file:
            _validated_config = config_schema(yaml.safe_load(await yaml_file.read()))
    except FileNotFoundError:
        LOGGER.error("Configuration file '%s' is not present!", _config_file_path)
        return False

    if entry.data[CONF_MAC] in _validated_config:
        hass.data[DOMAIN][entry.data[CONF_MAC]] = _validated_config[
            entry.data[CONF_MAC]
        ]
        _has_declared_platforms = bool(
            hass.data[DOMAIN][entry.data[CONF_MAC]].get(CONF_PLATFORMS)
        )
        ensure_camera_platform_config(
            hass.data[DOMAIN][entry.data[CONF_MAC]],
            entry.data,
        )
        ensure_alarm_platform_config(hass.data[DOMAIN][entry.data[CONF_MAC]])
        if _has_declared_platforms:
            ensure_media_player_platform_config(
                hass.data[DOMAIN][entry.data[CONF_MAC]]
            )
            hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS].setdefault(
                "number",
                {},
            )
            hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS].setdefault(
                SWITCH,
                hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS].get(
                    SWITCH,
                    {},
                ),
            )
            ensure_event_platform_config(hass.data[DOMAIN][entry.data[CONF_MAC]])
    else:
        LOGGER.error(
            "Gateway MAC '%s' not found in configuration file '%s'.",
            entry.data[CONF_MAC],
            _config_file_path,
        )
        return False

    # Migrate config entry unique_id if not formatted to Home Assistant standard
    if entry.unique_id != dr.format_mac(entry.unique_id):
        hass.config_entries.async_update_entry(
            entry, unique_id=dr.format_mac(entry.unique_id)
        )
        LOGGER.warning("Migrating config entry unique_id to %s", entry.unique_id)

    hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY] = MyHOMEGatewayHandler(
        hass=hass, config_entry=entry, generate_events=_generate_events
    )

    try:
        tests_results = await hass.data[DOMAIN][entry.data[CONF_MAC]][
            CONF_ENTITY
        ].test()
    except OSError as ose:
        _host = entry.data.get(CONF_GATEWAY, "unknown")
        raise ConfigEntryNotReady(
            f"Gateway cannot be reached at {_host}, make sure its address is correct."
        ) from ose

    if not tests_results["Success"]:
        if tests_results["Message"] in ("password_error", "password_required"):
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_REAUTH},
                    data=entry.data,
                )
            )
        del hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY]
        return False

    _command_worker_count = (
        int(entry.options[CONF_WORKER_COUNT])
        if CONF_WORKER_COUNT in entry.options
        else 1
    )

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    entity_entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    restore_scene_switch_platform_config(
        hass.data[DOMAIN][entry.data[CONF_MAC]],
        entity_entries,
        entry.data[CONF_MAC],
    )
    if MEDIA_PLAYER in hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS]:
        restore_media_player_platform_config(
            hass.data[DOMAIN][entry.data[CONF_MAC]],
            entity_entries,
            entry.data[CONF_MAC],
        )
        entity_entries = er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        )

    discovered_scenes = []
    if not _has_declared_platforms:
        discovered_scenes = await _discover_scene_switches(
            hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY],
            hass.data[DOMAIN][entry.data[CONF_MAC]],
        )
        if discovered_scenes:
            LOGGER.info(
                "%s Discovered %s scene programmer scene(s) on auxiliary gateway.",
                hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].log_id,
                len(discovered_scenes),
            )

    if not _has_declared_platforms:
        for entity_entry in entity_entries:
            if entity_entry.platform != DOMAIN:
                continue
            if entity_entry.domain not in {EVENT, MEDIA_PLAYER, ALARM_CONTROL_PANEL}:
                continue
            entity_registry.async_remove(entity_entry.entity_id)
        entity_entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)

    platforms_to_keep_if_empty = set()
    switch_devices = hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS].get(
        SWITCH,
        {},
    )
    camera_devices = hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS].get(
        CAMERA,
        {},
    )
    media_player_devices = hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS].get(
        MEDIA_PLAYER,
        {},
    )
    if camera_devices:
        hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS].setdefault(
            "button",
            {},
        )
    if media_player_devices:
        hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS].setdefault(
            "button",
            {},
        )
        hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS].setdefault(
            "binary_sensor",
            {},
        )
        hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS].setdefault(
            "sensor",
            {},
        )
        hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS].setdefault(
            TEXT,
            {},
        )
    if media_player_devices or any(
        device_config.get(CONF_WHO) == "18"
        for device_config in switch_devices.values()
    ):
        platforms_to_keep_if_empty.add("number")
    if camera_devices or media_player_devices:
        platforms_to_keep_if_empty.add("button")
    if media_player_devices:
        platforms_to_keep_if_empty.add("binary_sensor")
    if media_player_devices:
        platforms_to_keep_if_empty.add("sensor")
        platforms_to_keep_if_empty.add(TEXT)

    hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS] = {
        platform: devices
        for platform, devices in hass.data[DOMAIN][entry.data[CONF_MAC]][
            CONF_PLATFORMS
        ].items()
        if devices or platform in platforms_to_keep_if_empty
    }

    gateway_device_entry = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, entry.data[CONF_MAC])},
        identifiers={
            (DOMAIN, hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].unique_id)
        },
        manufacturer=hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].manufacturer,
        name=hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].name,
        model=hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].model,
        sw_version=hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].firmware,
    )

    _configured_platforms = hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS]
    _has_platforms = bool(_configured_platforms)
    _query_only_scene_gateway = _is_query_only_scene_gateway(
        hass.data[DOMAIN][entry.data[CONF_MAC]],
        _has_declared_platforms,
    )

    for i in range(_command_worker_count):
        hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].sending_workers.append(
            hass.loop.create_task(
                hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].sending_loop(i)
            )
        )

    if _has_platforms:
        await hass.config_entries.async_forward_entry_setups(
            entry, _configured_platforms.keys()
        )
        if _query_only_scene_gateway:
            LOGGER.info(
                "%s Loaded query-only scene programmer entities; keeping gateway without event listener.",
                hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].log_id,
            )
        else:
            hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].listening_worker = (
                hass.loop.create_task(
                    hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].listening_loop()
                )
            )
        hass.async_create_task(
            _async_refresh_load_switches(hass, entry.data[CONF_MAC])
        )
    else:
        LOGGER.info(
            "%s No platforms configured in `%s`; enabling gateway as send-only auxiliary gateway.",
            hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_ENTITY].log_id,
            _config_file_path,
        )

    # Prune loose entities and devices from registry
    entities_to_be_removed = []
    devices_to_be_removed = [
        device_entry.id
        for device_entry in device_registry.devices.values()
        if entry.entry_id in device_entry.config_entries
    ]

    configured_entities = []

    for _platform in hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS].keys():
        for _device in hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS][
            _platform
        ].keys():
            for _entity_name in hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS][
                _platform
            ][_device][CONF_ENTITIES]:
                if _entity_name != _platform:
                    configured_entities.append(
                        f"{entry.data[CONF_MAC]}-{_device}-{_entity_name}"
                    )
                else:
                    configured_entities.append(f"{entry.data[CONF_MAC]}-{_device}")

    for entity_entry in entity_entries:
        if entity_entry.unique_id in configured_entities:
            if entity_entry.device_id in devices_to_be_removed:
                devices_to_be_removed.remove(entity_entry.device_id)
            continue
        entities_to_be_removed.append(entity_entry.entity_id)

    for entity_id in entities_to_be_removed:
        entity_registry.async_remove(entity_id)

    if gateway_device_entry.id in devices_to_be_removed:
        devices_to_be_removed.remove(gateway_device_entry.id)

    for device_id in devices_to_be_removed:
        if (
            len(
                er.async_entries_for_device(
                    entity_registry, device_id, include_disabled_entities=True
                )
            )
            == 0
        ):
            device_registry.async_remove_device(device_id)

    # Services
    async def handle_sync_time(call):
        """Synchronize date/time on the gateway."""
        gateway = call.data.get(ATTR_GATEWAY, None)
        if gateway is None:
            gateway = _select_gateway_for_send(hass)
        else:
            mac = format_mac(gateway)
            if mac is None:
                LOGGER.error(
                    "Invalid gateway mac `%s`, could not send time synchronisation message.",
                    gateway,
                )
                return False
            gateway = mac

        timezone = hass.config.time_zone

        if gateway not in hass.data[DOMAIN]:
            LOGGER.error(
                "Gateway `%s` not found, could not send time synchronisation message.",
                gateway,
            )
            return False

        try:
            own_message = await hass.async_add_executor_job(
                OWNGatewayCommand.set_datetime_to_now,
                timezone,
            )
            await hass.data[DOMAIN][gateway][CONF_ENTITY].send(own_message)
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error(
                "Could not build/send time synchronisation message to gateway `%s`: %s",
                gateway,
                err,
            )
            return False

        return True

    if not hass.services.has_service(DOMAIN, "sync_time"):
        hass.services.async_register(DOMAIN, "sync_time", handle_sync_time)

    async def handle_send_message(call):
        """Send a raw OpenWebNet message."""
        gateway = call.data.get(ATTR_GATEWAY, None)
        message = call.data.get(ATTR_MESSAGE, None)

        if gateway is None:
            if _message_requires_listening_gateway(message):
                gateway = _primary_gateway_mac(hass)
                LOGGER.debug(
                    "Routing response-oriented message `%s` to primary listening gateway `%s`.",
                    message,
                    gateway,
                )
            else:
                gateway = _select_gateway_for_send(hass)
        else:
            mac = format_mac(gateway)
            if mac is None:
                LOGGER.error(
                    "Invalid gateway mac `%s`, could not send message `%s`.",
                    gateway,
                    message,
                )
                return False
            gateway = mac

        LOGGER.debug("Handling message `%s` to be sent to `%s`", message, gateway)

        if gateway not in hass.data[DOMAIN]:
            LOGGER.error(
                "Gateway `%s` not found, could not send message `%s`.",
                gateway,
                message,
            )
            return False

        if message is None:
            LOGGER.error("No message provided, not sending anything.")
            return False

        own_message = OWNCommand.parse(message)
        if own_message is None or not own_message.is_valid:
            if SUPPORTED_RAW_MESSAGE_RE.match(message):
                LOGGER.debug(
                    "%s Sending supported raw OpenWebNet Message: `%s`",
                    hass.data[DOMAIN][gateway][CONF_ENTITY].log_id,
                    message,
                )
                await hass.data[DOMAIN][gateway][CONF_ENTITY].send(message)
                return True
            if own_message is None:
                LOGGER.error("Could not parse message `%s`, not sending it.", message)
            else:
                LOGGER.error("Invalid OpenWebNet message `%s`, not sending it.", message)
            return False

        LOGGER.debug(
            "%s Sending valid OpenWebNet Message: `%s`",
            hass.data[DOMAIN][gateway][CONF_ENTITY].log_id,
            own_message,
        )
        await hass.data[DOMAIN][gateway][CONF_ENTITY].send(own_message)

        return True

    if not hass.services.has_service(DOMAIN, "send_message"):
        hass.services.async_register(DOMAIN, "send_message", handle_send_message)

    async def handle_gateway_request(call):
        request = call.data.get(ATTR_GATEWAY_INFO_REQUEST)

        if request is None:
            LOGGER.error("No `%s` provided for gateway request.", ATTR_GATEWAY_INFO_REQUEST)
            return {"success": False}

        gateway = _resolve_gateway_mac(
            hass,
            call.data.get(ATTR_GATEWAY),
            response_oriented=True,
        )
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for gateway request.", gateway)
            return {"success": False}

        try:
            messages = build_gateway_request(str(request))
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build gateway request: %s", err)
            return {"success": False}

        collected = await _collect_status_requests(
            hass.data[DOMAIN][gateway][CONF_ENTITY],
            messages,
        )
        result = build_gateway_response(collected["raw_frames"])
        result.update(
            {
                "success": collected["success"],
                "acknowledged": collected["acknowledged"],
                "gateway": gateway,
                "request": str(request),
                "raw_frames": collected["raw_frames"],
            }
        )
        return result

    if not hass.services.has_service(DOMAIN, SERVICE_GATEWAY_REQUEST):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GATEWAY_REQUEST,
            handle_gateway_request,
            supports_response=SupportsResponse.ONLY,
        )

    async def handle_gateway_command(call):
        operation = call.data.get(ATTR_GATEWAY_INFO_OPERATION)

        if operation is None:
            LOGGER.error("No `%s` provided for gateway command.", ATTR_GATEWAY_INFO_OPERATION)
            return {"success": False}

        gateway = _resolve_gateway_mac(hass, call.data.get(ATTR_GATEWAY))
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for gateway command.", gateway)
            return {"success": False}

        time_zone = str(call.data.get(ATTR_GATEWAY_INFO_TIME_ZONE) or hass.config.time_zone)

        try:
            message = await hass.async_add_executor_job(
                build_gateway_command,
                str(operation),
                time_zone,
            )
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build gateway command: %s", err)
            return {"success": False}

        await hass.data[DOMAIN][gateway][CONF_ENTITY].send(message)
        return {
            "success": True,
            "gateway": gateway,
            "operation": str(operation),
            "time_zone": time_zone,
            "message": str(message),
        }

    if not hass.services.has_service(DOMAIN, SERVICE_GATEWAY_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GATEWAY_COMMAND,
            handle_gateway_command,
            supports_response=SupportsResponse.OPTIONAL,
        )

    async def handle_scenario_command(call):
        operation = call.data.get(ATTR_SCENARIO_MODULE_OPERATION)
        where = call.data.get(ATTR_SCENARIO_MODULE_WHERE)
        scenario = call.data.get(ATTR_SCENARIO_ID)

        if operation is None:
            LOGGER.error("No `%s` provided for scenario command.", ATTR_SCENARIO_MODULE_OPERATION)
            return {"success": False}
        if where is None:
            LOGGER.error("No `%s` provided for scenario command.", ATTR_SCENARIO_MODULE_WHERE)
            return {"success": False}

        gateway = _resolve_gateway_mac(hass, call.data.get(ATTR_GATEWAY))
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for scenario command.", gateway)
            return {"success": False}

        try:
            message = build_scenario_command(where, str(operation), scenario)
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build scenario command: %s", err)
            return {"success": False}

        await hass.data[DOMAIN][gateway][CONF_ENTITY].send(message)
        return {
            "success": True,
            "gateway": gateway,
            "operation": str(operation),
            "where": str(where),
            "scenario": None if scenario is None else int(scenario),
            "message": message,
        }

    if not hass.services.has_service(DOMAIN, SERVICE_SCENARIO_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SCENARIO_COMMAND,
            handle_scenario_command,
            supports_response=SupportsResponse.OPTIONAL,
        )

    async def handle_cen_command(call):
        operation = call.data.get(ATTR_CEN_OPERATION)
        where = call.data.get(ATTR_CEN_WHERE)
        pushbutton = call.data.get(ATTR_CEN_PUSHBUTTON)

        if operation is None:
            LOGGER.error("No `%s` provided for CEN command.", ATTR_CEN_OPERATION)
            return {"success": False}
        if where is None or pushbutton is None:
            LOGGER.error("CEN command requires `%s` and `%s`.", ATTR_CEN_WHERE, ATTR_CEN_PUSHBUTTON)
            return {"success": False}

        gateway = _resolve_gateway_mac(hass, call.data.get(ATTR_GATEWAY))
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for CEN command.", gateway)
            return {"success": False}

        try:
            message = build_cen_command(where, pushbutton, str(operation))
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build CEN command: %s", err)
            return {"success": False}

        await hass.data[DOMAIN][gateway][CONF_ENTITY].send(message)
        return {
            "success": True,
            "gateway": gateway,
            "operation": str(operation),
            "where": str(where),
            "pushbutton": int(pushbutton),
            "message": message,
        }

    if not hass.services.has_service(DOMAIN, SERVICE_CEN_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CEN_COMMAND,
            handle_cen_command,
            supports_response=SupportsResponse.OPTIONAL,
        )

    async def handle_cenplus_command(call):
        operation = call.data.get(ATTR_CEN_OPERATION)
        where = call.data.get(ATTR_CEN_WHERE)
        pushbutton = call.data.get(ATTR_CEN_PUSHBUTTON)

        if operation is None:
            LOGGER.error("No `%s` provided for CEN Plus command.", ATTR_CEN_OPERATION)
            return {"success": False}
        if where is None or pushbutton is None:
            LOGGER.error(
                "CEN Plus command requires `%s` and `%s`.",
                ATTR_CEN_WHERE,
                ATTR_CEN_PUSHBUTTON,
            )
            return {"success": False}

        gateway = _resolve_gateway_mac(hass, call.data.get(ATTR_GATEWAY))
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for CEN Plus command.", gateway)
            return {"success": False}

        try:
            message = build_cenplus_command(where, pushbutton, str(operation))
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build CEN Plus command: %s", err)
            return {"success": False}

        await hass.data[DOMAIN][gateway][CONF_ENTITY].send(message)
        return {
            "success": True,
            "gateway": gateway,
            "operation": str(operation),
            "where": str(where),
            "pushbutton": int(pushbutton),
            "message": message,
        }

    if not hass.services.has_service(DOMAIN, SERVICE_CENPLUS_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CENPLUS_COMMAND,
            handle_cenplus_command,
            supports_response=SupportsResponse.OPTIONAL,
        )

    async def handle_alarm_request(call):
        request = call.data.get(ATTR_ALARM_REQUEST)
        zone = call.data.get(ATTR_ALARM_ZONE)

        if request is None:
            LOGGER.error("No `%s` provided for alarm request.", ATTR_ALARM_REQUEST)
            return {"success": False}

        gateway = _resolve_gateway_mac(
            hass,
            call.data.get(ATTR_GATEWAY),
            response_oriented=True,
        )
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for alarm request.", gateway)
            return {"success": False}

        try:
            message = build_alarm_request(str(request), zone)
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build alarm request: %s", err)
            return {"success": False}

        collected = await hass.data[DOMAIN][gateway][CONF_ENTITY].send_status_request_collect(
            message
        )
        result = build_alarm_response(collected["raw_frames"])
        result.update(
            {
                "success": collected["success"],
                "acknowledged": collected["acknowledged"],
                "gateway": gateway,
                "request": str(request),
                "raw_frames": collected["raw_frames"],
            }
        )
        if zone is not None:
            result["zone"] = int(zone)
        return result

    if not hass.services.has_service(DOMAIN, SERVICE_ALARM_REQUEST):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ALARM_REQUEST,
            handle_alarm_request,
            supports_response=SupportsResponse.ONLY,
        )

    async def handle_aux_command(call):
        operation = call.data.get(ATTR_OPERATION)
        channel = call.data.get(ATTR_CHANNEL)

        if operation is None:
            LOGGER.error("No `%s` provided for aux command.", ATTR_OPERATION)
            return {"success": False}
        if channel is None:
            LOGGER.error("No `%s` provided for aux command.", ATTR_CHANNEL)
            return {"success": False}

        gateway = _resolve_gateway_mac(hass, call.data.get(ATTR_GATEWAY))
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for aux command.", gateway)
            return {"success": False}

        try:
            message = build_aux_command(channel, operation)
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build aux command: %s", err)
            return {"success": False}

        await hass.data[DOMAIN][gateway][CONF_ENTITY].send(message)
        return {
            "success": True,
            "gateway": gateway,
            "channel": int(channel),
            "operation": str(operation),
            "message": message,
        }

    if not hass.services.has_service(DOMAIN, SERVICE_AUX_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_AUX_COMMAND,
            handle_aux_command,
            supports_response=SupportsResponse.OPTIONAL,
        )

    async def handle_audio_zone_command(call):
        operation = call.data.get(ATTR_OPERATION)
        area = call.data.get(ATTR_AREA)
        point = call.data.get(ATTR_POINT)
        query_after = bool(call.data.get(ATTR_QUERY_AFTER, False))

        if operation is None:
            LOGGER.error("No `%s` provided for audio zone command.", ATTR_OPERATION)
            return {"success": False}
        if area is None or point is None:
            LOGGER.error("Audio zone command requires `%s` and `%s`.", ATTR_AREA, ATTR_POINT)
            return {"success": False}

        gateway = _resolve_gateway_mac(
            hass,
            call.data.get(ATTR_GATEWAY),
            response_oriented=operation.startswith("query") or query_after,
        )
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for audio zone command.", gateway)
            return {"success": False}

        gateway_handler = hass.data[DOMAIN][gateway][CONF_ENTITY]
        is_query = str(operation).startswith("query")
        try:
            message = build_audio_zone_command(
                area,
                point,
                str(operation),
                source_id=call.data.get(ATTR_SOURCE_ID),
                source=call.data.get(ATTR_SOURCE),
                volume=call.data.get(ATTR_VOLUME),
                step=call.data.get(ATTR_STEP),
                mmtype=call.data.get("mmtype"),
                value=call.data.get(ATTR_VALUE),
                bands=call.data.get(ATTR_BANDS),
            )
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build audio zone command: %s", err)
            return {"success": False}

        if isinstance(message, list) or is_query or query_after:
            if not isinstance(message, list):
                if not is_query:
                    await gateway_handler.send(message)
                    feedback = _build_audio_equalization_feedback(
                        gateway_handler,
                        area,
                        point,
                        str(operation),
                        call.data.get(ATTR_BANDS),
                        raw_message=message,
                    )
                    if feedback is not None:
                        hass.bus.async_fire("myhome_audio_feedback_event", feedback)
                    message = build_audio_zone_command(area, point, "query_state")
            collected = await _collect_status_requests(gateway_handler, message)
            return {
                "success": collected["success"],
                "acknowledged": collected["acknowledged"],
                "gateway": gateway,
                "area": int(area),
                "point": int(point),
                "raw_frames": collected["raw_frames"],
                "state": gateway_handler.audio.zone_snapshot(area, point),
            }

        await gateway_handler.send(message)
        feedback = _build_audio_equalization_feedback(
            gateway_handler,
            area,
            point,
            str(operation),
            call.data.get(ATTR_BANDS),
            raw_message=message,
        )
        if feedback is not None:
            hass.bus.async_fire("myhome_audio_feedback_event", feedback)
        return {
            "success": True,
            "gateway": gateway,
            "area": int(area),
            "point": int(point),
        }

    if not hass.services.has_service(DOMAIN, SERVICE_AUDIO_ZONE_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_AUDIO_ZONE_COMMAND,
            handle_audio_zone_command,
            supports_response=SupportsResponse.OPTIONAL,
        )

    async def handle_audio_general_command(call):
        operation = call.data.get(ATTR_OPERATION)

        if operation is None:
            LOGGER.error("No `%s` provided for audio general command.", ATTR_OPERATION)
            return {"success": False}

        gateway = _resolve_gateway_mac(hass, call.data.get(ATTR_GATEWAY))
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for audio general command.", gateway)
            return {"success": False}

        try:
            message = build_audio_general_command(
                str(operation),
                source_id=call.data.get(ATTR_SOURCE_ID),
                source=call.data.get(ATTR_SOURCE),
                step=call.data.get(ATTR_STEP),
            )
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build audio general command: %s", err)
            return {"success": False}

        await hass.data[DOMAIN][gateway][CONF_ENTITY].send(message)
        return {"success": True, "gateway": gateway}

    if not hass.services.has_service(DOMAIN, SERVICE_AUDIO_GENERAL_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_AUDIO_GENERAL_COMMAND,
            handle_audio_general_command,
            supports_response=SupportsResponse.OPTIONAL,
        )

    async def handle_audio_source_command(call):
        operation = call.data.get(ATTR_OPERATION)
        source_id = call.data.get(ATTR_SOURCE_ID)
        query_after = bool(call.data.get(ATTR_QUERY_AFTER, False))

        if operation is None:
            LOGGER.error("No `%s` provided for audio source command.", ATTR_OPERATION)
            return {"success": False}
        if source_id is None:
            LOGGER.error("Audio source command requires `%s`.", ATTR_SOURCE_ID)
            return {"success": False}

        gateway = _resolve_gateway_mac(
            hass,
            call.data.get(ATTR_GATEWAY),
            response_oriented=operation.startswith("query") or query_after,
        )
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for audio source command.", gateway)
            return {"success": False}

        gateway_handler = hass.data[DOMAIN][gateway][CONF_ENTITY]
        is_query = str(operation).startswith("query")
        try:
            message = build_audio_source_command(
                str(operation),
                source_id=source_id,
                area=call.data.get(ATTR_AREA),
                mmtype=call.data.get("mmtype"),
                step=call.data.get(ATTR_STEP),
                station=call.data.get(ATTR_STATION),
            )
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build audio source command: %s", err)
            return {"success": False}

        if isinstance(message, list) or is_query or query_after:
            if not isinstance(message, list):
                if not is_query:
                    await gateway_handler.send(message)
                    message = build_audio_source_command(
                        "query_status",
                        source_id=source_id,
                    )
            collected = await _collect_status_requests(gateway_handler, message)
            return {
                "success": collected["success"],
                "acknowledged": collected["acknowledged"],
                "gateway": gateway,
                "source_id": int(source_id),
                "raw_frames": collected["raw_frames"],
                "state": gateway_handler.audio.source_snapshot(source_id),
            }

        await gateway_handler.send(message)
        return {
            "success": True,
            "gateway": gateway,
            "source_id": int(source_id),
        }

    if not hass.services.has_service(DOMAIN, SERVICE_AUDIO_SOURCE_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_AUDIO_SOURCE_COMMAND,
            handle_audio_source_command,
            supports_response=SupportsResponse.OPTIONAL,
        )

    async def handle_audio_radio_command(call):
        operation = call.data.get(ATTR_OPERATION)
        query_after = bool(call.data.get(ATTR_QUERY_AFTER, False))

        if operation is None:
            LOGGER.error("No `%s` provided for audio radio command.", ATTR_OPERATION)
            return {"success": False}

        gateway = _resolve_gateway_mac(
            hass,
            call.data.get(ATTR_GATEWAY),
            response_oriented=operation.startswith("query") or query_after,
        )
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for audio radio command.", gateway)
            return {"success": False}

        gateway_handler = hass.data[DOMAIN][gateway][CONF_ENTITY]
        try:
            message = build_audio_radio_command(str(operation))
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build audio radio command: %s", err)
            return {"success": False}

        if operation == "query_status" or query_after:
            if operation != "query_status":
                await gateway_handler.send(message)
                message = build_audio_radio_command("query_status")
            collected = await _collect_status_requests(gateway_handler, message)
            return {
                "success": collected["success"],
                "acknowledged": collected["acknowledged"],
                "gateway": gateway,
                "source_id": 1,
                "raw_frames": collected["raw_frames"],
                "state": gateway_handler.audio.radio_snapshot(),
            }

        await gateway_handler.send(message)
        return {"success": True, "gateway": gateway, "source_id": 1}

    if not hass.services.has_service(DOMAIN, SERVICE_AUDIO_RADIO_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_AUDIO_RADIO_COMMAND,
            handle_audio_radio_command,
            supports_response=SupportsResponse.OPTIONAL,
        )

    async def handle_scene_programmer_command(call):
        operation = call.data.get(ATTR_SCENE_OPERATION)
        where = call.data.get(ATTR_SCENE_WHERE)

        if operation is None:
            LOGGER.error(
                "No `%s` provided for scene programmer command.",
                ATTR_SCENE_OPERATION,
            )
            return {"success": False}
        if where is None:
            LOGGER.error(
                "No `%s` provided for scene programmer command.",
                ATTR_SCENE_WHERE,
            )
            return {"success": False}

        gateway = _resolve_gateway_mac(hass, call.data.get(ATTR_GATEWAY))
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error(
                "Gateway `%s` not found for scene programmer command.",
                gateway,
            )
            return {"success": False}

        gateway_handler = hass.data[DOMAIN][gateway][CONF_ENTITY]
        try:
            message = build_scene_programmer_command(where, str(operation))
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build scene programmer command: %s", err)
            return {"success": False}

        if str(operation) == "query_status":
            collected = await _collect_status_requests(gateway_handler, message)
            state = parse_scene_programmer_frames(
                collected["raw_frames"],
                where,
            )
            if state is not None:
                gateway_data = hass.data[DOMAIN][gateway]
                existing_scene_switches = [
                    device_config
                    for device_config in gateway_data.get(CONF_PLATFORMS, {})
                    .get(SWITCH, {})
                    .values()
                    if device_config.get(CONF_WHO) == "17"
                ]
                if not existing_scene_switches:
                    if int(where) == 0:
                        created_scene_ids = ensure_scene_switches_from_state(
                            gateway_data,
                            state,
                        )
                    else:
                        ensure_scene_switch_config(gateway_data, int(where))
                        created_scene_ids = [int(where)]

                    if created_scene_ids:
                        scene_entities_present = any(
                            device_config.get(CONF_WHO) == "17"
                            and SWITCH in device_config.get(CONF_ENTITIES, {})
                            for device_config in gateway_data.get(CONF_PLATFORMS, {})
                            .get(SWITCH, {})
                            .values()
                        )
                        if not scene_entities_present:
                            await hass.config_entries.async_forward_entry_setups(
                                gateway_handler.config_entry,
                                [SWITCH],
                            )
            return {
                "success": collected["success"],
                "acknowledged": collected["acknowledged"],
                "gateway": gateway,
                "where": int(where),
                "raw_frames": collected["raw_frames"],
                "state": state,
            }

        await gateway_handler.send(message)
        return {
            "success": True,
            "gateway": gateway,
            "where": int(where),
            "message": message,
        }

    if not hass.services.has_service(DOMAIN, SERVICE_SCENE_PROGRAMMER_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SCENE_PROGRAMMER_COMMAND,
            handle_scene_programmer_command,
            supports_response=SupportsResponse.OPTIONAL,
        )

    async def handle_video_command(call):
        operation = call.data.get(ATTR_VIDEO_OPERATION)

        if operation is None:
            LOGGER.error("No `%s` provided for video command.", ATTR_VIDEO_OPERATION)
            return {"success": False}

        gateway = _resolve_gateway_mac(hass, call.data.get(ATTR_GATEWAY))
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for video command.", gateway)
            return {"success": False}

        try:
            message = build_video_command(
                str(operation),
                where=call.data.get(ATTR_VIDEO_WHERE),
                dial_row=call.data.get(ATTR_DIAL_ROW),
                dial_col=call.data.get(ATTR_DIAL_COL),
            )
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build video command: %s", err)
            return {"success": False}

        await hass.data[DOMAIN][gateway][CONF_ENTITY].send(message)
        response = {"success": True, "gateway": gateway, "message": message}
        if call.data.get(ATTR_VIDEO_WHERE) is not None:
            response["where"] = int(call.data[ATTR_VIDEO_WHERE])
        return response

    if not hass.services.has_service(DOMAIN, SERVICE_VIDEO_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_VIDEO_COMMAND,
            handle_video_command,
            supports_response=SupportsResponse.OPTIONAL,
        )

    async def handle_light_management_request(call):
        request = call.data.get(ATTR_LM_REQUEST)
        where = call.data.get(ATTR_LM_WHERE)

        if request is None:
            LOGGER.error(
                "No `%s` provided for lighting management request.",
                ATTR_LM_REQUEST,
            )
            return {"results": []}
        if where is None:
            LOGGER.error(
                "No `%s` provided for lighting management request.",
                ATTR_LM_WHERE,
            )
            return {"results": []}

        gateway = _resolve_gateway_mac(
            hass,
            call.data.get(ATTR_GATEWAY),
            response_oriented=True,
        )
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error(
                "Gateway `%s` not found for lighting management request.",
                gateway,
            )
            return {"results": []}

        try:
            message = build_light_management_request(
                request,
                where,
                sensor_address=call.data.get(ATTR_LM_SENSOR_ADDRESS),
            )
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error(
                "Could not build lighting management request `%s`: %s",
                request,
                err,
            )
            return {"results": []}

        collected = await _collect_status_requests(
            hass.data[DOMAIN][gateway][CONF_ENTITY],
            message,
        )
        result = build_light_management_response(
            request,
            collected["raw_frames"],
            where=where,
        )
        result.update(
            {
                "gateway": gateway,
                "where": str(where),
                "success": collected["success"],
                "acknowledged": collected["acknowledged"],
            }
        )
        return {"results": [result]}

    if not hass.services.has_service(DOMAIN, SERVICE_LIGHT_MANAGEMENT_REQUEST):
        hass.services.async_register(
            DOMAIN,
            SERVICE_LIGHT_MANAGEMENT_REQUEST,
            handle_light_management_request,
            supports_response=SupportsResponse.ONLY,
        )

    async def handle_light_management_command(call):
        operation = call.data.get(ATTR_LM_OPERATION)
        where = call.data.get(ATTR_LM_WHERE)
        query_after = bool(call.data.get(ATTR_LM_QUERY_AFTER, False))

        if operation is None:
            LOGGER.error(
                "No `%s` provided for lighting management command.",
                ATTR_LM_OPERATION,
            )
            return {"success": False}
        if where is None:
            LOGGER.error(
                "No `%s` provided for lighting management command.",
                ATTR_LM_WHERE,
            )
            return {"success": False}

        gateway = _resolve_gateway_mac(
            hass,
            call.data.get(ATTR_GATEWAY),
            response_oriented=query_after,
        )
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error(
                "Gateway `%s` not found for lighting management command.",
                gateway,
            )
            return {"success": False}

        gateway_handler = hass.data[DOMAIN][gateway][CONF_ENTITY]
        try:
            message = build_light_management_command(
                operation,
                where,
                value=call.data.get(ATTR_LM_VALUE),
                enabled=call.data.get(ATTR_LM_ENABLED),
                profile=call.data.get(ATTR_LM_PROFILE),
                mode=call.data.get(ATTR_LM_MODE),
                exit_condition=call.data.get(ATTR_LM_EXIT_CONDITION),
                hours=call.data.get(ATTR_LM_HOURS),
                minutes=call.data.get(ATTR_LM_MINUTES),
                seconds=call.data.get(ATTR_LM_SECONDS),
                sensor_address=call.data.get(ATTR_LM_SENSOR_ADDRESS),
                lux=call.data.get(ATTR_LM_LUX),
                error=call.data.get(ATTR_LM_ERROR),
            )
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error(
                "Could not build lighting management command `%s`: %s",
                operation,
                err,
            )
            return {"success": False}

        response = {
            "success": True,
            "gateway": gateway,
            "where": str(where),
            "message": message,
            "operation": str(operation),
        }

        if query_after:
            request = {
                "set_state": "state",
                "set_centralized_lux": "centralized_lux",
                "activate_profile": "state",
                "set_switch_on_value": "switch_on_value",
                "set_max_lux": "max_lux",
                "set_maintained_lux": "maintained_lux",
                "set_auto_switch_on": "auto_switch_on",
                "set_switch_on_delay": "switch_on_delay",
                "set_auto_switch_off": "auto_switch_off",
                "set_switch_off_delay": "switch_off_delay",
                "set_delay_timer": "delay_timer",
                "set_standby_timer": "standby_timer",
                "set_standby_value": "standby_value",
                "set_off_value": "off_value",
                "set_slave_offset": "slave_offset",
            }.get(str(operation))

            if request is not None:
                await gateway_handler.send(message)
                try:
                    readback = build_light_management_request(
                        request,
                        where,
                        sensor_address=call.data.get(ATTR_LM_SENSOR_ADDRESS),
                    )
                except Exception as err:  # pylint: disable=broad-except
                    LOGGER.error(
                        "Could not build lighting management readback `%s`: %s",
                        request,
                        err,
                    )
                    return response

                collected = await _collect_status_requests(gateway_handler, readback)
                response.update(
                    {
                        "success": collected["success"],
                        "acknowledged": collected["acknowledged"],
                        "raw_frames": collected["raw_frames"],
                        "state": gateway_handler.light_management.zone_snapshot(where),
                    }
                )
                return response

        await gateway_handler.send(message)
        return response

    if not hass.services.has_service(DOMAIN, SERVICE_LIGHT_MANAGEMENT_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_LIGHT_MANAGEMENT_COMMAND,
            handle_light_management_command,
            supports_response=SupportsResponse.OPTIONAL,
        )

    async def handle_energy_request(call):
        entity_ids = _normalize_entity_ids(call.data.get(ATTR_ENTITY_ID))
        request = call.data.get(ATTR_ENERGY_REQUEST)

        if request is None:
            LOGGER.error("No `%s` provided for energy request.", ATTR_ENERGY_REQUEST)
            return {"results": []}

        kwargs = {
            "date_value": call.data.get(ATTR_ENERGY_DATE),
            "year": call.data.get(ATTR_ENERGY_YEAR),
            "month": call.data.get(ATTR_ENERGY_MONTH),
        }
        if request == REQUEST_HOURLY_HISTORY and kwargs["date_value"] is None:
            kwargs["date_value"] = date.today().isoformat()
        if request == REQUEST_DAILY_HISTORY and kwargs["month"] is None:
            kwargs["month"] = date.today().month
        if request == REQUEST_MONTHLY_AVERAGE_HOURLY and kwargs["month"] is None:
            kwargs["month"] = date.today().month

        results = []

        if entity_ids is not None:
            for entity in _iter_energy_targets(hass, entity_ids):
                try:
                    message = build_energy_request(request, entity._where, **kwargs)  # noqa: SLF001
                except Exception as err:  # pylint: disable=broad-except
                    LOGGER.error(
                        "Could not build energy request `%s` for `%s`: %s",
                        request,
                        entity.entity_id,
                        err,
                    )
                    continue

                collected = await entity._gateway_handler.send_status_request_collect(  # noqa: SLF001
                    message
                )
                result = build_energy_response(request, collected["raw_frames"])
                result.update(
                    {
                        "entity_id": entity.entity_id,
                        "gateway": entity._gateway_handler.mac,  # noqa: SLF001
                        "where": entity._where,  # noqa: SLF001
                        "success": collected["success"],
                        "acknowledged": collected["acknowledged"],
                    }
                )
                results.append(result)

            return {"results": results}

        where = call.data.get(ATTR_ENERGY_WHERE)
        if where is None:
            LOGGER.error(
                "No `%s` provided for energy request without entity_id.",
                ATTR_ENERGY_WHERE,
            )
            return {"results": []}

        gateway = _resolve_gateway_mac(
            hass,
            call.data.get(ATTR_GATEWAY),
            response_oriented=True,
        )
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for energy request.", gateway)
            return {"results": []}

        try:
            message = build_energy_request(request, str(where), **kwargs)
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build energy request `%s`: %s", request, err)
            return {"results": []}

        collected = await hass.data[DOMAIN][gateway][CONF_ENTITY].send_status_request_collect(
            message
        )
        result = build_energy_response(request, collected["raw_frames"])
        result.update(
            {
                "gateway": gateway,
                "where": str(where),
                "success": collected["success"],
                "acknowledged": collected["acknowledged"],
            }
        )
        return {"results": [result]}

    if not hass.services.has_service(DOMAIN, SERVICE_ENERGY_REQUEST):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ENERGY_REQUEST,
            handle_energy_request,
            supports_response=SupportsResponse.ONLY,
        )

    async def handle_thermo_zone_command(call):
        entity_ids = _normalize_entity_ids(call.data.get(ATTR_ENTITY_ID))
        operation = call.data.get(ATTR_OPERATION)
        mode_family = call.data.get(ATTR_MODE_FAMILY)
        temperature = call.data.get(ATTR_TEMPERATURE)

        if operation is None:
            LOGGER.error("No `%s` provided for thermo zone command.", ATTR_OPERATION)
            return False

        if entity_ids is not None:
            for entity in _iter_thermo_climates(hass, entity_ids):
                await entity.async_zone_command(
                    operation,
                    temperature=temperature,
                    mode_family=mode_family,
                )
            return True

        where = call.data.get(ATTR_WHERE, call.data.get(ATTR_ZONE))
        if where is None:
            LOGGER.error(
                "No `%s` or `%s` provided for thermo zone command.",
                ATTR_WHERE,
                ATTR_ZONE,
            )
            return False

        gateway = _resolve_gateway_mac(hass, call.data.get(ATTR_GATEWAY))
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for thermo zone command.", gateway)
            return False

        try:
            message = build_zone_command(
                str(where),
                str(operation),
                temperature=temperature,
                mode_family=mode_family,
            )
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build thermo zone command: %s", err)
            return False

        await hass.data[DOMAIN][gateway][CONF_ENTITY].send(message)
        return True

    if not hass.services.has_service(DOMAIN, SERVICE_THERMO_ZONE_COMMAND):
        hass.services.async_register(
            DOMAIN, SERVICE_THERMO_ZONE_COMMAND, handle_thermo_zone_command
        )

    async def handle_thermo_central_command(call):
        entity_ids = _normalize_entity_ids(call.data.get(ATTR_ENTITY_ID))
        operation = call.data.get(ATTR_OPERATION)

        if operation is None:
            LOGGER.error("No `%s` provided for thermo central command.", ATTR_OPERATION)
            return False

        kwargs = {
            "temperature": call.data.get(ATTR_TEMPERATURE),
            "mode_family": call.data.get(ATTR_MODE_FAMILY),
            "program": call.data.get(ATTR_PROGRAM),
            "scenario": call.data.get(ATTR_SCENARIO),
            "days": call.data.get(ATTR_DAYS),
            "date_value": call.data.get(ATTR_DATE),
            "time_value": call.data.get(ATTR_TIME),
        }

        if entity_ids is not None:
            for entity in _iter_thermo_climates(hass, entity_ids):
                await entity.async_central_command(operation, **kwargs)
            return True

        gateway = _resolve_gateway_mac(hass, call.data.get(ATTR_GATEWAY))
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for thermo central command.", gateway)
            return False

        try:
            message = build_central_command(str(operation), **kwargs)
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build thermo central command: %s", err)
            return False

        await hass.data[DOMAIN][gateway][CONF_ENTITY].send(message)
        return True

    if not hass.services.has_service(DOMAIN, SERVICE_THERMO_CENTRAL_COMMAND):
        hass.services.async_register(
            DOMAIN, SERVICE_THERMO_CENTRAL_COMMAND, handle_thermo_central_command
        )

    async def handle_thermo_request(call):
        entity_ids = _normalize_entity_ids(call.data.get(ATTR_ENTITY_ID))
        request = call.data.get(ATTR_REQUEST)
        wait_for_completion = bool(call.data.get("wait_for_completion", False))

        if request is None:
            LOGGER.error("No `%s` provided for thermo request.", ATTR_REQUEST)
            return False

        if entity_ids is not None:
            entity_kwargs = {"wait_for_completion": wait_for_completion}
            request_where = call.data.get(ATTR_WHERE, call.data.get(ATTR_ZONE))
            if request_where is not None:
                entity_kwargs["where"] = request_where
            for entity in _iter_thermo_climates(hass, entity_ids):
                await entity.async_request_thermo(request, **entity_kwargs)
            return True

        where = call.data.get(ATTR_WHERE, call.data.get(ATTR_ZONE))
        gateway = _resolve_gateway_mac(
            hass,
            call.data.get(ATTR_GATEWAY),
            response_oriented=True,
        )
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for thermo request.", gateway)
            return False

        try:
            message = build_request(
                str(request),
                where=None if where is None else str(where),
                actuator=call.data.get("actuator"),
            )
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build thermo request: %s", err)
            return False

        return await hass.data[DOMAIN][gateway][CONF_ENTITY].send_status_request(
            message,
            wait_for_completion=wait_for_completion,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_THERMO_REQUEST):
        hass.services.async_register(
            DOMAIN, SERVICE_THERMO_REQUEST, handle_thermo_request
        )

    async def handle_thermo_split_set(call):
        entity_ids = _normalize_entity_ids(call.data.get(ATTR_ENTITY_ID))
        where = call.data.get(ATTR_WHERE, call.data.get(ATTR_ZONE))
        kwargs = {
            "mode": call.data.get(ATTR_OPERATION),
            "temperature": call.data.get(ATTR_TEMPERATURE),
            "fan_mode": call.data.get(ATTR_FAN_MODE),
            "swing_mode": call.data.get(ATTR_SWING_MODE),
        }

        if entity_ids is not None:
            for entity in _iter_thermo_climates(hass, entity_ids):
                await entity._gateway_handler.send(  # noqa: SLF001
                    build_split_set_command(entity._where, **kwargs)  # noqa: SLF001
                )
            return True

        if where is None:
            LOGGER.error(
                "No `%s` or `%s` provided for thermo split command.",
                ATTR_WHERE,
                ATTR_ZONE,
            )
            return False

        gateway = _resolve_gateway_mac(hass, call.data.get(ATTR_GATEWAY))
        if gateway not in hass.data[DOMAIN]:
            LOGGER.error("Gateway `%s` not found for thermo split command.", gateway)
            return False

        try:
            message = build_split_set_command(str(where), **kwargs)
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Could not build thermo split command: %s", err)
            return False

        await hass.data[DOMAIN][gateway][CONF_ENTITY].send(message)
        return True

    if not hass.services.has_service(DOMAIN, SERVICE_THERMO_SPLIT_SET):
        hass.services.async_register(
            DOMAIN, SERVICE_THERMO_SPLIT_SET, handle_thermo_split_set
        )

    return True


async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    LOGGER.info("Unloading MyHome entry.")

    for platform in hass.data[DOMAIN][entry.data[CONF_MAC]][CONF_PLATFORMS].keys():
        await hass.config_entries.async_forward_entry_unload(entry, platform)

    gateway_handler = hass.data[DOMAIN][entry.data[CONF_MAC]].pop(CONF_ENTITY)
    del hass.data[DOMAIN][entry.data[CONF_MAC]]

    if len(hass.data[DOMAIN]) == 0:
        if hass.services.has_service(DOMAIN, "sync_time"):
            hass.services.async_remove(DOMAIN, "sync_time")
        if hass.services.has_service(DOMAIN, "send_message"):
            hass.services.async_remove(DOMAIN, "send_message")
        if hass.services.has_service(DOMAIN, SERVICE_GATEWAY_REQUEST):
            hass.services.async_remove(DOMAIN, SERVICE_GATEWAY_REQUEST)
        if hass.services.has_service(DOMAIN, SERVICE_GATEWAY_COMMAND):
            hass.services.async_remove(DOMAIN, SERVICE_GATEWAY_COMMAND)
        if hass.services.has_service(DOMAIN, SERVICE_SCENARIO_COMMAND):
            hass.services.async_remove(DOMAIN, SERVICE_SCENARIO_COMMAND)
        if hass.services.has_service(DOMAIN, SERVICE_CEN_COMMAND):
            hass.services.async_remove(DOMAIN, SERVICE_CEN_COMMAND)
        if hass.services.has_service(DOMAIN, SERVICE_CENPLUS_COMMAND):
            hass.services.async_remove(DOMAIN, SERVICE_CENPLUS_COMMAND)
        if hass.services.has_service(DOMAIN, SERVICE_ALARM_REQUEST):
            hass.services.async_remove(DOMAIN, SERVICE_ALARM_REQUEST)
        if hass.services.has_service(DOMAIN, SERVICE_AUX_COMMAND):
            hass.services.async_remove(DOMAIN, SERVICE_AUX_COMMAND)
        if hass.services.has_service(DOMAIN, SERVICE_AUDIO_ZONE_COMMAND):
            hass.services.async_remove(DOMAIN, SERVICE_AUDIO_ZONE_COMMAND)
        if hass.services.has_service(DOMAIN, SERVICE_AUDIO_GENERAL_COMMAND):
            hass.services.async_remove(DOMAIN, SERVICE_AUDIO_GENERAL_COMMAND)
        if hass.services.has_service(DOMAIN, SERVICE_AUDIO_SOURCE_COMMAND):
            hass.services.async_remove(DOMAIN, SERVICE_AUDIO_SOURCE_COMMAND)
        if hass.services.has_service(DOMAIN, SERVICE_AUDIO_RADIO_COMMAND):
            hass.services.async_remove(DOMAIN, SERVICE_AUDIO_RADIO_COMMAND)
        if hass.services.has_service(DOMAIN, SERVICE_SCENE_PROGRAMMER_COMMAND):
            hass.services.async_remove(DOMAIN, SERVICE_SCENE_PROGRAMMER_COMMAND)
        if hass.services.has_service(DOMAIN, SERVICE_VIDEO_COMMAND):
            hass.services.async_remove(DOMAIN, SERVICE_VIDEO_COMMAND)
        if hass.services.has_service(DOMAIN, SERVICE_LIGHT_MANAGEMENT_REQUEST):
            hass.services.async_remove(DOMAIN, SERVICE_LIGHT_MANAGEMENT_REQUEST)
        if hass.services.has_service(DOMAIN, SERVICE_LIGHT_MANAGEMENT_COMMAND):
            hass.services.async_remove(DOMAIN, SERVICE_LIGHT_MANAGEMENT_COMMAND)
        if hass.services.has_service(DOMAIN, SERVICE_ENERGY_REQUEST):
            hass.services.async_remove(DOMAIN, SERVICE_ENERGY_REQUEST)
        if hass.services.has_service(DOMAIN, SERVICE_THERMO_ZONE_COMMAND):
            hass.services.async_remove(DOMAIN, SERVICE_THERMO_ZONE_COMMAND)
        if hass.services.has_service(DOMAIN, SERVICE_THERMO_CENTRAL_COMMAND):
            hass.services.async_remove(DOMAIN, SERVICE_THERMO_CENTRAL_COMMAND)
        if hass.services.has_service(DOMAIN, SERVICE_THERMO_REQUEST):
            hass.services.async_remove(DOMAIN, SERVICE_THERMO_REQUEST)
        if hass.services.has_service(DOMAIN, SERVICE_THERMO_SPLIT_SET):
            hass.services.async_remove(DOMAIN, SERVICE_THERMO_SPLIT_SET)

    return await gateway_handler.close_listener()
