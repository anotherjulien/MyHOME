"""Support for MyHome binary sensors (dry contacts and motion sensors)."""
from datetime import datetime, timedelta, timezone
import voluptuous as vol

from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA,
    DOMAIN as PLATFORM,
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_DEVICES,
    CONF_ENTITIES,
    STATE_ON,
)
from homeassistant.helpers import config_validation as cv
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
    CONF,
    CONF_GATEWAY,
    CONF_WHO,
    CONF_WHERE,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_CLASS,
    CONF_INVERTED,
    DOMAIN,
    LOGGER,
)
from .myhome_device import MyHOMEEntity
from .gateway import MyHOMEGatewayHandler

MYHOME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WHERE): cv.string,
        vol.Optional(CONF_WHO): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_INVERTED): cv.boolean,
        vol.Optional(CONF_DEVICE_CLASS): vol.In(
            [
                BinarySensorDeviceClass.BATTERY,
                BinarySensorDeviceClass.BATTERY_CHARGING,
                BinarySensorDeviceClass.COLD,
                BinarySensorDeviceClass.CONNECTIVITY,
                BinarySensorDeviceClass.DOOR,
                BinarySensorDeviceClass.GARAGE_DOOR,
                BinarySensorDeviceClass.GAS,
                BinarySensorDeviceClass.HEAT,
                BinarySensorDeviceClass.LIGHT,
                BinarySensorDeviceClass.LOCK,
                BinarySensorDeviceClass.MOISTURE,
                BinarySensorDeviceClass.MOTION,
                BinarySensorDeviceClass.MOVING,
                BinarySensorDeviceClass.OCCUPANCY,
                BinarySensorDeviceClass.OPENING,
                BinarySensorDeviceClass.PLUG,
                BinarySensorDeviceClass.POWER,
                BinarySensorDeviceClass.PRESENCE,
                BinarySensorDeviceClass.PROBLEM,
                BinarySensorDeviceClass.SAFETY,
                BinarySensorDeviceClass.SMOKE,
                BinarySensorDeviceClass.SOUND,
                BinarySensorDeviceClass.VIBRATION,
                BinarySensorDeviceClass.WINDOW,
            ]
        ),
        vol.Optional(CONF_MANUFACTURER): cv.string,
        vol.Optional(CONF_DEVICE_MODEL): cv.string,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_DEVICES): cv.schema_with_slug_keys(MYHOME_SCHEMA)}
)

SCAN_INTERVAL = timedelta(seconds=5)

PIR_SENSITIVITY = ["low", "medium", "high", "very high"]


async def async_setup_platform(
    hass, config, async_add_entities, discovery_info=None
):  # pylint: disable=unused-argument
    if CONF not in hass.data[DOMAIN]:
        return False
    hass.data[DOMAIN][CONF][PLATFORM] = {}
    _configured_binary_sensors = config.get(CONF_DEVICES)

    if _configured_binary_sensors:
        for _, entity_info in _configured_binary_sensors.items():
            who = entity_info[CONF_WHO] if CONF_WHO in entity_info else "25"
            where = entity_info[CONF_WHERE]
            device_id = f"{who}-{where}"
            name = (
                entity_info[CONF_NAME]
                if CONF_NAME in entity_info
                else f"Sensor {where}"
            )
            inverted = (
                entity_info[CONF_INVERTED] if CONF_INVERTED in entity_info else False
            )
            device_class = (
                entity_info[CONF_DEVICE_CLASS]
                if CONF_DEVICE_CLASS in entity_info
                else None
            )
            entities = [device_class] if who == "1" else []
            manufacturer = (
                entity_info[CONF_MANUFACTURER]
                if CONF_MANUFACTURER in entity_info
                else None
            )
            model = (
                entity_info[CONF_DEVICE_MODEL]
                if CONF_DEVICE_MODEL in entity_info
                else None
            )
            hass.data[DOMAIN][CONF][PLATFORM][device_id] = {
                CONF_WHO: who,
                CONF_WHERE: where,
                CONF_ENTITIES: entities,
                CONF_NAME: name,
                CONF_INVERTED: inverted,
                CONF_DEVICE_CLASS: device_class,
                CONF_MANUFACTURER: manufacturer,
                CONF_DEVICE_MODEL: model,
            }


async def async_setup_entry(
    hass, config_entry, async_add_entities
):  # pylint: disable=unused-argument
    if PLATFORM not in hass.data[DOMAIN][CONF]:
        return True

    _binary_sensors = []
    _configured_binary_sensors = hass.data[DOMAIN][CONF][PLATFORM]

    for _binary_sensor in _configured_binary_sensors.keys():
        _who = int(_configured_binary_sensors[_binary_sensor][CONF_WHO])
        _device_class = _configured_binary_sensors[_binary_sensor][CONF_DEVICE_CLASS]
        if _who == 25:
            _binary_sensor = MyHOMEDryContact(
                hass=hass,
                device_id=_binary_sensor,
                who=_configured_binary_sensors[_binary_sensor][CONF_WHO],
                where=_configured_binary_sensors[_binary_sensor][CONF_WHERE],
                name=_configured_binary_sensors[_binary_sensor][CONF_NAME],
                inverted=_configured_binary_sensors[_binary_sensor][CONF_INVERTED],
                device_class=_device_class,
                manufacturer=_configured_binary_sensors[_binary_sensor][
                    CONF_MANUFACTURER
                ],
                model=_configured_binary_sensors[_binary_sensor][CONF_DEVICE_MODEL],
                gateway=hass.data[DOMAIN][CONF_GATEWAY],
            )
            _binary_sensors.append(_binary_sensor)
        elif _who == 9:
            _binary_sensor = MyHOMEAuxiliary(
                hass=hass,
                device_id=_binary_sensor,
                who=_configured_binary_sensors[_binary_sensor][CONF_WHO],
                where=_configured_binary_sensors[_binary_sensor][CONF_WHERE],
                name=_configured_binary_sensors[_binary_sensor][CONF_NAME],
                inverted=_configured_binary_sensors[_binary_sensor][CONF_INVERTED],
                device_class=_device_class,
                manufacturer=_configured_binary_sensors[_binary_sensor][
                    CONF_MANUFACTURER
                ],
                model=_configured_binary_sensors[_binary_sensor][CONF_DEVICE_MODEL],
                gateway=hass.data[DOMAIN][CONF_GATEWAY],
            )
            _binary_sensors.append(_binary_sensor)
        elif _who == 1 and _device_class == BinarySensorDeviceClass.MOTION:
            _binary_sensor = MyHOMEMotionSensor(
                hass=hass,
                device_id=_binary_sensor,
                who=_configured_binary_sensors[_binary_sensor][CONF_WHO],
                where=_configured_binary_sensors[_binary_sensor][CONF_WHERE],
                name=_configured_binary_sensors[_binary_sensor][CONF_NAME],
                entity_name=_configured_binary_sensors[_binary_sensor][CONF_ENTITIES][
                    0
                ],
                inverted=_configured_binary_sensors[_binary_sensor][CONF_INVERTED],
                device_class=_device_class,
                manufacturer=_configured_binary_sensors[_binary_sensor][
                    CONF_MANUFACTURER
                ],
                model=_configured_binary_sensors[_binary_sensor][CONF_DEVICE_MODEL],
                gateway=hass.data[DOMAIN][CONF_GATEWAY],
            )
            _binary_sensors.append(_binary_sensor)

    async_add_entities(_binary_sensors)


async def async_unload_entry(hass, config_entry):  # pylint: disable=unused-argument
    if PLATFORM not in hass.data[DOMAIN][CONF]:
        return True

    _configured_binary_sensors = hass.data[DOMAIN][CONF][PLATFORM]

    for _binary_sensor in _configured_binary_sensors.keys():
        if _configured_binary_sensors[_binary_sensor][CONF_ENTITIES]:
            for _entity_name in _configured_binary_sensors[_binary_sensor][
                CONF_ENTITIES
            ]:
                del hass.data[DOMAIN][CONF_ENTITIES][f"{_binary_sensor}-{_entity_name}"]
        else:
            del hass.data[DOMAIN][CONF_ENTITIES][_binary_sensor]


class MyHOMEDryContact(MyHOMEEntity, BinarySensorEntity):
    def __init__(
        self,
        hass,
        name: str,
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
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._inverted = inverted

        self._attr_device_class = device_class

        self._attr_is_on = False
        self._attr_extra_state_attributes = {
            "Sensor": f"({self._where[0]}){self._where[1:]}"
        }

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway_handler.send_status_request(
            OWNDryContactCommand.status(self._where)
        )

    def handle_event(self, message: OWNDryContactEvent):
        """Handle an event message."""
        LOGGER.info(message.human_readable_log)
        self._attr_is_on = message.is_on != self._inverted
        self.async_schedule_update_ha_state()


class MyHOMEAuxiliary(MyHOMEEntity, BinarySensorEntity):
    def __init__(
        self,
        hass,
        name: str,
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
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._inverted = inverted

        self._attr_device_class = device_class

        self._attr_is_on = False
        self._attr_extra_state_attributes = {"Auxiliary channel": self._where}

    async def async_update(self):
        """AUX sensors are read only and cannot be queried, no async_update implementation."""

    def handle_event(self, message: OWNDryContactEvent):
        """Handle an event message."""
        LOGGER.info(message.human_readable_log)
        self._attr_is_on = message.is_on != self._inverted
        self.async_schedule_update_ha_state()


class MyHOMEMotionSensor(MyHOMEEntity, BinarySensorEntity, RestoreEntity):
    def __init__(
        self,
        hass,
        name: str,
        device_id: str,
        who: str,
        where: str,
        entity_name: str,
        inverted: bool,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        super().__init__(
            hass=hass,
            name=name,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._entity_name = entity_name
        self._inverted = inverted

        self._attr_unique_id = f"{self._device_id}-{self._entity_name}"

        self._attr_force_update = False
        self._last_updated = None
        self._timeout = timedelta(seconds=315)

        self._attr_device_class = device_class
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
        self._hass.data[DOMAIN][CONF_ENTITIES][self._attr_unique_id] = self
        await self._gateway_handler.send_status_request(
            OWNLightingCommand.get_pir_sensitivity(self._where)
        )
        await self._gateway_handler.send_status_request(
            OWNLightingCommand.get_motion_timeout(self._where)
        )
        state = await self.async_get_last_state()
        if state:
            self._attr_is_on = state.state == STATE_ON
            self._last_updated = state.last_updated
        await self.async_update()

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        if (
            self._attr_is_on
            and self._last_updated
            and self._last_updated + self._timeout < datetime.now(timezone.utc)
        ):
            self._attr_is_on = False
            self._last_updated = datetime.now(timezone.utc)
            self.async_schedule_update_ha_state()

    def handle_event(self, message: OWNLightingEvent):
        """Handle an event message."""
        LOGGER.info(message.human_readable_log)
        if message.message_type == MESSAGE_TYPE_MOTION and message.motion:
            self._attr_is_on = message.motion != self._inverted
        elif message.message_type == MESSAGE_TYPE_MOTION_TIMEOUT:
            self._timeout = message.motion_timeout + timedelta(seconds=15)
            self._attr_extra_state_attributes["Timeout"] = self._timeout.total_seconds()
        elif message.message_type == MESSAGE_TYPE_PIR_SENSITIVITY:
            self._attr_extra_state_attributes["Sensitivity"] = PIR_SENSITIVITY[
                message.pir_sensitivity
            ]
        self._last_updated = datetime.now(timezone.utc)
        self._attr_force_update = True
        self.async_write_ha_state()
        self._attr_force_update = False
