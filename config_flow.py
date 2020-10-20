"""Config flow to configure Philips Hue."""
import asyncio
from typing import Dict, Optional
from urllib.parse import urlparse

from OWNd.connection import OWNSession, OWNGateway
from OWNd.discovery import find_gateways
from OWNd.message import OWNEvent, OWNLightingEvent
import async_timeout
import voluptuous as vol

from homeassistant import config_entries, core
from homeassistant.components import ssdp
from homeassistant.const import (
    CONF_HOST, 
    CONF_PORT, 
    CONF_PASSWORD, 
    CONF_NAME, 
    CONF_MAC, 
    CONF_ID, 
    CONF_FRIENDLY_NAME,
    CONF_LIGHTS,
    CONF_COVERS,
)
from homeassistant.helpers import aiohttp_client

from .const import (
    CONF_FIRMWARE,
    CONF_SSDP_LOCATION,
    CONF_SSDP_ST,
    CONF_DEVICE_TYPE,
    CONF_MANUFACTURER,
    CONF_MANUFACTURER_URL,
    CONF_UDN,
    CONF_WHO,
    CONF_WHERE,
    CONF_PARENT_ID,
    DOMAIN,
    LOGGER,
)

class MyhomeFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a MyHome config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    # pylint: disable=no-member # https://github.com/PyCQA/pylint/issues/3167

    def __init__(self):
        """Initialize the MyHome flow."""
        self.gateway: Optional[OWNGateway] = None
        self.discovered_gateways: Optional[Dict[str, OWNGateway]] = None

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if (
            user_input is not None
            and self.discovered_gateways is not None
            and user_input["id"] in self.discovered_gateways
        ):
            self.gateway = self.discovered_gateways[user_input["id"]]
            await self.async_set_unique_id(self.gateway.id, raise_on_progress=False)
            # We pass user input to link so it will attempt to link right away
            return await self.async_step_test_connection()

        try:
            with async_timeout.timeout(5):
                local_gateways = await find_gateways()
        except asyncio.TimeoutError:
            return self.async_abort(reason="discovery_timeout")

        if not local_gateways:
            return self.async_abort(reason="no_gateways")

        # Find already configured hosts
        already_configured = self._async_current_ids(False)
        local_gateways = [gateway for gateway in local_gateways if gateway["serialNumber"] not in already_configured]

        if not local_gateways:
            return self.async_abort(reason="all_configured")

        if len(local_gateways) == 1:
            self.gateway = await OWNGateway.build_from_discovery_info(local_gateways[0])
            await self.async_set_unique_id(self.gateway.serial, raise_on_progress=False)
            return await self.async_step_test_connection()

        self.discovered_gateways = {gateway["serialNumber"]: gateway for gateway in local_gateways}

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("serial"): vol.In(
                        {gateway["serialNumber"]: gateway["address"] for gateway in local_gateways}
                    )
                }
            ),
            description_placeholders={
                CONF_HOST: self.context[CONF_HOST],
                CONF_NAME: self.context[CONF_NAME],
                CONF_MAC: self.context[CONF_MAC],
            },
        )

    async def async_step_test_connection(self):
        """Testing connection to the OWN Gateway.

        Given a configured gateway, will attempt to connect and negociate a
        dummy event session to validate all parameters.
        """

        gateway = self.gateway
        assert gateway is not None
        errors = {}

        self.context.update(
            {
                CONF_HOST: gateway.host,
                CONF_NAME: gateway.modelName,
                CONF_MAC: gateway.serial,
                "title_placeholders": {
                    CONF_HOST: gateway.host,
                    CONF_NAME: gateway.modelName,
                    CONF_MAC: gateway.serial,
                },
            }
        )

        test_session = OWNSession(gateway=gateway, logger=LOGGER)
        test_result = await test_session.test_connection()

        if test_result["Success"]:
            return self.async_create_entry(
                title=f"{gateway.modelName} Gateway",
                data={
                    CONF_ID: gateway.serial,
                    CONF_HOST: gateway.address,
                    CONF_PORT: gateway.port,
                    CONF_PASSWORD: gateway.password,
                    CONF_SSDP_LOCATION: gateway.ssdp_location,
                    CONF_SSDP_ST: gateway.ssdp_st,
                    CONF_DEVICE_TYPE: gateway.deviceType,
                    CONF_FRIENDLY_NAME: gateway.friendlyName,
                    CONF_MANUFACTURER: gateway.manufacturer,
                    CONF_MANUFACTURER_URL: gateway.manufacturerURL,
                    CONF_NAME: gateway.modelName,
                    CONF_FIRMWARE: gateway.modelNumber,
                    CONF_MAC: gateway.serial,
                    CONF_UDN: gateway.UDN,
                    CONF_LIGHTS: {},
                    CONF_COVERS: {},
                },
            )
        else:
            if test_result["Message"] == "password_required":
                return await self.async_step_password()
            elif test_result["Message"] == "password_error":
                errors["password"] = "password_error"
                return self.async_step_password(errors=errors)
            else:
                return self.async_abort(reason=test_result["Message"])

    async def async_step_port(self, user_input=None):
        """ Port information for the gateway is missing.

        Asking user to provide the port on which the gateway is listening.
        """
        errors = {}
        if user_input is not None:
            # Validate user input
            if 1 <= int(user_input["port"]) <= 65535:
                self.gateway.port = int(user_input["port"])
                return await self.async_step_test_connection()
            errors["port"] = "invalid_port"

        return self.async_show_form(
            step_id="port",
            data_schema=vol.Schema(
                {
                    vol.Required("port", description={"suggested_value": 20000}): int,
                }
            ),
            description_placeholders={
                CONF_HOST: self.context[CONF_HOST],
                CONF_NAME: self.context[CONF_NAME],
                CONF_MAC: self.context[CONF_MAC],
            },
            errors=errors
        )

    async def async_step_password(self, user_input=None, errors={}):
        """ Password is required to connect the gateway.

        Asking user to provide the gateway's password.
        """
        #errors = {}
        if user_input is not None:
            # Validate user input
            print(str(user_input["password"]))
            self.gateway.password = str(user_input["password"])
            return await self.async_step_test_connection()

        return self.async_show_form(
            step_id="password",
            data_schema=vol.Schema(
                {
                    vol.Required("password", description={"suggested_value": 12345}): str,
                }
            ),
            description_placeholders={
                CONF_HOST: self.context[CONF_HOST],
                CONF_NAME: self.context[CONF_NAME],
                CONF_MAC: self.context[CONF_MAC],
            },
            errors=errors
        )

    
    async def async_step_ssdp(self, discovery_info):
        """ Handle a discovered OpenWebNet gateway.

        This flow is triggered by the SSDP component. It will check if the
        gateway is already configured and if not, it will ask for the connection port
        if it has not been discovered on its own, and test the connection.
        """

        if "port" not in discovery_info:
            discovery_info["port"] = None
        
        gateway = await OWNGateway.build_from_discovery_info(discovery_info)
        await self.async_set_unique_id(gateway.id)
        LOGGER.info("Found gateway: %s", gateway.address)
        updatable = {CONF_HOST: gateway.address, CONF_NAME: gateway.modelName, CONF_FRIENDLY_NAME: gateway.friendlyName, CONF_ID: gateway.UDN, CONF_FIRMWARE: gateway.firmware}
        if gateway.port is not None:
            updatable[CONF_PORT] = gateway.port

        self._abort_if_unique_id_configured(updates=updatable)

        self.gateway = gateway

        if self.gateway.port is None:
            return await self.async_step_port()
        return await self.async_step_test_connection()