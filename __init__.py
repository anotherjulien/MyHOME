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

PLATFORMS = ["light", "switch", "cover", "binary_sensor", "sensor"]

async def async_setup(hass, config):
    """Set up the MyHOME component."""
    hass.data[DOMAIN] = {}

    if DOMAIN not in config:
        return True

    LOGGER.error("configuration.yaml not supported for this component!")

    return False

async def async_setup_entry(hass: core.HomeAssistant, entry: config_entries.ConfigEntry):

    myhome_gateway = MyHOMEGateway(hass, entry)

    if not await myhome_gateway.test():
        return False

    hass.data[DOMAIN][CONF_GATEWAY] = myhome_gateway

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

    await myhome_gateway.connect()

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "light")
    )
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "switch")
    )
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "cover")
    )
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "binary_sensor")
    )
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )

    myhome_gateway.listening_task = asyncio.create_task(myhome_gateway.listening_loop())

    return True

async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    myhome_gateway = hass.data[DOMAIN][entry.entry_id]
    await myhome_gateway.close_listener()