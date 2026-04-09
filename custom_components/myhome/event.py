"""Native MyHOME bus event entities."""

from __future__ import annotations

from homeassistant.components.event import (
    DOMAIN as PLATFORM,
    EventDeviceClass,
    EventEntity,
)
from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.core import callback

from .const import (
    CONF_ENTITIES,
    CONF_ENTITY,
    CONF_LONG_PRESS,
    CONF_LONG_RELEASE,
    CONF_PLATFORMS,
    CONF_SHORT_PRESS,
    CONF_SHORT_RELEASE,
    DOMAIN,
)
from .light_management import (
    REQUEST_ALL,
    REQUEST_AUTO_SWITCH_OFF,
    REQUEST_AUTO_SWITCH_ON,
    REQUEST_CENTRALIZED_LUX,
    REQUEST_DELAY_TIMER,
    REQUEST_MAINTAINED_LUX,
    REQUEST_MAX_LUX,
    REQUEST_OFF_VALUE,
    REQUEST_SLAVE_OFFSET,
    REQUEST_STANDBY_TIMER,
    REQUEST_STANDBY_VALUE,
    REQUEST_STATE,
    REQUEST_SWITCH_OFF_DELAY,
    REQUEST_SWITCH_ON_DELAY,
    REQUEST_SWITCH_ON_VALUE,
)
from .gateway_info import REQUEST_ORDER as GATEWAY_REQUEST_ORDER

BUS_EVENT_TYPE = "bus_event_type"
EVENT_TYPES = "event_types"
DEVICE_CLASS = "device_class"
CLASSIFIER = "classifier"


EVENT_ENTITY_DEFINITIONS = {
    "gateway_cen_events": {
        CONF_NAME: "CEN",
        BUS_EVENT_TYPE: "myhome_cen_event",
        EVENT_TYPES: [
            CONF_SHORT_PRESS,
            CONF_SHORT_RELEASE,
            CONF_LONG_PRESS,
            CONF_LONG_RELEASE,
        ],
        DEVICE_CLASS: EventDeviceClass.BUTTON,
        CLASSIFIER: "cen",
    },
    "gateway_cenplus_events": {
        CONF_NAME: "CEN Plus",
        BUS_EVENT_TYPE: "myhome_cenplus_event",
        EVENT_TYPES: [
            CONF_SHORT_PRESS,
            CONF_LONG_PRESS,
            CONF_LONG_RELEASE,
        ],
        DEVICE_CLASS: EventDeviceClass.BUTTON,
        CLASSIFIER: "cenplus",
    },
    "gateway_scenario_events": {
        CONF_NAME: "Scenario",
        BUS_EVENT_TYPE: "myhome_scenario_event",
        EVENT_TYPES: ["triggered"],
        DEVICE_CLASS: EventDeviceClass.BUTTON,
        CLASSIFIER: "scenario",
    },
    "gateway_scene_events": {
        CONF_NAME: "Scene",
        BUS_EVENT_TYPE: "myhome_scene_event",
        EVENT_TYPES: ["enabled", "on", "off", "update"],
        DEVICE_CLASS: EventDeviceClass.BUTTON,
        CLASSIFIER: "scene",
    },
    "gateway_alarm_events": {
        CONF_NAME: "Alarm",
        BUS_EVENT_TYPE: "myhome_alarm_event",
        EVENT_TYPES: ["alarm", "active", "engaged", "update"],
        CLASSIFIER: "alarm",
    },
    "gateway_light_management_events": {
        CONF_NAME: "Light management",
        BUS_EVENT_TYPE: "myhome_light_management_event",
        EVENT_TYPES: [
            REQUEST_SWITCH_ON_VALUE,
            REQUEST_MAX_LUX,
            REQUEST_MAINTAINED_LUX,
            REQUEST_AUTO_SWITCH_ON,
            REQUEST_SWITCH_ON_DELAY,
            REQUEST_AUTO_SWITCH_OFF,
            REQUEST_SWITCH_OFF_DELAY,
            REQUEST_DELAY_TIMER,
            REQUEST_STANDBY_TIMER,
            REQUEST_STANDBY_VALUE,
            REQUEST_OFF_VALUE,
            REQUEST_SLAVE_OFFSET,
            REQUEST_STATE,
            REQUEST_CENTRALIZED_LUX,
            REQUEST_ALL,
        ],
        CLASSIFIER: "light_management",
    },
    "gateway_gateway_events": {
        CONF_NAME: "Gateway",
        BUS_EVENT_TYPE: "myhome_gateway_event",
        EVENT_TYPES: [*GATEWAY_REQUEST_ORDER, "update"],
        CLASSIFIER: "gateway",
    },
}


def ensure_event_platform_config(gateway_config: dict) -> None:
    """Inject synthetic event entities into the in-memory gateway config."""
    platform_config = gateway_config.setdefault(CONF_PLATFORMS, {}).setdefault(
        PLATFORM, {}
    )

    for device_id, definition in EVENT_ENTITY_DEFINITIONS.items():
        platform_config.setdefault(
            device_id,
            {
                CONF_NAME: definition[CONF_NAME],
                BUS_EVENT_TYPE: definition[BUS_EVENT_TYPE],
                EVENT_TYPES: list(definition[EVENT_TYPES]),
                DEVICE_CLASS: definition.get(DEVICE_CLASS),
                CLASSIFIER: definition[CLASSIFIER],
                CONF_ENTITIES: {PLATFORM: {}},
            },
        )


async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    configured_entities = hass.data[DOMAIN][config_entry.data[CONF_MAC]][
        CONF_PLATFORMS
    ][PLATFORM]
    gateway_handler = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY]

    async_add_entities(
        [
            MyHOMEGatewayEventEntity(
                hass=hass,
                gateway=gateway_handler,
                device_id=device_id,
                name=device_config[CONF_NAME],
                bus_event_type=device_config[BUS_EVENT_TYPE],
                event_types=device_config[EVENT_TYPES],
                classifier=device_config[CLASSIFIER],
                device_class=device_config.get(DEVICE_CLASS),
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


class MyHOMEGatewayEventEntity(EventEntity):
    """Expose MyHOME gateway bus events as native HA event entities."""

    def __init__(
        self,
        hass,
        gateway,
        device_id: str,
        name: str,
        bus_event_type: str,
        event_types: list[str],
        classifier: str,
        device_class: EventDeviceClass | None = None,
    ) -> None:
        self._hass = hass
        self._gateway_handler = gateway
        self._platform = PLATFORM
        self._device_id = device_id
        self._bus_event_type = bus_event_type
        self._classifier = classifier

        self._attr_unique_id = f"{gateway.mac}-{device_id}"
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_should_poll = False
        self._attr_event_types = event_types
        self._attr_device_class = device_class
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._gateway_handler.unique_id)},
        }

    async def async_added_to_hass(self) -> None:
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._platform] = self
        self.async_on_remove(
            self._hass.bus.async_listen(
                self._bus_event_type,
                self._handle_bus_event,
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
    def _handle_bus_event(self, event) -> None:
        data = dict(event.data)
        if data.get("gateway_mac") != self._gateway_handler.mac:
            return

        event_type, attributes = self._classify_event(data)
        if event_type is None:
            return

        self._trigger_event(event_type, attributes or None)
        self.async_write_ha_state()

    def _classify_event(self, data: dict) -> tuple[str | None, dict]:
        attributes = {k: v for k, v in data.items() if k != "gateway_mac"}

        if self._classifier in {"cen", "cenplus"}:
            event_type = attributes.pop("event", None)
            return event_type, attributes

        if self._classifier == "scenario":
            return "triggered", attributes

        if self._classifier == "scene":
            if attributes.get("is_enabled"):
                return "enabled", attributes
            if attributes.get("is_on") is True:
                return "on", attributes
            if attributes.get("is_on") is False:
                return "off", attributes
            return "update", attributes

        if self._classifier == "alarm":
            if attributes.get("is_alarm"):
                return "alarm", attributes
            if attributes.get("is_active"):
                return "active", attributes
            if attributes.get("is_engaged"):
                return "engaged", attributes
            return "update", attributes

        if self._classifier == "light_management":
            event_type = attributes.get("kind")
            return event_type or REQUEST_ALL, attributes

        if self._classifier == "gateway":
            event_type = attributes.get("kind")
            return event_type or "update", attributes

        return None, attributes
