""" MyHOME integration. """
import logging
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
    DOMAIN,
    LOGGER,
)
from  .gateway import MyHOMEGateway

_LOGGER = logging.getLogger(__name__)

CONF_WHERE = "where"

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

async def async_setup(hass, config):
    """Set up the MyHOME component."""
    # if DOMAIN not in config:
    #     return True
    
    # host = config[DOMAIN][CONF_HOST]
    # myhome = None

    # try:
    #     myhome = MyHOME(device=device, logger=_LOGGER)
    #     myhome.start()
    # except Exception as exception:
    #     _LOGGER.error("Cannot setup MyHOME component: %s", exception)
    #     return False

    # def stop_monitor(event):
    #     """Stop the SCSGate."""
    #     _LOGGER.info("Stopping MyHOME monitor thread")
    #     myhome.stop()

    # hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, stop_monitor)
    # hass.data[DOMAIN] = myhome

    return True

async def async_setup_entry(hass: core.HomeAssistant, entry: config_entries.ConfigEntry):

    myhome_gateway = MyHOMEGateway(hass, entry)

    if not await myhome_gateway.test():
        return False

    
    LOGGER.info(f"{DOMAIN}")
    LOGGER.info(f"{DOMAIN in hass.data}")
    LOGGER.info(entry.entry_id)
    LOGGER.info(myhome_gateway)

    hass.data[DOMAIN][entry.entry_id] = myhome_gateway

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

    hass.async_create_task(myhome_gateway.listening_loop())

    return True

class MyHOME:

    def __init__(self, device, logger):
        super().__init__()