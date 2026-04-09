"""Native MyHOME burglar alarm control panel."""

from __future__ import annotations

from homeassistant.components.alarm_control_panel import (
    DOMAIN as PLATFORM,
    AlarmControlPanelEntity,
)
from homeassistant.components.alarm_control_panel.const import (
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.restore_state import RestoreEntity

from .alarm import (
    ATTR_ARM_CHANNEL,
    ATTR_CONTROL_CHANNEL,
    ATTR_DISARM_CHANNEL,
    ATTR_STATE_CODE,
    ATTR_STATE_NAME,
    build_aux_command,
    map_alarm_state,
)
from .const import (
    CONF_DEVICE_MODEL,
    CONF_ENTITIES,
    CONF_ENTITY,
    CONF_ENTITY_NAME,
    CONF_MANUFACTURER,
    CONF_PLATFORMS,
    DOMAIN,
)


async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    gateway_handler = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY]
    configured_entities = hass.data[DOMAIN][config_entry.data[CONF_MAC]][
        CONF_PLATFORMS
    ][PLATFORM]

    async_add_entities(
        [
            MyHOMEAlarmPanel(
                hass=hass,
                gateway=gateway_handler,
                device_id=device_id,
                name=device_config[CONF_NAME],
                entity_name=device_config.get(CONF_ENTITY_NAME),
                manufacturer=device_config[CONF_MANUFACTURER],
                model=device_config.get(CONF_DEVICE_MODEL),
                control_channel=device_config.get(ATTR_CONTROL_CHANNEL),
                arm_channel=device_config.get(ATTR_ARM_CHANNEL),
                disarm_channel=device_config.get(ATTR_DISARM_CHANNEL),
            )
            for device_id, device_config in configured_entities.items()
        ]
    )


async def async_unload_entry(hass, config_entry):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    configured_entities = hass.data[DOMAIN][config_entry.data[CONF_MAC]][
        CONF_PLATFORMS
    ][PLATFORM]
    for entity_id in list(configured_entities):
        del configured_entities[entity_id]

    return True


class MyHOMEAlarmPanel(AlarmControlPanelEntity, RestoreEntity):
    """Represent the MyHOME burglar alarm as a native HA alarm panel."""

    def __init__(
        self,
        hass,
        gateway,
        device_id: str,
        name: str,
        entity_name: str | None,
        manufacturer: str,
        model: str | None,
        control_channel: int | str | None,
        arm_channel: int | str | None,
        disarm_channel: int | str | None,
    ) -> None:
        self.hass = hass
        self._hass = hass
        self._gateway_handler = gateway
        self._device_id = device_id
        self._platform = PLATFORM
        self._control_channel = (
            None if control_channel is None else int(control_channel)
        )
        self._arm_channel = (
            int(arm_channel)
            if arm_channel is not None
            else self._control_channel
        )
        self._disarm_channel = (
            int(disarm_channel)
            if disarm_channel is not None
            else self._control_channel
        )

        self._attr_has_entity_name = True
        self._attr_name = entity_name
        self._attr_unique_id = f"{gateway.mac}-{device_id}"
        self._attr_should_poll = False
        self._attr_code_arm_required = False
        self._attr_code_format = None
        self._attr_alarm_state = AlarmControlPanelState.DISARMED
        self._attr_icon = "mdi:shield-home"
        self._attr_supported_features = (
            AlarmControlPanelEntityFeature.ARM_AWAY
            if self._arm_channel is not None
            else AlarmControlPanelEntityFeature(0)
        )
        self._engaged = False
        self._attr_extra_state_attributes = {
            "control_channel": self._control_channel,
            "arm_channel": self._arm_channel,
            "disarm_channel": self._disarm_channel,
            "last_state_code": None,
            "last_state_name": None,
            "last_zone": None,
            "last_sensor": None,
            "general": None,
            "engaged": self._engaged,
            "last_message": None,
        }
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{gateway.mac}-{device_id}")},
            "name": name,
            "manufacturer": manufacturer or "BTicino S.p.A.",
            "model": model or "MyHOME Burglar Alarm",
            "via_device": (DOMAIN, self._gateway_handler.unique_id),
        }

    async def async_added_to_hass(self) -> None:
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._platform] = self
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._attr_alarm_state = AlarmControlPanelState(last_state.state)
            except ValueError:
                self._attr_alarm_state = AlarmControlPanelState.DISARMED

        self.async_on_remove(
            self._hass.bus.async_listen(
                "myhome_alarm_event",
                self._handle_alarm_event,
            )
        )

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
    def _handle_alarm_event(self, event) -> None:
        data = dict(event.data)
        if data.get("gateway_mac") != self._gateway_handler.mac:
            return

        state_code = data.get(ATTR_STATE_CODE)
        self._attr_alarm_state, self._engaged = map_alarm_state(
            state_code,
            self._attr_alarm_state,
            self._engaged,
        )
        self._attr_changed_by = data.get(ATTR_STATE_NAME)
        self._attr_extra_state_attributes.update(
            {
                "last_state_code": state_code,
                "last_state_name": data.get(ATTR_STATE_NAME),
                "last_zone": data.get("zone"),
                "last_sensor": data.get("sensor"),
                "general": data.get("general"),
                "engaged": self._engaged,
                "last_message": data.get("message"),
            }
        )
        self.async_write_ha_state()

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        del code
        if self._arm_channel is None:
            return

        await self._gateway_handler.send(build_aux_command(self._arm_channel, "on"))
        self._engaged = True
        self._attr_alarm_state = AlarmControlPanelState.ARMING
        self._attr_changed_by = f"aux:{self._arm_channel}"
        self.async_write_ha_state()

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        del code
        if self._disarm_channel is None:
            return

        await self._gateway_handler.send(
            build_aux_command(self._disarm_channel, "off")
        )
        self._engaged = False
        self._attr_alarm_state = AlarmControlPanelState.DISARMING
        self._attr_changed_by = f"aux:{self._disarm_channel}"
        self.async_write_ha_state()
