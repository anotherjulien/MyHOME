"""Support for MyHome heating."""
import logging

import voluptuous as vol

from homeassistant.components.climate import (
    ClimateEntity, 
    PLATFORM_SCHEMA,
)
from homeassistant.components.climate.const import (
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
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
    ATTR_ENTITY_ID,
    ATTR_STATE,
    CONF_DEVICES,
    TEMP_CELSIUS,
)

import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_GATEWAY,
    CONF_WHO,
    CONF_ZONE,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_HEATING_SUPPORT,
    CONF_COOLING_SUPPORT,
    CONF_FAN_SUPPORT,
    DOMAIN,
    LOGGER,
)
from .gateway import MyHOMEGateway
from OWNd.message import (
    OWNHeatingEvent,
    OWNHeatingCommand,
    CLIMATE_MODE_OFF,
    CLIMATE_MODE_HEAT,
    CLIMATE_MODE_COOL,
    CLIMATE_MODE_AUTO,
    MESSAGE_TYPE_MAIN_TEMPERATURE,
    MESSAGE_TYPE_SECONDARY_TEMPERATURE,
    MESSAGE_TYPE_TARGET_TEMPERATURE,
    MESSAGE_TYPE_LOCAL_OFFSET,
    MESSAGE_TYPE_LOCAL_TARGET_TEMPERATURE,
    MESSAGE_TYPE_MODE,
    MESSAGE_TYPE_MODE_TARGET,
    MESSAGE_TYPE_ACTION,
)

MYHOME_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ZONE): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_HEATING_SUPPORT): cv.boolean,
        vol.Optional(CONF_COOLING_SUPPORT): cv.boolean,
        #vol.Optional(CONF_FAN_SUPPORT): cv.boolean,
        vol.Optional(CONF_MANUFACTURER): cv.string,
        vol.Optional(CONF_DEVICE_MODEL): cv.string,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_DEVICES): cv.schema_with_slug_keys(MYHOME_SCHEMA)}
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    devices = config.get(CONF_DEVICES)
    try:
        gateway = hass.data[DOMAIN][CONF_GATEWAY]

        if devices:
            for _, entity_info in devices.items():
                zone = entity_info[CONF_ZONE] if CONF_ZONE in entity_info else "#0"
                name = entity_info[CONF_NAME] if CONF_NAME in entity_info else None
                heating = entity_info[CONF_HEATING_SUPPORT] if CONF_HEATING_SUPPORT in entity_info else True
                cooling = entity_info[CONF_COOLING_SUPPORT] if CONF_COOLING_SUPPORT in entity_info else False
                fan = entity_info[CONF_FAN_SUPPORT] if CONF_FAN_SUPPORT in entity_info else False
                manufacturer = entity_info[CONF_MANUFACTURER] if CONF_MANUFACTURER in entity_info else None
                model = entity_info[CONF_DEVICE_MODEL] if CONF_DEVICE_MODEL in entity_info else None
                gateway.add_climate_zone(zone, {CONF_NAME: name, CONF_HEATING_SUPPORT: heating, CONF_COOLING_SUPPORT: cooling, CONF_FAN_SUPPORT: fan, CONF_MANUFACTURER: manufacturer, CONF_DEVICE_MODEL: model})
    except KeyError:
        _LOGGER.warning("Climate devices configured but no gateway present in configuration.")


async def async_setup_entry(hass, config_entry, async_add_entities):
    devices = []
    gateway = hass.data[DOMAIN][CONF_GATEWAY]

    gateway_devices = gateway.get_climate_zones()
    for device in gateway_devices.keys():
        device = MyHOMEClimate(
            hass=hass,
            zone=device,
            name=gateway_devices[device][CONF_NAME],
            heating=gateway_devices[device][CONF_HEATING_SUPPORT],
            cooling=gateway_devices[device][CONF_COOLING_SUPPORT],
            fan=gateway_devices[device][CONF_FAN_SUPPORT],
            manufacturer=gateway_devices[device][CONF_MANUFACTURER],
            model=gateway_devices[device][CONF_DEVICE_MODEL],
            gateway=gateway
        )
        devices.append(device)
        
    async_add_entities(devices)

    for device in gateway_devices.keys():
        await gateway.send_status_request(OWNHeatingCommand.status(device))

class MyHOMEClimate(ClimateEntity):

    def __init__(self, hass, zone: str, name: str, heating: bool, cooling: bool, fan: bool, manufacturer: str, model: str, gateway: MyHOMEGateway):

        self._name = name
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._model = model
        self._who = "4"
        self._zone = zone
        self._id = f"{self._who}-{self._zone}"
        if self._name is None:
            self._name = "Central unit" if self._zone == "#0" else f"Zone {self._zone}"
        self._gateway = gateway

        self._supported_features = 0
        self._hvac_modes = [HVAC_MODE_OFF]
        self._heating = heating
        self._cooling = cooling
        if heating or cooling:
            self._supported_features |= SUPPORT_TARGET_TEMPERATURE
            self._hvac_modes.append(HVAC_MODE_AUTO)
            if heating:
                self._hvac_modes.append(HVAC_MODE_HEAT)
            if cooling:
                self._hvac_modes.append(HVAC_MODE_COOL)

        self._fan_modes = []
        self._fan = fan
        if fan:
            self._supported_features |= SUPPORT_FAN_MODE
            self._fan_modes = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_OFF]

        self._current_temperature = None
        self._target_temperature = None
        self._local_offset = 0
        self._local_target_temperature = None

        self._hvac_mode = None
        self._hvac_action = None

        self._fan_mode = None

        hass.data[DOMAIN][self._id] = self

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway.send_status_request(OWNHeatingCommand.status(self._zone))

    @property
    def device_info(self):
        return {
            "identifiers": {
                (DOMAIN, self.unique_id)
            },
            "name": self.name,
            "manufacturer": self._manufacturer,
            "model": self._model,
            "via_device": (DOMAIN, self._gateway.id),
        }

    @property
    def should_poll(self):
        """No polling needed for a MyHome device."""
        return False

    @property
    def name(self):
        """Return the name of the device if any."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique ID of the device."""
        return self._id

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._supported_features

    @property
    def hvac_modes(self):
        """Return the list of available hvac operation modes."""
        return self._hvac_modes

    @property
    def fan_modes(self):
        """Return the list of available fan operation modes."""
        return self._fan_modes

    @property
    def temperature_unit(self) -> str:
        return TEMP_CELSIUS

    @property
    def precision(self) -> float:
        return 0.1

    @property
    def target_temperature_step(self) -> float:
        return 0.5

    @property
    def min_temp(self) -> int:
        return 5
    
    @property
    def max_temp(self) -> int:
        return 40

    @property
    def current_temperature(self) -> float:
        return self._current_temperature

    @property
    def target_temperature(self) -> float:
        return self._local_target_temperature

    @property
    def hvac_mode(self) -> str:
        return self._hvac_mode

    @property
    def hvac_action(self) -> str:
        return self._hvac_action

    @property
    def fan_mode(self) -> str:
        return self._fan_mode

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if hvac_mode == HVAC_MODE_OFF:
            await self._gateway.send(OWNHeatingCommand.set_mode(where=self._zone, mode=CLIMATE_MODE_OFF))
        elif hvac_mode == HVAC_MODE_AUTO:
            await self._gateway.send(OWNHeatingCommand.set_mode(where=self._zone, mode=CLIMATE_MODE_AUTO))
        elif hvac_mode == HVAC_MODE_HEAT:
            if self._target_temperature is not None:
                await self._gateway.send(OWNHeatingCommand.set_temperature(where=self._zone, temperature=self._target_temperature, mode=CLIMATE_MODE_HEAT))
        elif hvac_mode == HVAC_MODE_COOL:
            if self._target_temperature is not None:
                await self._gateway.send(OWNHeatingCommand.set_temperature(where=self._zone, temperature=self._target_temperature, mode=CLIMATE_MODE_COOL))

    async def async_set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        pass

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        target_temperature = kwargs.get("temperature", self._local_target_temperature) - self._local_offset
        if self._hvac_mode == HVAC_MODE_HEAT:
            await self._gateway.send(OWNHeatingCommand.set_temperature(where=self._zone, temperature=target_temperature, mode=CLIMATE_MODE_HEAT))
        elif self._hvac_mode == HVAC_MODE_COOL:
            await self._gateway.send(OWNHeatingCommand.set_temperature(where=self._zone, temperature=target_temperature, mode=CLIMATE_MODE_COOL))
        else:
            await self._gateway.send(OWNHeatingCommand.set_temperature(where=self._zone, temperature=target_temperature, mode=CLIMATE_MODE_AUTO))

    def handle_event(self, message: OWNHeatingEvent):
        """Handle an event message."""
        if message.message_type == MESSAGE_TYPE_MAIN_TEMPERATURE:
            self._current_temperature = message.main_temperature
        elif message.message_type == MESSAGE_TYPE_TARGET_TEMPERATURE:
            self._target_temperature = message.set_temperature
        elif message.message_type == MESSAGE_TYPE_LOCAL_OFFSET:
            self._local_offset = message.local_offset
        elif message.message_type == MESSAGE_TYPE_LOCAL_TARGET_TEMPERATURE:
            self._local_target_temperature = message.local_set_temperature
        elif message.message_type == MESSAGE_TYPE_MODE:
            if message.mode == CLIMATE_MODE_AUTO:
                self._hvac_mode = HVAC_MODE_AUTO
            elif message.mode == CLIMATE_MODE_COOL:
                self._hvac_mode = HVAC_MODE_COOL
            elif message.mode == CLIMATE_MODE_HEAT:
                self._hvac_mode = HVAC_MODE_HEAT
            elif message.mode == CLIMATE_MODE_OFF:
                self._hvac_mode = HVAC_MODE_OFF
        elif message.message_type == MESSAGE_TYPE_MODE_TARGET:
            if message.mode == CLIMATE_MODE_AUTO:
                self._hvac_mode = HVAC_MODE_AUTO
            elif message.mode == CLIMATE_MODE_COOL:
                self._hvac_mode = HVAC_MODE_COOL
            elif message.mode == CLIMATE_MODE_HEAT:
                self._hvac_mode = HVAC_MODE_HEAT
            elif message.mode == CLIMATE_MODE_OFF:
                self._hvac_mode = HVAC_MODE_OFF
            self._target_temperature = message.set_temperature
        elif message.message_type == MESSAGE_TYPE_ACTION:
            if message.is_active:
                if self._heating and self._cooling:
                    if message.is_heating:
                        self._hvac_action = CURRENT_HVAC_HEAT
                    elif message.is_cooling:
                        self._hvac_action = CURRENT_HVAC_COOL
                elif self._heating:
                    self._hvac_action = CURRENT_HVAC_HEAT
                elif self._cooling:
                    self._hvac_action = CURRENT_HVAC_COOL
            elif self._hvac_mode == HVAC_MODE_OFF:
                self._hvac_action = CURRENT_HVAC_OFF
            else:
                self._hvac_action = CURRENT_HVAC_IDLE
                
        self.async_schedule_update_ha_state()
