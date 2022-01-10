"""Support for MyHome heating."""
import voluptuous as vol

from homeassistant.components.climate import (
    ClimateEntity,
    PLATFORM_SCHEMA,
    DOMAIN as PLATFORM,
)
from homeassistant.components.climate.const import (
    HVAC_MODE_AUTO,
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    FAN_OFF,
    FAN_AUTO,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_HIGH,
    SUPPORT_FAN_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    CURRENT_HVAC_OFF,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_IDLE,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_DEVICES,
    CONF_ENTITIES,
    TEMP_CELSIUS,
)
import homeassistant.helpers.config_validation as cv

from OWNd.message import (
    OWNHeatingEvent,
    OWNHeatingCommand,
    CLIMATE_MODE_OFF,
    CLIMATE_MODE_HEAT,
    CLIMATE_MODE_COOL,
    CLIMATE_MODE_AUTO,
    MESSAGE_TYPE_MAIN_TEMPERATURE,
    MESSAGE_TYPE_MAIN_HUMIDITY,
    MESSAGE_TYPE_TARGET_TEMPERATURE,
    MESSAGE_TYPE_LOCAL_OFFSET,
    MESSAGE_TYPE_LOCAL_TARGET_TEMPERATURE,
    MESSAGE_TYPE_MODE,
    MESSAGE_TYPE_MODE_TARGET,
    MESSAGE_TYPE_ACTION,
)

from .const import (
    CONF,
    CONF_GATEWAY,
    CONF_WHO,
    CONF_ZONE,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_HEATING_SUPPORT,
    CONF_COOLING_SUPPORT,
    CONF_FAN_SUPPORT,
    CONF_STANDALONE,
    CONF_CENTRAL,
    DOMAIN,
    LOGGER,
)
from .myhome_device import MyHOMEEntity
from .gateway import MyHOMEGatewayHandler

MYHOME_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ZONE): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_HEATING_SUPPORT): cv.boolean,
        vol.Optional(CONF_COOLING_SUPPORT): cv.boolean,
        vol.Optional(CONF_STANDALONE): cv.boolean,
        vol.Optional(CONF_CENTRAL): cv.boolean,
        # vol.Optional(CONF_FAN_SUPPORT): cv.boolean,
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
    _configured_climate_devices = config.get(CONF_DEVICES)

    if _configured_climate_devices:
        for _, entity_info in _configured_climate_devices.items():
            who = "4"
            zone = entity_info[CONF_ZONE] if CONF_ZONE in entity_info else "#0"
            device_id = f"{who}-{zone}"
            central = (
                entity_info[CONF_CENTRAL] if CONF_CENTRAL in entity_info else False
            )
            zone = f"#0#{zone}" if central and zone != "#0" else zone
            name = (
                entity_info[CONF_NAME]
                if CONF_NAME in entity_info
                else "Central unit"
                if zone.startswith("#0")
                else f"Zone {zone}"
            )
            heating = (
                entity_info[CONF_HEATING_SUPPORT]
                if CONF_HEATING_SUPPORT in entity_info
                else True
            )
            cooling = (
                entity_info[CONF_COOLING_SUPPORT]
                if CONF_COOLING_SUPPORT in entity_info
                else False
            )
            fan = (
                entity_info[CONF_FAN_SUPPORT]
                if CONF_FAN_SUPPORT in entity_info
                else False
            )
            standalone = (
                entity_info[CONF_STANDALONE]
                if CONF_STANDALONE in entity_info
                else False
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
                CONF_ZONE: zone,
                CONF_ENTITIES: entities,
                CONF_NAME: name,
                CONF_HEATING_SUPPORT: heating,
                CONF_COOLING_SUPPORT: cooling,
                CONF_FAN_SUPPORT: fan,
                CONF_STANDALONE: standalone,
                CONF_CENTRAL: central,
                CONF_MANUFACTURER: manufacturer,
                CONF_DEVICE_MODEL: model,
            }


async def async_setup_entry(
    hass, config_entry, async_add_entities
):  # pylint: disable=unused-argument
    if PLATFORM not in hass.data[DOMAIN][CONF]:
        return True

    _climate_devices = []
    _configured_climate_devices = hass.data[DOMAIN][CONF][PLATFORM]

    for _climate_device in _configured_climate_devices.keys():
        _climate_devices.append(
            MyHOMEClimate(
                hass=hass,
                device_id=_climate_device,
                who=_configured_climate_devices[_climate_device][CONF_WHO],
                where=_configured_climate_devices[_climate_device][CONF_ZONE],
                name=_configured_climate_devices[_climate_device][CONF_NAME],
                heating=_configured_climate_devices[_climate_device][
                    CONF_HEATING_SUPPORT
                ],
                cooling=_configured_climate_devices[_climate_device][
                    CONF_COOLING_SUPPORT
                ],
                fan=_configured_climate_devices[_climate_device][CONF_FAN_SUPPORT],
                standalone=_configured_climate_devices[_climate_device][
                    CONF_STANDALONE
                ],
                central=_configured_climate_devices[_climate_device][CONF_CENTRAL],
                manufacturer=_configured_climate_devices[_climate_device][
                    CONF_MANUFACTURER
                ],
                model=_configured_climate_devices[_climate_device][CONF_DEVICE_MODEL],
                gateway=hass.data[DOMAIN][CONF_GATEWAY],
            )
        )

    async_add_entities(_climate_devices)


async def async_unload_entry(hass, config_entry):  # pylint: disable=unused-argument
    if PLATFORM not in hass.data[DOMAIN][CONF]:
        return True

    _configured_climate_devices = hass.data[DOMAIN][CONF][PLATFORM]

    for _climate_device in _configured_climate_devices.keys():
        del hass.data[DOMAIN][CONF_ENTITIES][_climate_device]


class MyHOMEClimate(MyHOMEEntity, ClimateEntity):
    def __init__(
        self,
        hass,
        name: str,
        device_id: str,
        who: str,
        where: str,
        heating: bool,
        cooling: bool,
        fan: bool,
        standalone: bool,
        central: bool,
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

        self._standalone = standalone
        self._central = True if self._where == "#0" else central

        self._attr_temperature_unit = TEMP_CELSIUS
        self._attr_precision = 0.1
        self._attr_target_temperature_step = 0.5
        self._attr_min_temp = 5
        self._attr_max_temp = 40

        self._attr_supported_features = 0
        self._attr_hvac_modes = [HVAC_MODE_OFF]
        self._heating = heating
        self._cooling = cooling
        if heating or cooling:
            self._attr_supported_features |= SUPPORT_TARGET_TEMPERATURE
            if not self._central:
                self._attr_hvac_modes.append(HVAC_MODE_AUTO)
            if heating:
                self._attr_hvac_modes.append(HVAC_MODE_HEAT)
            if cooling:
                self._attr_hvac_modes.append(HVAC_MODE_COOL)

        self._attr_fan_modes = []
        self._fan = fan
        if fan:
            self._attr_supported_features |= SUPPORT_FAN_MODE
            self._attr_fan_modes = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_OFF]

        self._attr_current_temperature = None
        self._attr_current_humidity = None
        self._target_temperature = None
        self._local_offset = 0
        self._local_target_temperature = None

        self._attr_hvac_mode = None
        self._attr_hvac_action = None

        self._attr_fan_mode = None

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway_handler.send_status_request(
            OWNHeatingCommand.status(self._where)
        )

    @property
    def target_temperature(self) -> float:
        if self._local_target_temperature is not None:
            return self._local_target_temperature
        else:
            return self._target_temperature

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if hvac_mode == HVAC_MODE_OFF:
            await self._gateway_handler.send(
                OWNHeatingCommand.set_mode(
                    where=self._where,
                    mode=CLIMATE_MODE_OFF,
                    standalone=self._standalone,
                )
            )
        elif hvac_mode == HVAC_MODE_AUTO:
            await self._gateway_handler.send(
                OWNHeatingCommand.set_mode(
                    where=self._where,
                    mode=CLIMATE_MODE_AUTO,
                    standalone=self._standalone,
                )
            )
        elif hvac_mode == HVAC_MODE_HEAT:
            if self._target_temperature is not None:
                await self._gateway_handler.send(
                    OWNHeatingCommand.set_temperature(
                        where=self._where,
                        temperature=self._target_temperature,
                        mode=CLIMATE_MODE_HEAT,
                        standalone=self._standalone,
                    )
                )
        elif hvac_mode == HVAC_MODE_COOL:
            if self._target_temperature is not None:
                await self._gateway_handler.send(
                    OWNHeatingCommand.set_temperature(
                        where=self._where,
                        temperature=self._target_temperature,
                        mode=CLIMATE_MODE_COOL,
                        standalone=self._standalone,
                    )
                )

    # async def async_set_fan_mode(self, fan_mode):
    #     """Set new target fan mode."""
    #     pass

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        target_temperature = (
            kwargs.get("temperature", self._local_target_temperature)
            - self._local_offset
        )
        if self._attr_hvac_mode == HVAC_MODE_HEAT:
            await self._gateway_handler.send(
                OWNHeatingCommand.set_temperature(
                    where=self._where,
                    temperature=target_temperature,
                    mode=CLIMATE_MODE_HEAT,
                    standalone=self._standalone,
                )
            )
        elif self._attr_hvac_mode == HVAC_MODE_COOL:
            await self._gateway_handler.send(
                OWNHeatingCommand.set_temperature(
                    where=self._where,
                    temperature=target_temperature,
                    mode=CLIMATE_MODE_COOL,
                    standalone=self._standalone,
                )
            )
        else:
            await self._gateway_handler.send(
                OWNHeatingCommand.set_temperature(
                    where=self._where,
                    temperature=target_temperature,
                    mode=CLIMATE_MODE_AUTO,
                    standalone=self._standalone,
                )
            )

    def handle_event(self, message: OWNHeatingEvent):
        """Handle an event message."""
        if message.message_type == MESSAGE_TYPE_MAIN_TEMPERATURE:
            LOGGER.info(message.human_readable_log)
            self._attr_current_temperature = message.main_temperature
        elif message.message_type == MESSAGE_TYPE_MAIN_HUMIDITY:
            LOGGER.info(message.human_readable_log)
            self._attr_current_humidity = message.main_humidity
        elif message.message_type == MESSAGE_TYPE_TARGET_TEMPERATURE:
            LOGGER.info(message.human_readable_log)
            self._target_temperature = message.set_temperature
            self._local_target_temperature = (
                self._target_temperature + self._local_offset
            )
        elif message.message_type == MESSAGE_TYPE_LOCAL_OFFSET:
            LOGGER.info(message.human_readable_log)
            self._local_offset = message.local_offset
            if self._target_temperature is not None:
                self._local_target_temperature = (
                    self._target_temperature + self._local_offset
                )
        elif message.message_type == MESSAGE_TYPE_LOCAL_TARGET_TEMPERATURE:
            LOGGER.info(message.human_readable_log)
            self._local_target_temperature = message.local_set_temperature
            self._target_temperature = (
                self._local_target_temperature - self._local_offset
            )
        elif message.message_type == MESSAGE_TYPE_MODE:
            if (
                message.mode == CLIMATE_MODE_AUTO
                and HVAC_MODE_AUTO in self._attr_hvac_modes
            ):
                LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_AUTO
                if self._attr_hvac_action == CURRENT_HVAC_OFF:
                    self._attr_hvac_action = CURRENT_HVAC_IDLE
            elif (
                message.mode == CLIMATE_MODE_COOL
                and HVAC_MODE_COOL in self._attr_hvac_modes
            ):
                LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_COOL
                if self._attr_hvac_action == CURRENT_HVAC_OFF:
                    self._attr_hvac_action = CURRENT_HVAC_IDLE
            elif (
                message.mode == CLIMATE_MODE_HEAT
                and HVAC_MODE_HEAT in self._attr_hvac_modes
            ):
                LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_HEAT
                if self._attr_hvac_action == CURRENT_HVAC_OFF:
                    self._attr_hvac_action = CURRENT_HVAC_IDLE
            elif message.mode == CLIMATE_MODE_OFF:
                LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_OFF
                self._attr_hvac_action = CURRENT_HVAC_OFF
        elif message.message_type == MESSAGE_TYPE_MODE_TARGET:
            if (
                message.mode == CLIMATE_MODE_AUTO
                and HVAC_MODE_AUTO in self._attr_hvac_modes
            ):
                LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_AUTO
                if self._attr_hvac_action == CURRENT_HVAC_OFF:
                    self._attr_hvac_action = CURRENT_HVAC_IDLE
            elif (
                message.mode == CLIMATE_MODE_COOL
                and HVAC_MODE_COOL in self._attr_hvac_modes
            ):
                LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_COOL
                if self._attr_hvac_action == CURRENT_HVAC_OFF:
                    self._attr_hvac_action = CURRENT_HVAC_IDLE
            elif (
                message.mode == CLIMATE_MODE_HEAT
                and HVAC_MODE_HEAT in self._attr_hvac_modes
            ):
                LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_HEAT
                if self._attr_hvac_action == CURRENT_HVAC_OFF:
                    self._attr_hvac_action = CURRENT_HVAC_IDLE
            elif message.mode == CLIMATE_MODE_OFF:
                LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_OFF
                self._attr_hvac_action = CURRENT_HVAC_OFF
            self._target_temperature = message.set_temperature
            self._local_target_temperature = (
                self._target_temperature + self._local_offset
            )
        elif message.message_type == MESSAGE_TYPE_ACTION:
            LOGGER.info(message.human_readable_log)
            if message.is_active():
                if self._heating and self._cooling:
                    if message.is_heating():
                        self._attr_hvac_action = CURRENT_HVAC_HEAT
                    elif message.is_cooling():
                        self._attr_hvac_action = CURRENT_HVAC_COOL
                elif self._heating:
                    self._attr_hvac_action = CURRENT_HVAC_HEAT
                elif self._cooling:
                    self._attr_hvac_action = CURRENT_HVAC_COOL
            elif self._attr_hvac_mode == HVAC_MODE_OFF:
                self._attr_hvac_action = CURRENT_HVAC_OFF
            else:
                self._attr_hvac_action = CURRENT_HVAC_IDLE

        self.async_schedule_update_ha_state()
