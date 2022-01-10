"""Config flow to configure MyHome."""
import asyncio
from typing import Dict, Optional
import ipaddress
import re
import async_timeout
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
    CONN_CLASS_LOCAL_PUSH,
)
from homeassistant.core import callback
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_PASSWORD,
    CONF_NAME,
    CONF_MAC,
    CONF_ID,
    CONF_FRIENDLY_NAME,
)
from homeassistant.helpers import device_registry

from OWNd.connection import OWNSession, OWNGateway
from OWNd.discovery import find_gateways

from .const import (
    CONF_ADDRESS,
    CONF_OWN_PASSWORD,
    CONF_FIRMWARE,
    CONF_SSDP_LOCATION,
    CONF_SSDP_ST,
    CONF_DEVICE_TYPE,
    CONF_MANUFACTURER,
    CONF_MANUFACTURER_URL,
    CONF_UDN,
    CONF_WORKER_COUNT,
    DOMAIN,
    LOGGER,
)
from .gateway import MyHOMEGatewayHandler


class MACAddress:
    def __init__(self, mac: str):
        mac = re.sub("[.:-]", "", mac).upper()
        mac = "".join(mac.split())
        if len(mac) != 12 or not mac.isalnum() or re.search("[G-Z]", mac) is not None:
            raise ValueError("Invalid MAC address")
        self.mac = mac

    def __repr__(self) -> str:
        return ":".join(["%s" % (self.mac[i : i + 2]) for i in range(0, 12, 2)])

    def __str__(self) -> str:
        return ":".join(["%s" % (self.mac[i : i + 2]) for i in range(0, 12, 2)])


class MyhomeFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a MyHome config flow."""

    VERSION = 1
    CONNECTION_CLASS = CONN_CLASS_LOCAL_PUSH

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return MyhomeOptionsFlowHandler(config_entry)

    def __init__(self):
        """Initialize the MyHome flow."""
        self.gateway_handler: Optional[OWNGateway] = None
        self.discovered_gateways: Optional[Dict[str, OWNGateway]] = None
        self._existing_entry: ConfigEntry = None

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""

        # Check if user chooses manual entry
        if user_input is not None and user_input["serial"] == "00:00:00:00:00:00":
            return await self.async_step_custom()

        if (
            user_input is not None
            and self.discovered_gateways is not None
            and user_input["serial"] in self.discovered_gateways
        ):
            self.gateway_handler = await OWNGateway.build_from_discovery_info(
                self.discovered_gateways[user_input["serial"]]
            )
            await self.async_set_unique_id(
                device_registry.format_mac(self.gateway_handler.serial),
                raise_on_progress=False,
            )
            # We pass user input to link so it will attempt to link right away
            return await self.async_step_test_connection()

        try:
            with async_timeout.timeout(5):
                local_gateways = await find_gateways()
        except asyncio.TimeoutError:
            return self.async_abort(reason="discovery_timeout")

        # Find already configured hosts
        already_configured = self._async_current_ids(False)
        local_gateways = [
            gateway
            for gateway in local_gateways
            if gateway["serialNumber"] not in already_configured
        ]

        if not local_gateways:
            return self.async_abort(reason="all_configured")

        self.discovered_gateways = {
            gateway["serialNumber"]: gateway for gateway in local_gateways
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("serial"): vol.In(
                        {
                            **{
                                gateway[
                                    "serialNumber"
                                ]: f"{gateway['modelName']} Gateway ({gateway['address']})"
                                for gateway in local_gateways
                            },
                            "00:00:00:00:00:00": "Custom",
                        }
                    )
                }
            ),
        )

    async def async_step_custom(
        self, user_input=None, errors={}
    ):  # pylint: disable=dangerous-default-value
        """Handle manual gateway setup."""

        if user_input is not None:

            try:
                user_input["address"] = str(
                    ipaddress.IPv4Address(user_input["address"])
                )
            except ipaddress.AddressValueError:
                errors["address"] = "invalid_ip"

            try:
                user_input["serialNumber"] = device_registry.format_mac(
                    MACAddress(user_input["serialNumber"])
                )
            except ValueError:
                errors["serialNumber"] = "invalid_mac"

            if not errors:
                user_input["ssdp_location"] = (None,)
                user_input["ssdp_st"] = (None,)
                user_input["deviceType"] = (None,)
                user_input["friendlyName"] = (None,)
                user_input["manufacturer"] = ("BTicino S.p.A.",)
                user_input["manufacturerURL"] = ("http://www.bticino.it",)
                user_input["modelNumber"] = (None,)
                user_input["UDN"] = (None,)
                self.gateway_handler = OWNGateway(user_input)
                await self.async_set_unique_id(
                    user_input["serialNumber"], raise_on_progress=False
                )
                return await self.async_step_test_connection()

        address_suggestion = (
            user_input["address"]
            if user_input is not None and user_input["address"] is not None
            else "192.168.1.135"
        )
        port_suggestion = (
            user_input["port"]
            if user_input is not None and user_input["port"] is not None
            else 20000
        )
        serial_number_suggestion = (
            user_input["serialNumber"]
            if user_input is not None and user_input["serialNumber"] is not None
            else "00:03:50:00:00:00"
        )
        model_name_suggestion = (
            user_input["modelName"]
            if user_input is not None and user_input["modelName"] is not None
            else "F454"
        )

        return self.async_show_form(
            step_id="custom",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "address", description={"suggested_value": address_suggestion}
                    ): str,
                    vol.Required(
                        "port", description={"suggested_value": port_suggestion}
                    ): int,
                    vol.Required(
                        "serialNumber",
                        description={"suggested_value": serial_number_suggestion},
                    ): str,
                    vol.Required(
                        "modelName",
                        description={"suggested_value": model_name_suggestion},
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, config: dict = None):
        """Perform reauth upon an authentication error."""

        self._existing_entry = await self.async_set_unique_id(config[CONF_MAC])

        self.gateway_handler = MyHOMEGatewayHandler(
            hass=self.hass, config_entry=self._existing_entry
        ).gateway

        self.context.update(
            {
                CONF_HOST: self.gateway_handler.host,
                CONF_NAME: self.gateway_handler.model,
                CONF_MAC: self.gateway_handler.serial,
                "title_placeholders": {
                    CONF_HOST: self.gateway_handler.host,
                    CONF_NAME: self.gateway_handler.model,
                    CONF_MAC: self.gateway_handler.serial,
                },
            }
        )

        return await self.async_step_password(
            errors={CONF_OWN_PASSWORD: "password_error"}
        )

    async def async_step_test_connection(
        self, user_input=None, errors={}
    ):  # pylint: disable=unused-argument,dangerous-default-value
        """Testing connection to the OWN Gateway.

        Given a configured gateway, will attempt to connect and negociate a
        dummy event session to validate all parameters.
        """
        gateway = self.gateway_handler
        assert gateway is not None

        self.context.update(
            {
                CONF_HOST: gateway.host,
                CONF_NAME: gateway.model_name,
                CONF_MAC: gateway.serial,
                "title_placeholders": {
                    CONF_HOST: gateway.host,
                    CONF_NAME: gateway.model_name,
                    CONF_MAC: gateway.serial,
                },
            }
        )

        test_session = OWNSession(gateway=gateway, logger=LOGGER)
        test_result = await test_session.test_connection()

        if test_result["Success"]:
            _new_entry_data = {
                CONF_ID: device_registry.format_mac(gateway.serial),
                CONF_HOST: gateway.address,
                CONF_PORT: gateway.port,
                CONF_PASSWORD: gateway.password,
                CONF_SSDP_LOCATION: gateway.ssdp_location,
                CONF_SSDP_ST: gateway.ssdp_st,
                CONF_DEVICE_TYPE: gateway.device_type,
                CONF_FRIENDLY_NAME: gateway.friendly_name,
                CONF_MANUFACTURER: gateway.manufacturer,
                CONF_MANUFACTURER_URL: gateway.manufacturer_url,
                CONF_NAME: gateway.model_name,
                CONF_FIRMWARE: gateway.model_number,
                CONF_MAC: device_registry.format_mac(gateway.serial),
                CONF_UDN: gateway.udn,
            }
            _new_entry_options = {
                CONF_WORKER_COUNT: self._existing_entry.options[CONF_WORKER_COUNT]
                if self._existing_entry
                and CONF_WORKER_COUNT in self._existing_entry.options
                else 1,
            }

            if self._existing_entry:
                self.hass.config_entries.async_update_entry(
                    self._existing_entry,
                    data=_new_entry_data,
                    options=_new_entry_options,
                )
                await self.hass.config_entries.async_reload(
                    self._existing_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")
            else:
                return self.async_create_entry(
                    title=f"{gateway.model_name} Gateway",
                    data=_new_entry_data,
                    options=_new_entry_options,
                )
        else:
            if test_result["Message"] == "password_required":
                return await self.async_step_password()
            elif (
                test_result["Message"] == "password_error"
                or test_result["Message"] == "password_retry"
            ):
                errors["password"] = test_result["Message"]
                return await self.async_step_password(errors=errors)
            else:
                return self.async_abort(reason=test_result["Message"])

    async def async_step_port(
        self, user_input=None, errors={}
    ):  # pylint: disable=dangerous-default-value
        """Port information for the gateway is missing.

        Asking user to provide the port on which the gateway is listening.
        """
        if user_input is not None:
            # Validate user input
            if 1 <= int(user_input[CONF_PORT]) <= 65535:
                self.gateway_handler.port = int(user_input[CONF_PORT])
                return await self.async_step_test_connection()
            errors["port"] = "invalid_port"

        return self.async_show_form(
            step_id="port",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PORT, description={"suggested_value": 20000}
                    ): int,
                }
            ),
            description_placeholders={
                CONF_HOST: self.context[CONF_HOST],
                CONF_NAME: self.context[CONF_NAME],
                CONF_MAC: self.context[CONF_MAC],
            },
            errors=errors,
        )

    async def async_step_password(
        self, user_input=None, errors={}
    ):  # pylint: disable=dangerous-default-value
        """Password is required to connect the gateway.

        Asking user to provide the gateway's password.
        """
        if user_input is not None:
            # Validate user input
            self.gateway_handler.password = str(user_input[CONF_OWN_PASSWORD])
            return await self.async_step_test_connection()
        else:
            if self.gateway_handler.password is not None:
                _suggested_password = self.gateway_handler.password
            else:
                _suggested_password = 12345

        return self.async_show_form(
            step_id="password",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_OWN_PASSWORD,
                        description={"suggested_value": _suggested_password},
                    ): str,
                }
            ),
            description_placeholders={
                CONF_HOST: self.context[CONF_HOST],
                CONF_NAME: self.context[CONF_NAME],
                CONF_MAC: self.context[CONF_MAC],
            },
            errors=errors,
        )

    async def async_step_ssdp(self, discovery_info):
        """Handle a discovered OpenWebNet gateway.

        This flow is triggered by the SSDP component. It will check if the
        gateway is already configured and if not, it will ask for the connection port
        if it has not been discovered on its own, and test the connection.
        """

        _discovery_info = discovery_info.upnp
        _discovery_info["ssdp_st"] = discovery_info.ssdp_st
        _discovery_info["ssdp_location"] = discovery_info.ssdp_location
        _discovery_info["address"] = discovery_info.ssdp_headers["_host"]
        _discovery_info["port"] = 20000

        gateway = await OWNGateway.build_from_discovery_info(_discovery_info)
        await self.async_set_unique_id(device_registry.format_mac(gateway.unique_id))
        LOGGER.info("Found gateway: %s", gateway.address)
        updatable = {
            CONF_HOST: gateway.address,
            CONF_NAME: gateway.model_name,
            CONF_FRIENDLY_NAME: gateway.friendly_name,
            CONF_UDN: gateway.udn,
            CONF_FIRMWARE: gateway.firmware,
        }
        if gateway.port is not None:
            updatable[CONF_PORT] = gateway.port

        self._abort_if_unique_id_configured(updates=updatable)

        self.gateway_handler = gateway

        if self.gateway_handler.port is None:
            return await self.async_step_port()
        return await self.async_step_test_connection()


class MyhomeOptionsFlowHandler(OptionsFlow):
    """Handle MyHome options."""

    def __init__(self, config_entry):
        """Initialize MyHome options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)
        self.data = dict(config_entry.data)
        if CONF_WORKER_COUNT not in self.options:
            self.options[CONF_WORKER_COUNT] = 1

    async def async_step_init(self, user_input=None):  # pylint: disable=unused-argument
        """Manage the MyHome options."""
        return await self.async_step_user()

    async def async_step_user(
        self, user_input=None, errors={}
    ):  # pylint: disable=dangerous-default-value
        """Manage the MyHome devices options."""

        errors = {}

        if user_input is not None:
            if not 1 <= user_input[CONF_WORKER_COUNT] <= 10:
                errors[CONF_WORKER_COUNT] = "invalid_worker_count"

            self.options.update({CONF_WORKER_COUNT: user_input[CONF_WORKER_COUNT]})

            _data_update = not (
                self.data[CONF_HOST] == user_input[CONF_ADDRESS]
                and self.data[CONF_OWN_PASSWORD] == user_input[CONF_OWN_PASSWORD]
            )
            self.data.update({CONF_HOST: user_input[CONF_ADDRESS]})
            self.data.update({CONF_OWN_PASSWORD: user_input[CONF_OWN_PASSWORD]})

            try:
                self.data[CONF_HOST] = str(ipaddress.IPv4Address(self.data[CONF_HOST]))
            except ipaddress.AddressValueError:
                errors[CONF_ADDRESS] = "invalid_ip"

            if not errors:
                if _data_update:
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data=self.data
                    )
                    await self.hass.config_entries.async_reload(
                        self.config_entry.entry_id
                    )

                return self.async_create_entry(title="", data=self.options)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ADDRESS,
                        description={"suggested_value": self.data[CONF_HOST]},
                    ): str,
                    vol.Required(
                        CONF_OWN_PASSWORD,
                        description={"suggested_value": self.data[CONF_PASSWORD]},
                    ): str,
                    vol.Required(
                        CONF_WORKER_COUNT,
                        description={
                            "suggested_value": self.options[CONF_WORKER_COUNT]
                        },
                    ): int,
                }
            ),
            errors=errors,
        )
