"""Support for MyHome switches (light modules used for controlled outlets, relays)."""
import voluptuous as vol

from homeassistant.components.switch import (
    PLATFORM_SCHEMA,
    DOMAIN as PLATFORM,
    SwitchDeviceClass,
    SwitchEntity,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_DEVICES,
    CONF_ENTITIES,
)
import homeassistant.helpers.config_validation as cv

from OWNd.message import (
    OWNLightingEvent,
    OWNLightingCommand,
)

from .const import (
    CONF,
    CONF_GATEWAY,
    CONF_WHO,
    CONF_WHERE,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_CLASS,
    DOMAIN,
    LOGGER,
)
from .myhome_device import MyHOMEEntity
from .gateway import MyHOMEGatewayHandler

MYHOME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WHERE): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_DEVICE_CLASS): vol.In(
            [SwitchDeviceClass.OUTLET, SwitchDeviceClass.SWITCH]
        ),
        vol.Optional(CONF_MANUFACTURER): cv.string,
        vol.Optional(CONF_DEVICE_MODEL): cv.string,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_DEVICES): cv.schema_with_slug_keys(MYHOME_SCHEMA)}
)


async def async_setup_platform(
    hass, config, async_add_entities, discovery_info=None
):  # pylint: disable=unused-argument
    if CONF not in hass.data[DOMAIN]:
        return False
    hass.data[DOMAIN][CONF][PLATFORM] = {}
    _configured_switches = config.get(CONF_DEVICES)

    if _configured_switches:
        for _, entity_info in _configured_switches.items():
            who = "1"
            where = entity_info[CONF_WHERE]
            device_id = f"{who}-{where}"
            name = (
                entity_info[CONF_NAME]
                if CONF_NAME in entity_info
                else f"A{where[:len(where)//2]}PL{where[len(where)//2:]}"
            )
            device_class = (
                entity_info[CONF_DEVICE_CLASS]
                if CONF_DEVICE_CLASS in entity_info
                else SwitchDeviceClass.SWITCH
            )
            entities = []
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
                CONF_DEVICE_CLASS: device_class,
                CONF_MANUFACTURER: manufacturer,
                CONF_DEVICE_MODEL: model,
            }


async def async_setup_entry(
    hass, config_entry, async_add_entities
):  # pylint: disable=unused-argument
    if PLATFORM not in hass.data[DOMAIN][CONF]:
        return True

    _switches = []
    _configured_switches = hass.data[DOMAIN][CONF][PLATFORM]

    for _switch in _configured_switches.keys():
        _switch = MyHOMESwitch(
            hass=hass,
            device_id=_switch,
            who=_configured_switches[_switch][CONF_WHO],
            where=_configured_switches[_switch][CONF_WHERE],
            name=_configured_switches[_switch][CONF_NAME],
            device_class=_configured_switches[_switch][CONF_DEVICE_CLASS],
            manufacturer=_configured_switches[_switch][CONF_MANUFACTURER],
            model=_configured_switches[_switch][CONF_DEVICE_MODEL],
            gateway=hass.data[DOMAIN][CONF_GATEWAY],
        )
        _switches.append(_switch)

    async_add_entities(_switches)


async def async_unload_entry(hass, config_entry):  # pylint: disable=unused-argument
    if PLATFORM not in hass.data[DOMAIN][CONF]:
        return True

    _configured_switches = hass.data[DOMAIN][CONF][PLATFORM]

    for _switch in _configured_switches.keys():
        del hass.data[DOMAIN][CONF_ENTITIES][_switch]


class MyHOMESwitch(MyHOMEEntity, SwitchEntity):
    def __init__(
        self,
        hass,
        name: str,
        device_id: str,
        who: str,
        where: str,
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

        self._attr_extra_state_attributes = {
            "A": where[: len(where) // 2],
            "PL": where[len(where) // 2 :],
        }

        self._attr_device_class = (
            SwitchDeviceClass.OUTLET
            if device_class.lower() == "outlet"
            else SwitchDeviceClass.SWITCH
        )

        self._attr_is_on = None

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway_handler.send_status_request(
            OWNLightingCommand.status(self._where)
        )

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Turn the device on."""
        await self._gateway_handler.send(OWNLightingCommand.switch_on(self._where))

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        """Turn the device off."""
        await self._gateway_handler.send(OWNLightingCommand.switch_off(self._where))

    def handle_event(self, message: OWNLightingEvent):
        """Handle an event message."""
        LOGGER.info(message.human_readable_log)
        self._attr_is_on = message.is_on
        self.async_schedule_update_ha_state()
