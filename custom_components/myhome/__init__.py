""" MyHOME integration. """
import logging
import asyncio
from threading import Lock

from OWNd.connection import OWNSession
from OWNd.message import *
import voluptuous as vol

from homeassistant.const import (
    CONF_IP_ADDRESS, 
    CONF_PORT, 
    CONF_PASSWORD,
)
from homeassistant import config_entries, core
from homeassistant.core import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    CONF_FIRMWARE,
    CONF_GATEWAY,
    ATTR_MESSAGE,
    DOMAIN,
    LOGGER,
)
from .gateway import MyHOMEGateway

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_IP_ADDRESS): cv.string,
                vol.Optional(CONF_PORT): cv.positive_int,
                vol.Optional(CONF_PASSWORD): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA
)

PLATFORMS = ["light", "switch", "cover", "climate", "binary_sensor", "sensor"]

async def async_setup(hass, config):
    """Set up the MyHOME component."""
    hass.data[DOMAIN] = {}

    if DOMAIN not in config:
        return True

    LOGGER.error("configuration.yaml not supported for this component!")

    return False

async def async_setup_entry(hass: core.HomeAssistant, entry: config_entries.ConfigEntry):

    if CONF_GATEWAY in hass.data[DOMAIN] and isinstance(hass.data[DOMAIN][CONF_GATEWAY], MyHOMEGateway):
        myhome_gateway = hass.data[DOMAIN][CONF_GATEWAY]
    else:
        myhome_gateway = MyHOMEGateway(hass, entry)
        hass.data[DOMAIN][CONF_GATEWAY] = myhome_gateway

    if not await myhome_gateway.test():
        return False

    device_registry = await dr.async_get_registry(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, myhome_gateway.mac)},
        identifiers={(DOMAIN, myhome_gateway.id)},
        manufacturer=myhome_gateway.manufacturer,
        name=myhome_gateway.name,
        model=myhome_gateway.model,
        sw_version=myhome_gateway.firmware,
    )

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    myhome_gateway.listening_worker = hass.loop.create_task(myhome_gateway.listening_loop())
    for i in range(5):
        myhome_gateway.sending_workers.append(hass.loop.create_task(myhome_gateway.sending_loop(i)))

    async def handle_sync_time(call):
        timezone = hass.config.as_dict()['time_zone']
        await myhome_gateway.send(OWNGatewayCommand.set_datetime_to_now(timezone))
    
    hass.services.async_register(DOMAIN, "sync_time", handle_sync_time)

    async def handle_send_message(call):
        message = call.data.get(ATTR_MESSAGE, None)
        LOGGER.debug(f"message to be sent: {message}")
        if message is not None:
            OWN_message = OWNCommand.parse(message)
            if OWN_message is not None:
                LOGGER.debug(f"OWN Message: {OWN_message}")
                if OWN_message.is_valid:
                    LOGGER.debug("message valid")
                    await myhome_gateway.send(OWN_message)
            else:
                LOGGER.error(f"Could not parse message {message}, not sending it.")

    hass.services.async_register(DOMAIN, "send_message", handle_send_message)

    return True

async def async_unload_entry(hass, entry):
    """Unload a config entry."""

    LOGGER.info("Unloading MyHome entry.")

    for platform in PLATFORMS:
        await hass.config_entries.async_forward_entry_unload(entry, platform)

    hass.services.async_remove(DOMAIN, "sync_time")
    hass.services.async_remove(DOMAIN, "send_message")

    myhome_gateway = hass.data[DOMAIN][CONF_GATEWAY]
    return await myhome_gateway.close_listener()
