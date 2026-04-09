"""Support for MyHome selects."""

from __future__ import annotations

from homeassistant.components.select import (
    DOMAIN as PLATFORM,
    SelectEntity,
)
from homeassistant.const import (
    CONF_ENTITIES,
    CONF_MAC,
    EntityCategory,
)
from homeassistant.core import callback

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
    EXIT_CONDITION_OPTIONS,
    MODE_OPTIONS,
    build_light_management_command,
    build_light_management_request,
    exit_condition_code_from_option,
    exit_condition_option_from_code,
    mode_code_from_option,
    mode_option_from_code,
)
from .myhome_device import MyHOMEEntity


async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    selects = []
    configured_selects = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][
        PLATFORM
    ]

    for select_id, select_config in configured_selects.items():
        if select_config[CONF_WHO] != "24":
            continue
        selects.append(
            MyHOMELightManagementSelect(
                hass=hass,
                device_id=select_id,
                who=select_config[CONF_WHO],
                where=select_config[CONF_WHERE],
                name=select_config["name"],
                entity_name=select_config.get(CONF_ENTITY_NAME),
                operation=select_config.get(CONF_OPERATION),
                manufacturer=select_config[CONF_MANUFACTURER],
                model=select_config[CONF_DEVICE_MODEL],
                gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
            )
        )

    async_add_entities(selects)


async def async_unload_entry(hass, config_entry):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    configured_selects = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][
        PLATFORM
    ]

    for select_id in list(configured_selects):
        del configured_selects[select_id]

    return True


class MyHOMELightManagementSelect(MyHOMEEntity, SelectEntity):
    """Represent WHO=24 mode/exit_condition as native selects."""

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
        gateway,
    ):
        operation = str(operation or "mode")
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
        self._attr_name = entity_name or operation.replace("_", " ").title()
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_icon = (
            "mdi:state-machine"
            if self._operation == "mode"
            else "mdi:exit-run"
        )
        self._attr_options = (
            list(MODE_OPTIONS)
            if self._operation == "mode"
            else list(EXIT_CONDITION_OPTIONS)
        )
        self._attr_current_option = None
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

        if self._operation == "mode":
            self._attr_current_option = mode_option_from_code(snapshot.get("mode"))
        else:
            self._attr_current_option = exit_condition_option_from_code(
                snapshot.get("exit_condition")
            )
        self._attr_extra_state_attributes.update(
            {
                "last_update": snapshot.get("last_update"),
                "state_time": snapshot.get("state_time"),
                "mode": snapshot.get("mode_name"),
                "exit_condition": snapshot.get("exit_condition_name"),
            }
        )

    async def async_update(self):
        await self._gateway_handler.send_status_request_collect(
            build_light_management_request("state", self._where)
        )
        self._apply_snapshot(
            self._gateway_handler.light_management.zone_snapshot(self._where)
        )
        self.async_schedule_update_ha_state()

    async def async_select_option(self, option: str) -> None:
        snapshot = self._gateway_handler.light_management.zone_snapshot(self._where)
        if not snapshot or snapshot.get("mode") is None or snapshot.get("exit_condition") is None:
            await self.async_update()
            snapshot = self._gateway_handler.light_management.zone_snapshot(self._where)

        if not snapshot:
            raise ValueError("Lighting management state unavailable.")

        mode = int(snapshot.get("mode", 0))
        exit_condition = int(snapshot.get("exit_condition", 4))
        hours = int(snapshot.get("state_hours") or 0)
        minutes = int(snapshot.get("state_minutes") or 0)
        seconds = int(snapshot.get("state_seconds") or 0)

        if self._operation == "mode":
            mode = mode_code_from_option(option)
        else:
            exit_condition = exit_condition_code_from_option(option)

        await self._gateway_handler.send(
            build_light_management_command(
                "set_state",
                self._where,
                mode=mode,
                exit_condition=exit_condition,
                hours=hours,
                minutes=minutes,
                seconds=seconds,
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
        if data.get("kind") != "state":
            return
        self._apply_snapshot(
            self._gateway_handler.light_management.zone_snapshot(self._where)
        )
        self.async_write_ha_state()
