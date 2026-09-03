"""Support for common values for MyHome devices."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .gateway import MyHOMEGatewayHandler

from homeassistant.helpers.entity import Entity
from homeassistant.const import CONF_ENTITIES


from .const import DOMAIN, CONF_PLATFORMS, CONF_ENTITIES


class MyHOMEEntity(Entity):
    def __init__(
        self,
        hass,
        name: str,
        platform: str,
        device_id: str,
        who: str,
        where: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        self._hass = hass
        self._platform = platform
        self._who = who
        self._where = where
        self._device_id = device_id
        self._attr_unique_id = f"{gateway.mac}-{self._device_id}"
        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._model = model
        self._gateway_handler = gateway
        self._attr_has_entity_name = True
        self._attr_name = None
        self._attr_entity_registry_enabled_default = True
        self._attr_should_poll = False

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{gateway.mac}-{self._device_id}")},
            "name": name,
            "manufacturer": self._manufacturer,
            "model": self._model,
        }

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        # Set via_device_id to link this device to the gateway
        if "via_device_id" not in self._attr_device_info:
            from homeassistant.helpers import device_registry as dr
            device_registry = dr.async_get(self._hass)
            gateway_device = device_registry.async_get_device(
                identifiers={(DOMAIN, self._gateway_handler.unique_id)}
            )
            if gateway_device:
                self._attr_device_info["via_device_id"] = gateway_device.id

        # Initialize CONF_ENTITIES dict if it doesn't exist
        device_data = self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][self._platform][self._device_id]
        if CONF_ENTITIES not in device_data:
            device_data[CONF_ENTITIES] = {}

        # Store entity reference
        device_data[CONF_ENTITIES][self._platform] = self
        await self.async_update()

    async def async_will_remove_from_hass(self):
        """When entity is removed from hass."""
        device_data = self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][self._platform][self._device_id]
        if CONF_ENTITIES in device_data and self._platform in device_data[CONF_ENTITIES]:
            del device_data[CONF_ENTITIES][self._platform]
