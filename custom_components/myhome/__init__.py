""" MyHOME integration. """
from homeassistant.config_entries import ConfigEntry, SOURCE_REAUTH
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, format_mac
from homeassistant.helpers.entity_registry import (
    async_entries_for_config_entry,
    async_entries_for_device,
)

from OWNd.message import OWNGatewayCommand, OWNCommand

from .const import (
    CONF,
    CONF_ENTITIES,
    CONF_GATEWAY,
    ATTR_MESSAGE,
    CONF_WORKER_COUNT,
    CONF_CENTRAL,
    DOMAIN,
    LOGGER,
)
from .gateway import MyHOMEGatewayHandler

PLATFORMS = ["light", "switch", "cover", "climate", "binary_sensor", "sensor"]


async def async_setup(hass, config):
    """Set up the MyHOME component."""
    hass.data[DOMAIN] = {}

    if DOMAIN not in config:
        return True

    LOGGER.error("configuration.yaml not supported for this component!")

    return False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):

    if CONF not in hass.data[DOMAIN]:
        hass.data[DOMAIN][CONF] = {}
    if CONF_ENTITIES not in hass.data[DOMAIN]:
        hass.data[DOMAIN][CONF_ENTITIES] = {}

    # Migrating the config entry's unique_id if it was not formated to the recommended hass standard
    if entry.unique_id != format_mac(entry.unique_id):
        hass.config_entries.async_update_entry(
            entry, unique_id=format_mac(entry.unique_id)
        )
        LOGGER.warning("Migrating config entry unique_id to %s", entry.unique_id)

    hass.data[DOMAIN][CONF_GATEWAY] = MyHOMEGatewayHandler(
        hass=hass, config_entry=entry
    )

    try:
        tests_results = await hass.data[DOMAIN][CONF_GATEWAY].test()
    except OSError as ose:
        _gateway_handler = hass.data[DOMAIN].pop(CONF_GATEWAY)
        _host = _gateway_handler.gateway.host
        raise ConfigEntryNotReady(
            f"Gateway cannot be reached at {_host}, make sure its address is correct."
        ) from ose

    if not tests_results["Success"]:
        if (
            tests_results["Message"] == "password_error"
            or tests_results["Message"] == "password_required"
        ):
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_REAUTH},
                    data=entry.data,
                )
            )
        del hass.data[DOMAIN][CONF_GATEWAY]
        return False

    _command_worker_count = (
        int(entry.options[CONF_WORKER_COUNT])
        if CONF_WORKER_COUNT in entry.options
        else 1
    )

    entity_registry = await hass.helpers.entity_registry.async_get_registry()
    device_registry = await hass.helpers.device_registry.async_get_registry()

    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(CONNECTION_NETWORK_MAC, hass.data[DOMAIN][CONF_GATEWAY].mac)},
        identifiers={(DOMAIN, hass.data[DOMAIN][CONF_GATEWAY].unique_id)},
        manufacturer=hass.data[DOMAIN][CONF_GATEWAY].manufacturer,
        name=hass.data[DOMAIN][CONF_GATEWAY].name,
        model=hass.data[DOMAIN][CONF_GATEWAY].model,
        sw_version=hass.data[DOMAIN][CONF_GATEWAY].firmware,
    )

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    hass.data[DOMAIN][CONF_GATEWAY].listening_worker = hass.loop.create_task(
        hass.data[DOMAIN][CONF_GATEWAY].listening_loop()
    )
    for i in range(_command_worker_count):
        hass.data[DOMAIN][CONF_GATEWAY].sending_workers.append(
            hass.loop.create_task(hass.data[DOMAIN][CONF_GATEWAY].sending_loop(i))
        )

    async def handle_sync_time(call):  # pylint: disable=unused-argument
        timezone = hass.config.as_dict()["time_zone"]
        await hass.data[DOMAIN][CONF_GATEWAY].send(
            OWNGatewayCommand.set_datetime_to_now(timezone)
        )

    hass.services.async_register(DOMAIN, "sync_time", handle_sync_time)

    async def handle_send_message(call):
        message = call.data.get(ATTR_MESSAGE, None)
        LOGGER.debug("message to be sent: %s", message)
        if message is not None:
            own_message = OWNCommand.parse(message)
            if own_message is not None:
                LOGGER.debug("OWN Message: %s", own_message)
                if own_message.is_valid:
                    LOGGER.debug("message valid")
                    await hass.data[DOMAIN][CONF_GATEWAY].send(own_message)
            else:
                LOGGER.error("Could not parse message %s, not sending it.", message)

    hass.services.async_register(DOMAIN, "send_message", handle_send_message)

    async def handle_registry_cleanup(call):

        entity_entries = async_entries_for_config_entry(entity_registry, entry.entry_id)

        entities_to_be_removed = []
        devices_to_be_removed = [
            device_entry.id
            for device_entry in device_registry.devices.values()
            if entry.entry_id in device_entry.config_entries
        ]
        gateway_entry = device_registry.async_get_device(
            identifiers={(DOMAIN, hass.data[DOMAIN][CONF_GATEWAY].unique_id)},
            connections={(CONNECTION_NETWORK_MAC, hass.data[DOMAIN][CONF_GATEWAY].mac)},
        )
        if gateway_entry.id in devices_to_be_removed:
            devices_to_be_removed.remove(gateway_entry.id)

        configured_entities = []

        for platform in PLATFORMS:
            if platform in hass.data[DOMAIN][CONF]:
                for _device in hass.data[DOMAIN][CONF][platform].keys():
                    if hass.data[DOMAIN][CONF][platform][_device][CONF_ENTITIES]:
                        for _entity_name in hass.data[DOMAIN][CONF][platform][_device][
                            CONF_ENTITIES
                        ]:
                            configured_entities.append(f"{_device}-{_entity_name}")
                    else:
                        configured_entities.append(_device)

        for entity_entry in entity_entries:

            if entity_entry.unique_id in configured_entities:
                if entity_entry.device_id in devices_to_be_removed:
                    devices_to_be_removed.remove(entity_entry.device_id)
                continue

            entities_to_be_removed.append(entity_entry.entity_id)

        for enity_id in entities_to_be_removed:
            entity_registry.async_remove(enity_id)

        for device_id in devices_to_be_removed:
            if (
                len(
                    async_entries_for_device(
                        entity_registry, device_id, include_disabled_entities=True
                    )
                )
                == 0
            ):
                device_registry.async_remove_device(device_id)
        
    hass.services.async_register(DOMAIN, "registry_cleanup", handle_registry_cleanup)

    return True


async def async_unload_entry(hass, entry):
    """Unload a config entry."""

    LOGGER.info("Unloading MyHome entry.")

    for platform in PLATFORMS:
        await hass.config_entries.async_forward_entry_unload(entry, platform)

    hass.services.async_remove(DOMAIN, "sync_time")
    hass.services.async_remove(DOMAIN, "send_message")

    gateway_handler = hass.data[DOMAIN].pop(CONF_GATEWAY)
    return await gateway_handler.close_listener()
