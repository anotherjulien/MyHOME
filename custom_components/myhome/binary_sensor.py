"""Support for MyHome binary sensors (dry contacts and motion sensors)."""
import re
from datetime import datetime, timedelta, timezone
from homeassistant.components.binary_sensor import (
    DOMAIN as PLATFORM,
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.media_player import (
    DOMAIN as MEDIA_PLAYER,
    MediaPlayerState,
)
from homeassistant.components.switch import DOMAIN as SWITCH
from homeassistant.const import (
    CONF_NAME,
    CONF_MAC,
    CONF_ENTITIES,
    EntityCategory,
    STATE_ON,
)
from homeassistant.helpers.restore_state import RestoreEntity

from OWNd.message import (
    OWNDryContactEvent,
    OWNDryContactCommand,
    OWNLightingCommand,
    MESSAGE_TYPE_MOTION,
    MESSAGE_TYPE_PIR_SENSITIVITY,
    MESSAGE_TYPE_MOTION_TIMEOUT,
    OWNLightingEvent,
)

from .const import (
    CONF_PLATFORMS,
    CONF_ENTITY,
    CONF_ENTITY_NAME,
    CONF_OPERATION,
    CONF_WHO,
    CONF_WHERE,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_CLASS,
    CONF_INVERTED,
    DOMAIN,
    LOGGER,
)
from .media_player import ATTR_AREA as AUDIO_AREA_ATTR, ATTR_POINT as AUDIO_POINT_ATTR
from .myhome_device import MyHOMEEntity
from .gateway import MyHOMEGatewayHandler

SCAN_INTERVAL = timedelta(seconds=5)
PIR_SENSITIVITY = ["low", "medium", "high", "very high"]
LOAD_CONTROL_STATUS_RE = re.compile(
    r"^\*#18\*(?P<where>\d+)(?:#0)?\*71\*(?P<disabled>[01])\*(?P<forcing>[01])\*(?P<threshold>[01])\*(?P<protection>[01])\*(?P<phase>[01])\*(?P<advanced>[12])##$"
)


async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    gateway_data = hass.data[DOMAIN][config_entry.data[CONF_MAC]]
    _ensure_audio_radio_binary_sensor_configs(gateway_data)

    _binary_sensors = []
    _configured_binary_sensors = gateway_data[CONF_PLATFORMS][PLATFORM]

    for _binary_sensor in _configured_binary_sensors.keys():
        _who = int(_configured_binary_sensors[_binary_sensor][CONF_WHO])
        _device_class = _configured_binary_sensors[_binary_sensor][CONF_DEVICE_CLASS]
        _operation = _configured_binary_sensors[_binary_sensor].get(CONF_OPERATION)
        if _who == 22 and _operation == "radio_in_use":
            _binary_sensor = MyHOMEAudioRadioInUseBinarySensor(
                hass=hass,
                device_id=_binary_sensor,
                who=_configured_binary_sensors[_binary_sensor][CONF_WHO],
                where=_configured_binary_sensors[_binary_sensor][CONF_WHERE],
                name=_configured_binary_sensors[_binary_sensor][CONF_NAME],
                entity_name=_configured_binary_sensors[_binary_sensor][CONF_ENTITY_NAME],
                manufacturer=_configured_binary_sensors[_binary_sensor][CONF_MANUFACTURER],
                model=_configured_binary_sensors[_binary_sensor][CONF_DEVICE_MODEL],
                gateway=gateway_data[CONF_ENTITY],
            )
            _binary_sensors.append(_binary_sensor)
            continue
        if _who == 25:
            _binary_sensor = MyHOMEDryContact(
                hass=hass,
                device_id=_binary_sensor,
                who=_configured_binary_sensors[_binary_sensor][CONF_WHO],
                where=_configured_binary_sensors[_binary_sensor][CONF_WHERE],
                name=_configured_binary_sensors[_binary_sensor][CONF_NAME],
                entity_name=_configured_binary_sensors[_binary_sensor][CONF_ENTITY_NAME],
                inverted=_configured_binary_sensors[_binary_sensor][CONF_INVERTED],
                device_class=_device_class,
                manufacturer=_configured_binary_sensors[_binary_sensor][CONF_MANUFACTURER],
                model=_configured_binary_sensors[_binary_sensor][CONF_DEVICE_MODEL],
                gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
            )
            _binary_sensors.append(_binary_sensor)
        elif _who == 9:
            _binary_sensor = MyHOMEAuxiliary(
                hass=hass,
                device_id=_binary_sensor,
                who=_configured_binary_sensors[_binary_sensor][CONF_WHO],
                where=_configured_binary_sensors[_binary_sensor][CONF_WHERE],
                name=_configured_binary_sensors[_binary_sensor][CONF_NAME],
                entity_name=_configured_binary_sensors[_binary_sensor][CONF_ENTITY_NAME],
                inverted=_configured_binary_sensors[_binary_sensor][CONF_INVERTED],
                device_class=_device_class,
                manufacturer=_configured_binary_sensors[_binary_sensor][CONF_MANUFACTURER],
                model=_configured_binary_sensors[_binary_sensor][CONF_DEVICE_MODEL],
                gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
            )
            _binary_sensors.append(_binary_sensor)
        elif _who == 1 and _device_class == BinarySensorDeviceClass.MOTION:
            _binary_sensor = MyHOMEMotionSensor(
                hass=hass,
                device_id=_binary_sensor,
                who=_configured_binary_sensors[_binary_sensor][CONF_WHO],
                where=_configured_binary_sensors[_binary_sensor][CONF_WHERE],
                name=_configured_binary_sensors[_binary_sensor][CONF_NAME],
                entity_name=_configured_binary_sensors[_binary_sensor][CONF_ENTITY_NAME],
                inverted=_configured_binary_sensors[_binary_sensor][CONF_INVERTED],
                device_class=_device_class,
                manufacturer=_configured_binary_sensors[_binary_sensor][CONF_MANUFACTURER],
                model=_configured_binary_sensors[_binary_sensor][CONF_DEVICE_MODEL],
                gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
            )
            _binary_sensors.append(_binary_sensor)

    _configured_switches = hass.data[DOMAIN][config_entry.data[CONF_MAC]][
        CONF_PLATFORMS
    ].get(SWITCH, {})
    for _switch, _switch_config in _configured_switches.items():
        if _switch_config[CONF_WHO] != "18":
            continue

        _configured_binary_sensors.setdefault(
            _switch,
            {
                CONF_WHO: _switch_config[CONF_WHO],
                CONF_WHERE: _switch_config[CONF_WHERE],
                CONF_NAME: _switch_config[CONF_NAME],
                CONF_MANUFACTURER: _switch_config[CONF_MANUFACTURER],
                CONF_DEVICE_MODEL: _switch_config[CONF_DEVICE_MODEL],
                CONF_ENTITIES: {},
            },
        )

        _binary_sensors.extend(
            [
                MyHOMELoadBinarySensor(
                    hass=hass,
                    device_id=_switch,
                    who=_switch_config[CONF_WHO],
                    where=_switch_config[CONF_WHERE],
                    name=_switch_config[CONF_NAME],
                    manufacturer=_switch_config[CONF_MANUFACTURER],
                    model=_switch_config[CONF_DEVICE_MODEL],
                    gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][
                        CONF_ENTITY
                    ],
                    entity_specific_id="load-enabled",
                    entity_name="Enabled",
                    value_getter=lambda disabled, threshold, protection, phase: not disabled,
                    icon_on="mdi:power-plug",
                    icon_off="mdi:power-plug-off-outline",
                ),
                MyHOMELoadBinarySensor(
                    hass=hass,
                    device_id=_switch,
                    who=_switch_config[CONF_WHO],
                    where=_switch_config[CONF_WHERE],
                    name=_switch_config[CONF_NAME],
                    manufacturer=_switch_config[CONF_MANUFACTURER],
                    model=_switch_config[CONF_DEVICE_MODEL],
                    gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][
                        CONF_ENTITY
                    ],
                    entity_specific_id="load-below-threshold",
                    entity_name="Below threshold",
                    value_getter=lambda disabled, threshold, protection, phase: threshold,
                    icon_on="mdi:gauge-low",
                    icon_off="mdi:gauge",
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
                MyHOMELoadBinarySensor(
                    hass=hass,
                    device_id=_switch,
                    who=_switch_config[CONF_WHO],
                    where=_switch_config[CONF_WHERE],
                    name=_switch_config[CONF_NAME],
                    manufacturer=_switch_config[CONF_MANUFACTURER],
                    model=_switch_config[CONF_DEVICE_MODEL],
                    gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][
                        CONF_ENTITY
                    ],
                    entity_specific_id="load-protection",
                    entity_name="Protection",
                    value_getter=lambda disabled, threshold, protection, phase: protection,
                    icon_on="mdi:shield-alert-outline",
                    icon_off="mdi:shield-check-outline",
                    device_class=BinarySensorDeviceClass.PROBLEM,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
                MyHOMELoadBinarySensor(
                    hass=hass,
                    device_id=_switch,
                    who=_switch_config[CONF_WHO],
                    where=_switch_config[CONF_WHERE],
                    name=_switch_config[CONF_NAME],
                    manufacturer=_switch_config[CONF_MANUFACTURER],
                    model=_switch_config[CONF_DEVICE_MODEL],
                    gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][
                        CONF_ENTITY
                    ],
                    entity_specific_id="load-local-phase-disabled",
                    entity_name="Local phase disabled",
                    value_getter=lambda disabled, threshold, protection, phase: phase,
                    icon_on="mdi:power-plug-off-outline",
                    icon_off="mdi:power-plug-outline",
                    device_class=BinarySensorDeviceClass.PROBLEM,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
            ]
        )

    async_add_entities(_binary_sensors)


def _ensure_audio_radio_binary_sensor_configs(gateway_data: dict) -> None:
    binary_sensor_config = gateway_data.setdefault(CONF_PLATFORMS, {}).setdefault(
        PLATFORM,
        {},
    )
    media_players = gateway_data.get(CONF_PLATFORMS, {}).get(MEDIA_PLAYER, {})
    if not media_players:
        return

    first_media_player = next(iter(media_players.values()))
    binary_sensor_config.setdefault(
        "audio-radio-in-use",
        {
            CONF_WHO: "22",
            CONF_WHERE: "1",
            CONF_NAME: "Audio radio",
            CONF_ENTITY_NAME: "In use",
            CONF_OPERATION: "radio_in_use",
            CONF_INVERTED: False,
            CONF_DEVICE_CLASS: BinarySensorDeviceClass.RUNNING,
            CONF_MANUFACTURER: first_media_player.get(
                CONF_MANUFACTURER,
                "BTicino S.p.A.",
            ),
            CONF_DEVICE_MODEL: first_media_player.get(CONF_DEVICE_MODEL),
            CONF_ENTITIES: {},
        },
    )


async def async_unload_entry(hass, config_entry):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    _configured_binary_sensors = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM]

    for _binary_sensor in _configured_binary_sensors.keys():
        del hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM][_binary_sensor]


class MyHOMEDryContact(MyHOMEEntity, BinarySensorEntity):
    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        device_id: str,
        who: str,
        where: str,
        inverted: bool,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
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

        self._inverted = inverted

        self._attr_device_class = device_class
        self._attr_name = entity_name if entity_name else self._attr_device_class.replace("_", " ").capitalize()

        self._attr_unique_id = f"{gateway.mac}-{self._device_id}-{self._attr_device_class}"

        self._attr_is_on = False
        self._attr_extra_state_attributes = {"Sensor": f"({self._where[0]}){self._where[1:]}"}

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][self._platform][self._device_id][CONF_ENTITIES][self._attr_device_class] = self
        await self.async_update()

    async def async_will_remove_from_hass(self):
        """When entity is removed from hass."""
        if self._attr_device_class in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][self._platform][self._device_id][CONF_ENTITIES]:
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][self._platform][self._device_id][CONF_ENTITIES][self._attr_device_class]

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway_handler.send_status_request(OWNDryContactCommand.status(self._where))

    def handle_event(self, message: OWNDryContactEvent):
        """Handle an event message."""
        LOGGER.info(
            "%s %s",
            self._gateway_handler.log_id,
            message.human_readable_log,
        )
        self._attr_is_on = message.is_on != self._inverted
        self.async_schedule_update_ha_state()


class MyHOMEAuxiliary(MyHOMEEntity, BinarySensorEntity):
    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        device_id: str,
        who: str,
        where: str,
        inverted: bool,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
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

        self._inverted = inverted

        self._attr_device_class = device_class
        self._attr_name = entity_name if entity_name else self._attr_device_class.replace("_", " ").capitalize()

        self._attr_unique_id = f"{gateway.mac}-{self._device_id}-{self._attr_device_class}"

        self._attr_is_on = False
        self._attr_extra_state_attributes = {"Auxiliary channel": self._where}

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][self._platform][self._device_id][CONF_ENTITIES][self._attr_device_class] = self
        await self.async_update()

    async def async_will_remove_from_hass(self):
        """When entity is removed from hass."""
        if self._attr_device_class in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][self._platform][self._device_id][CONF_ENTITIES]:
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][self._platform][self._device_id][CONF_ENTITIES][self._attr_device_class]

    async def async_update(self):
        """AUX sensors are read only and cannot be queried, no async_update implementation."""

    def handle_event(self, message: OWNDryContactEvent):
        """Handle an event message."""
        LOGGER.info(
            "%s %s",
            self._gateway_handler.log_id,
            message.human_readable_log,
        )
        self._attr_is_on = message.is_on != self._inverted
        self.async_schedule_update_ha_state()


class MyHOMEMotionSensor(MyHOMEEntity, BinarySensorEntity, RestoreEntity):
    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        device_id: str,
        who: str,
        where: str,
        inverted: bool,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
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

        self._inverted = inverted
        self._attr_force_update = False
        self._last_updated = None
        self._timeout = timedelta(seconds=315)

        self._attr_device_class = device_class
        self._attr_name = entity_name if entity_name else self._attr_device_class.replace("_", " ").capitalize()

        self._attr_unique_id = f"{gateway.mac}-{self._device_id}-{self._attr_device_class}"
        self._attr_should_poll = True
        self._attr_is_on = None
        self._attr_extra_state_attributes = {
            "A": where[: len(where) // 2],
            "PL": where[len(where) // 2 :],
            "Timeout": self._timeout.total_seconds(),
            "Sensitivity": PIR_SENSITIVITY[1],
        }

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][self._platform][self._device_id][CONF_ENTITIES][self._attr_device_class] = self
        await self._gateway_handler.send_status_request(OWNLightingCommand.get_pir_sensitivity(self._where))
        await self._gateway_handler.send_status_request(OWNLightingCommand.get_motion_timeout(self._where))
        state = await self.async_get_last_state()
        if state:
            self._attr_is_on = state.state == STATE_ON
            self._last_updated = state.last_updated
        await self.async_update()

    async def async_will_remove_from_hass(self):
        """When entity is removed from hass."""
        if self._attr_device_class in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][self._platform][self._device_id][CONF_ENTITIES]:
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][self._platform][self._device_id][CONF_ENTITIES][self._attr_device_class]

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        if self._attr_is_on and self._last_updated and self._last_updated + self._timeout < datetime.now(timezone.utc):
            self._attr_is_on = False
            self._last_updated = datetime.now(timezone.utc)
            self.async_schedule_update_ha_state()

    def handle_event(self, message: OWNLightingEvent):
        """Handle an event message."""
        if message.message_type not in [
            MESSAGE_TYPE_MOTION,
            MESSAGE_TYPE_MOTION_TIMEOUT,
            MESSAGE_TYPE_PIR_SENSITIVITY,
        ]:
            return True

        LOGGER.info(
            "%s %s",
            self._gateway_handler.log_id,
            message.human_readable_log,
        )
        if message.message_type == MESSAGE_TYPE_MOTION and message.motion:
            self._attr_is_on = message.motion != self._inverted
        elif message.message_type == MESSAGE_TYPE_MOTION_TIMEOUT:
            self._timeout = message.motion_timeout + timedelta(seconds=15)
            self._attr_extra_state_attributes["Timeout"] = self._timeout.total_seconds()
        elif message.message_type == MESSAGE_TYPE_PIR_SENSITIVITY:
            self._attr_extra_state_attributes["Sensitivity"] = PIR_SENSITIVITY[message.pir_sensitivity]
        self._last_updated = datetime.now(timezone.utc)
        self._attr_force_update = True
        self.async_write_ha_state()
        self._attr_force_update = False


class MyHOMEAudioRadioInUseBinarySensor(MyHOMEEntity, BinarySensorEntity):
    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        device_id: str,
        who: str,
        where: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model or "MyHOME Audio Radio",
            gateway=gateway,
        )
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_name = entity_name or "In use"
        self._attr_unique_id = f"{gateway.mac}-{self._device_id}"
        self._attr_is_on = False
        self._attr_extra_state_attributes = {
            "source_id": 1,
            "active_zones": [],
            "zone_count": 0,
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

    def _compute_from_media_players(self) -> tuple[bool, list[str]]:
        active_zones: list[str] = []
        media_player_configs = self._hass.data[DOMAIN][self._gateway_handler.mac][
            CONF_PLATFORMS
        ].get(MEDIA_PLAYER, {})

        for device_config in media_player_configs.values():
            entity = device_config.get(CONF_ENTITIES, {}).get(MEDIA_PLAYER)
            if entity is None:
                continue
            entity_state = getattr(entity, "state", None)
            entity_source = getattr(entity, "source", None)
            if entity_state in {MediaPlayerState.OFF, None}:
                continue
            if str(entity_source) != "Radio":
                continue

            area = device_config.get(AUDIO_AREA_ATTR)
            point = device_config.get(AUDIO_POINT_ATTR)
            if area is None or point is None:
                continue
            active_zones.append(f"{int(area)}#{int(point)}")

        if active_zones:
            return True, active_zones

        for zone in self._gateway_handler.audio.zones.values():
            if zone.is_on and int(zone.source_id or 0) == 1:
                active_zones.append(f"{zone.area}#{zone.point}")
        return bool(active_zones), active_zones

    def _apply_state(self) -> None:
        is_on, active_zones = self._compute_from_media_players()
        self._attr_is_on = is_on
        self._attr_extra_state_attributes["active_zones"] = active_zones
        self._attr_extra_state_attributes["zone_count"] = len(active_zones)

    async def async_update(self):
        media_player_configs = self._hass.data[DOMAIN][self._gateway_handler.mac][
            CONF_PLATFORMS
        ].get(MEDIA_PLAYER, {})
        for device_config in media_player_configs.values():
            entity = device_config.get(CONF_ENTITIES, {}).get(MEDIA_PLAYER)
            if entity is not None:
                await entity.async_update()
        self._apply_state()
        self.async_schedule_update_ha_state()

    def _handle_audio_feedback_event(self, event) -> None:
        data = dict(event.data)
        if data.get("gateway_mac") != self._gateway_handler.mac:
            return
        self._apply_state()
        self.async_write_ha_state()


class MyHOMELoadBinarySensor(MyHOMEEntity, BinarySensorEntity):
    def __init__(
        self,
        hass,
        name: str,
        device_id: str,
        who: str,
        where: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
        entity_specific_id: str,
        entity_name: str,
        value_getter,
        icon_on: str,
        icon_off: str,
        device_class: str | None = None,
        entity_category: str | None = None,
    ):
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

        self._entity_specific_id = entity_specific_id
        self._value_getter = value_getter
        self._full_where = f"{self._where}#0" if self._where.startswith("7") else self._where
        self._icon_on = icon_on
        self._icon_off = icon_off
        self._attr_name = entity_name
        self._attr_unique_id = f"{gateway.mac}-{self._device_id}-{self._entity_specific_id}"
        self._attr_device_class = device_class
        self._attr_is_on = None
        self._attr_icon = self._icon_off
        self._attr_extra_state_attributes = {
            "load": self._where[1:] if self._where.startswith("7") else self._where,
        }
        if entity_category is not None:
            self._attr_entity_category = entity_category

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

    async def async_update(self):
        switch_config = self._hass.data[DOMAIN][self._gateway_handler.mac][
            CONF_PLATFORMS
        ].get(SWITCH, {}).get(self._device_id, {})
        switch_entity = switch_config.get(CONF_ENTITIES, {}).get(SWITCH)
        if switch_entity is None:
            return
        await switch_entity.async_update()

        self.apply_switch_attributes(switch_entity.extra_state_attributes or {})

    def apply_switch_attributes(self, switch_attrs):
        attr_map = {
            "load-enabled": "enabled",
            "load-below-threshold": "below_threshold",
            "load-protection": "protection",
            "load-local-phase-disabled": "local_phase_disabled",
        }
        value = switch_attrs.get(attr_map[self._entity_specific_id])
        if value is None:
            return
        self._attr_is_on = value
        self._attr_icon = self._icon_on if self._attr_is_on else self._icon_off
        self.async_schedule_update_ha_state()

    def handle_event(self, message):
        match = LOAD_CONTROL_STATUS_RE.match(str(message))
        if match is None:
            return True

        disabled = match.group("disabled") == "1"
        threshold = match.group("threshold") == "1"
        protection = match.group("protection") == "1"
        phase = match.group("phase") == "1"
        self._attr_is_on = self._value_getter(disabled, threshold, protection, phase)
        self._attr_icon = self._icon_on if self._attr_is_on else self._icon_off
        self.async_schedule_update_ha_state()
        return True
