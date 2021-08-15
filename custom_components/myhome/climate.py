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
    CONF_STANDALONE,
    CONF_CENTRAL,
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
    MESSAGE_TYPE_MAIN_HUMIDITY,
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
        vol.Optional(CONF_STANDALONE): cv.boolean,
        vol.Optional(CONF_CENTRAL): cv.boolean,
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
                standalone = entity_info[CONF_STANDALONE] if CONF_STANDALONE in entity_info else False
                central = entity_info[CONF_CENTRAL] if CONF_CENTRAL in entity_info else False
                manufacturer = entity_info[CONF_MANUFACTURER] if CONF_MANUFACTURER in entity_info else None
                model = entity_info[CONF_DEVICE_MODEL] if CONF_DEVICE_MODEL in entity_info else None
                gateway.add_climate_zone(zone, {CONF_NAME: name, CONF_HEATING_SUPPORT: heating, CONF_COOLING_SUPPORT: cooling, CONF_FAN_SUPPORT: fan, CONF_STANDALONE: standalone, CONF_CENTRAL: central, CONF_MANUFACTURER: manufacturer, CONF_DEVICE_MODEL: model})
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
            standalone=gateway_devices[device][CONF_STANDALONE],
            central=gateway_devices[device][CONF_CENTRAL],
            manufacturer=gateway_devices[device][CONF_MANUFACTURER],
            model=gateway_devices[device][CONF_DEVICE_MODEL],
            gateway=gateway
        )
        devices.append(device)
        
    async_add_entities(devices)

async def async_unload_entry(hass, config_entry):

    gateway = hass.data[DOMAIN][CONF_GATEWAY]
    gateway_devices = gateway.get_climate_zones()

    for device in gateway_devices.keys():
        del hass.data[DOMAIN][f"4-{device}"]

class MyHOMEClimate(ClimateEntity):

    def __init__(self, hass, zone: str, name: str, heating: bool, cooling: bool, fan: bool, standalone: bool, central: bool, manufacturer: str, model: str, gateway: MyHOMEGateway):

        self._hass = hass
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._model = model
        self._who = "4"
        self._zone = f"#0#{zone}" if central and zone != "#0" else zone
        self._standalone = standalone
        self._central = True if self._zone == "#0" else central

        self._attr_unique_id = f"{self._who}-{zone}"
        if name is None:
            self._attr_name = "Central unit" if self._zone == "#0" else f"Zone {self._zone}"
        else:
            self._attr_name = name
        self._gateway = gateway

        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, self._attr_unique_id)
            },
            "name": self._attr_name,
            "manufacturer": self._manufacturer,
            "model": self._model,
            "via_device": (DOMAIN, self._gateway.id),
        }
        
        self._attr_entity_registry_enabled_default = True
        self._attr_should_poll = False

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

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self._hass.data[DOMAIN][self._attr_unique_id] = self
        await self.async_update()

    async def async_will_remove_from_hass(self):
        """When entity is removed from hass."""
        del self._hass.data[DOMAIN][self._attr_unique_id]

    async def async_update(self):
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self._gateway.send_status_request(OWNHeatingCommand.status(self._zone))
    
    @property
    def target_temperature(self) -> float:
        if self._local_target_temperature is not None:
            return self._local_target_temperature
        else:
            return self._target_temperature

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if hvac_mode == HVAC_MODE_OFF:
            await self._gateway.send(OWNHeatingCommand.set_mode(where=self._zone, mode=CLIMATE_MODE_OFF, standalone=self._standalone))
        elif hvac_mode == HVAC_MODE_AUTO:
            await self._gateway.send(OWNHeatingCommand.set_mode(where=self._zone, mode=CLIMATE_MODE_AUTO, standalone=self._standalone))
        elif hvac_mode == HVAC_MODE_HEAT:
            if self._target_temperature is not None:
                await self._gateway.send(OWNHeatingCommand.set_temperature(where=self._zone, temperature=self._target_temperature, mode=CLIMATE_MODE_HEAT, standalone=self._standalone))
        elif hvac_mode == HVAC_MODE_COOL:
            if self._target_temperature is not None:
                await self._gateway.send(OWNHeatingCommand.set_temperature(where=self._zone, temperature=self._target_temperature, mode=CLIMATE_MODE_COOL, standalone=self._standalone))

    async def async_set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        pass

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        target_temperature = kwargs.get("temperature", self._local_target_temperature) - self._local_offset
        if self._attr_hvac_mode == HVAC_MODE_HEAT:
            await self._gateway.send(OWNHeatingCommand.set_temperature(where=self._zone, temperature=target_temperature, mode=CLIMATE_MODE_HEAT, standalone=self._standalone))
        elif self._attr_hvac_mode == HVAC_MODE_COOL:
            await self._gateway.send(OWNHeatingCommand.set_temperature(where=self._zone, temperature=target_temperature, mode=CLIMATE_MODE_COOL, standalone=self._standalone))
        else:
            await self._gateway.send(OWNHeatingCommand.set_temperature(where=self._zone, temperature=target_temperature, mode=CLIMATE_MODE_AUTO, standalone=self._standalone))

    def handle_event(self, message: OWNHeatingEvent):
        """Handle an event message."""
        if message.message_type == MESSAGE_TYPE_MAIN_TEMPERATURE:
            _LOGGER.info(message.human_readable_log)
            self._attr_current_temperature = message.main_temperature
        elif message.message_type == MESSAGE_TYPE_MAIN_HUMIDITY:
            _LOGGER.info(message.human_readable_log)
            self._attr_current_humidity = message.main_humidity
        elif message.message_type == MESSAGE_TYPE_TARGET_TEMPERATURE:
            _LOGGER.info(message.human_readable_log)
            self._target_temperature = message.set_temperature
            self._local_target_temperature = self._target_temperature + self._local_offset
        elif message.message_type == MESSAGE_TYPE_LOCAL_OFFSET:
            _LOGGER.info(message.human_readable_log)
            self._local_offset = message.local_offset
            self._local_target_temperature = self._target_temperature + self._local_offset
        elif message.message_type == MESSAGE_TYPE_LOCAL_TARGET_TEMPERATURE:
            _LOGGER.info(message.human_readable_log)
            self._local_target_temperature = message.local_set_temperature
            self._target_temperature = self._local_target_temperature - self._local_offset
        elif message.message_type == MESSAGE_TYPE_MODE:
            if message.mode == CLIMATE_MODE_AUTO:
                _LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_AUTO
                if self._attr_hvac_action == CURRENT_HVAC_OFF:
                    self._attr_hvac_action = CURRENT_HVAC_IDLE
            elif message.mode == CLIMATE_MODE_COOL:
                _LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_COOL
                if self._attr_hvac_action == CURRENT_HVAC_OFF:
                    self._attr_hvac_action = CURRENT_HVAC_IDLE
            elif message.mode == CLIMATE_MODE_HEAT:
                _LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_HEAT
                if self._attr_hvac_action == CURRENT_HVAC_OFF:
                    self._attr_hvac_action = CURRENT_HVAC_IDLE
            elif message.mode == CLIMATE_MODE_OFF:
                _LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_OFF
                self._attr_hvac_action = CURRENT_HVAC_OFF
        elif message.message_type == MESSAGE_TYPE_MODE_TARGET:
            if message.mode == CLIMATE_MODE_AUTO:
                _LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_AUTO
                if self._attr_hvac_action == CURRENT_HVAC_OFF:
                    self._attr_hvac_action = CURRENT_HVAC_IDLE
            elif message.mode == CLIMATE_MODE_COOL:
                _LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_COOL
                if self._attr_hvac_action == CURRENT_HVAC_OFF:
                    self._attr_hvac_action = CURRENT_HVAC_IDLE
            elif message.mode == CLIMATE_MODE_HEAT:
                _LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_HEAT
                if self._attr_hvac_action == CURRENT_HVAC_OFF:
                    self._attr_hvac_action = CURRENT_HVAC_IDLE 
            elif message.mode == CLIMATE_MODE_OFF:
                _LOGGER.info(message.human_readable_log)
                self._attr_hvac_mode = HVAC_MODE_OFF
                self._attr_hvac_action = CURRENT_HVAC_OFF
            self._target_temperature = message.set_temperature
            self._local_target_temperature = self._target_temperature + self._local_offset
        elif message.message_type == MESSAGE_TYPE_ACTION:
            _LOGGER.info(message.human_readable_log)
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
