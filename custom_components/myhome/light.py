"""Support for MyHome lights."""
import voluptuous as vol

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_FLASH,
    FLASH_LONG,
    FLASH_SHORT,
    ATTR_TRANSITION,
    SUPPORT_BRIGHTNESS,
    SUPPORT_FLASH,
    SUPPORT_TRANSITION,
    PLATFORM_SCHEMA,
    DOMAIN as PLATFORM,
    LightEntity,
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
    CONF_DIMMABLE,
    DOMAIN,
    LOGGER,
)
from .myhome_device import MyHOMEEntity
from .gateway import MyHOMEGatewayHandler

MYHOME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WHERE): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_DIMMABLE): cv.boolean,
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
    _configured_lights = config.get(CONF_DEVICES)

    if _configured_lights:
        for _, entity_info in _configured_lights.items():
            who = "1"
            where = entity_info[CONF_WHERE]
            device_id = f"{who}-{where}"
            name = (
                entity_info[CONF_NAME]
                if CONF_NAME in entity_info
                else f"A{where[:len(where)//2]}PL{where[len(where)//2:]}"
            )
            dimmable = (
                entity_info[CONF_DIMMABLE] if CONF_DIMMABLE in entity_info else False
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
                CONF_DIMMABLE: dimmable,
                CONF_MANUFACTURER: manufacturer,
                CONF_DEVICE_MODEL: model,
            }


async def async_setup_entry(
    hass, config_entry, async_add_entities
):  # pylint: disable=unused-argument
    if PLATFORM not in hass.data[DOMAIN][CONF]:
        return True

    _lights = []
    _configured_lights = hass.data[DOMAIN][CONF][PLATFORM]

    for _light in _configured_lights.keys():
        _light = MyHOMELight(
            hass=hass,
            device_id=_light,
            who=_configured_lights[_light][CONF_WHO],
            where=_configured_lights[_light][CONF_WHERE],
            name=_configured_lights[_light][CONF_NAME],
            dimmable=_configured_lights[_light][CONF_DIMMABLE],
            manufacturer=_configured_lights[_light][CONF_MANUFACTURER],
            model=_configured_lights[_light][CONF_DEVICE_MODEL],
            gateway=hass.data[DOMAIN][CONF_GATEWAY],
        )
        _lights.append(_light)

    async_add_entities(_lights)


async def async_unload_entry(hass, config_entry):  # pylint: disable=unused-argument
    if PLATFORM not in hass.data[DOMAIN][CONF]:
        return True

    _configured_lights = hass.data[DOMAIN][CONF][PLATFORM]

    for _light in _configured_lights.keys():
        del hass.data[DOMAIN][CONF_ENTITIES][_light]


def eight_bits_to_percent(value: int) -> int:
    return int(round(100 / 255 * value, 0))


def percent_to_eight_bits(value: int) -> int:
    return int(round(255 / 100 * value, 0))


class MyHOMELight(MyHOMEEntity, LightEntity):
    def __init__(
        self,
        hass,
        name: str,
        device_id: str,
        who: str,
        where: str,
        dimmable: bool,
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

        self._attr_supported_features = 0
        if dimmable:
            self._attr_supported_features |= SUPPORT_BRIGHTNESS
            self._attr_supported_features |= SUPPORT_TRANSITION
        else:
            self._attr_supported_features |= SUPPORT_FLASH

        self._attr_extra_state_attributes = {
            "A": where[: len(where) // 2],
            "PL": where[len(where) // 2 :],
        }

        self._attr_is_on = None
        self._attr_brightness = None
        self._attr_brightness_pct = None

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        if self._attr_supported_features & SUPPORT_BRIGHTNESS:
            await self._gateway_handler.send_status_request(
                OWNLightingCommand.get_brightness(self._where)
            )
        else:
            await self._gateway_handler.send_status_request(
                OWNLightingCommand.status(self._where)
            )

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""

        if ATTR_FLASH in kwargs and self._attr_supported_features & SUPPORT_FLASH:
            if kwargs[ATTR_FLASH] == FLASH_SHORT:
                return await self._gateway_handler.send(
                    OWNLightingCommand.flash(self._where, 0.5)
                )
            elif kwargs[ATTR_FLASH] == FLASH_LONG:
                return await self._gateway_handler.send(
                    OWNLightingCommand.flash(self._where, 1.5)
                )

        if (
            (ATTR_BRIGHTNESS in kwargs or ATTR_BRIGHTNESS_PCT in kwargs)
            and self._attr_supported_features & SUPPORT_BRIGHTNESS
        ) or (
            ATTR_TRANSITION in kwargs
            and self._attr_supported_features & SUPPORT_TRANSITION
        ):
            if ATTR_BRIGHTNESS in kwargs or ATTR_BRIGHTNESS_PCT in kwargs:
                _percent_brightness = (
                    eight_bits_to_percent(kwargs[ATTR_BRIGHTNESS])
                    if ATTR_BRIGHTNESS in kwargs
                    else None
                )
                _percent_brightness = (
                    kwargs[ATTR_BRIGHTNESS_PCT]
                    if ATTR_BRIGHTNESS_PCT in kwargs
                    else _percent_brightness
                )

                if _percent_brightness == 0:
                    return await self.async_turn_off(**kwargs)
                else:
                    return (
                        await self._gateway_handler.send(
                            OWNLightingCommand.set_brightness(
                                self._where,
                                _percent_brightness,
                                int(kwargs[ATTR_TRANSITION]),
                            )
                        )
                        if ATTR_TRANSITION in kwargs
                        else await self._gateway_handler.send(
                            OWNLightingCommand.set_brightness(
                                self._where, _percent_brightness
                            )
                        )
                    )
            else:
                return await self._gateway_handler.send(
                    OWNLightingCommand.switch_on(
                        self._where, int(kwargs[ATTR_TRANSITION])
                    )
                )
        else:
            await self._gateway_handler.send(OWNLightingCommand.switch_on(self._where))
            if self._attr_supported_features & SUPPORT_BRIGHTNESS:
                await self.async_update()

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""

        if (
            ATTR_TRANSITION in kwargs
            and self._attr_supported_features & SUPPORT_TRANSITION
        ):
            return await self._gateway_handler.send(
                OWNLightingCommand.switch_off(self._where, int(kwargs[ATTR_TRANSITION]))
            )

        if ATTR_FLASH in kwargs and self._attr_supported_features & SUPPORT_FLASH:
            if kwargs[ATTR_FLASH] == FLASH_SHORT:
                return await self._gateway_handler.send(
                    OWNLightingCommand.flash(self._where, 0.5)
                )
            elif kwargs[ATTR_FLASH] == FLASH_LONG:
                return await self._gateway_handler.send(
                    OWNLightingCommand.flash(self._where, 1.5)
                )

        return await self._gateway_handler.send(
            OWNLightingCommand.switch_off(self._where)
        )

    def handle_event(self, message: OWNLightingEvent):
        """Handle an event message."""
        LOGGER.info(message.human_readable_log)
        self._attr_is_on = message.is_on
        if (
            self._attr_supported_features & SUPPORT_BRIGHTNESS
            and message.brightness is not None
        ):
            self._attr_brightness_pct = message.brightness
            self._attr_brightness = percent_to_eight_bits(message.brightness)
        self.async_schedule_update_ha_state()
