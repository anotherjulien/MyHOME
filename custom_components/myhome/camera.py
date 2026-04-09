"""Native MyHOME gateway camera entities."""

from __future__ import annotations

from datetime import datetime, timedelta
import httpx
from urllib.parse import urlencode

from homeassistant.components.camera import Camera, DOMAIN as PLATFORM
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME, CONF_PASSWORD
from homeassistant.helpers.httpx_client import get_async_client

from .const import (
    CONF_DEVICE_MODEL,
    CONF_ENTITIES,
    CONF_ENTITY,
    CONF_MANUFACTURER,
    CONF_PLATFORMS,
    CONF_WHERE,
    DOMAIN,
    LOGGER,
)

ATTR_FALLBACK_SNAPSHOT_PATHS = "fallback_snapshot_paths"
ATTR_FRAME_INTERVAL = "frame_interval"
ATTR_SNAPSHOT_PATH = "snapshot_path"
ATTR_VERIFY_SSL = "verify_ssl"

CAMERA_DEVICE_ID_PREFIX = "gateway-camera-"
DEFAULT_CAMERA_MODEL = "MyHOME Video Gateway Camera"
DEFAULT_FRAME_INTERVAL = 1.0
DEFAULT_SNAPSHOT_PATH = "JPEGgrab.cgi"
DEFAULT_VIDEO_CAMERA_NAME = "{model} Camera"
FALLBACK_SNAPSHOT_PATHS = ("JPEGgrab.cgi", "telecamera.php")
SUPPORTED_VIDEO_GATEWAY_MODELS = {"F453AV", "F454", "F455"}


def gateway_supports_camera(config_entry_data: dict) -> bool:
    """Return True if this gateway model can expose a native video snapshot."""
    model = str(config_entry_data.get(CONF_NAME, "") or "").upper()
    if model in SUPPORTED_VIDEO_GATEWAY_MODELS:
        return True

    udn = str(config_entry_data.get("UDN", "") or "").lower()
    return "webserver" in udn


def _default_camera_name(config_entry_data: dict) -> str:
    model = str(config_entry_data.get(CONF_NAME, "") or "MyHOME").strip() or "MyHOME"
    return DEFAULT_VIDEO_CAMERA_NAME.format(model=model)


def _gateway_camera_device_id(where: int | str = 0) -> str:
    return f"{CAMERA_DEVICE_ID_PREFIX}{int(where)}"


def _build_snapshot_url(host: str, snapshot_path: str, password: str | None = None) -> str:
    path = str(snapshot_path).lstrip("/")
    base_url = f"https://{host}/{path}"
    if not password:
        return base_url
    return f"{base_url}?{urlencode({'CAM_PASSWD': password})}"


def ensure_camera_platform_config(gateway_config: dict, config_entry_data: dict) -> None:
    """Inject the dynamic camera platform for supported MyHOME video gateways."""
    if not gateway_supports_camera(config_entry_data):
        return

    platform_config = gateway_config.setdefault(CONF_PLATFORMS, {}).setdefault(
        PLATFORM,
        {},
    )
    if platform_config:
        return

    device_id = _gateway_camera_device_id()
    device_config = platform_config.setdefault(
        device_id,
        {
            CONF_NAME: _default_camera_name(config_entry_data),
            CONF_WHERE: "0",
            CONF_HOST: config_entry_data[CONF_HOST],
            CONF_PASSWORD: config_entry_data.get(CONF_PASSWORD),
            ATTR_SNAPSHOT_PATH: DEFAULT_SNAPSHOT_PATH,
            ATTR_FALLBACK_SNAPSHOT_PATHS: list(FALLBACK_SNAPSHOT_PATHS),
            ATTR_VERIFY_SSL: False,
            ATTR_FRAME_INTERVAL: DEFAULT_FRAME_INTERVAL,
            CONF_MANUFACTURER: "BTicino S.p.A.",
            CONF_DEVICE_MODEL: (
                f"{config_entry_data.get(CONF_NAME) or DEFAULT_CAMERA_MODEL} Video Gateway"
            ),
            CONF_ENTITIES: {},
        },
    )

    device_config.setdefault(CONF_NAME, _default_camera_name(config_entry_data))
    device_config.setdefault(CONF_WHERE, "0")
    device_config[CONF_HOST] = config_entry_data[CONF_HOST]
    device_config[CONF_PASSWORD] = config_entry_data.get(CONF_PASSWORD)
    device_config.setdefault(ATTR_SNAPSHOT_PATH, DEFAULT_SNAPSHOT_PATH)
    device_config.setdefault(
        ATTR_FALLBACK_SNAPSHOT_PATHS,
        list(FALLBACK_SNAPSHOT_PATHS),
    )
    device_config.setdefault(ATTR_VERIFY_SSL, False)
    device_config.setdefault(ATTR_FRAME_INTERVAL, DEFAULT_FRAME_INTERVAL)
    device_config.setdefault(CONF_MANUFACTURER, "BTicino S.p.A.")
    device_config.setdefault(
        CONF_DEVICE_MODEL,
        f"{config_entry_data.get(CONF_NAME) or DEFAULT_CAMERA_MODEL} Video Gateway",
    )
    device_config.setdefault(CONF_ENTITIES, {})


async def async_setup_entry(hass, config_entry, async_add_entities):
    gateway_data = hass.data[DOMAIN][config_entry.data[CONF_MAC]]
    if PLATFORM not in gateway_data[CONF_PLATFORMS]:
        return True

    gateway_handler = gateway_data[CONF_ENTITY]
    gateway_entry_data = config_entry.data
    entities = []
    for device_id, device_config in gateway_data[CONF_PLATFORMS][PLATFORM].items():
        entities.append(
            MyHOMEGatewayCamera(
                hass=hass,
                gateway=gateway_handler,
                device_id=device_id,
                name=device_config.get(CONF_NAME),
                manufacturer=device_config.get(CONF_MANUFACTURER),
                model=device_config.get(CONF_DEVICE_MODEL),
                where=device_config.get(CONF_WHERE, "0"),
                host=device_config.get(CONF_HOST, gateway_entry_data[CONF_HOST]),
                password=device_config.get(
                    CONF_PASSWORD,
                    gateway_entry_data.get(CONF_PASSWORD),
                ),
                snapshot_path=device_config.get(ATTR_SNAPSHOT_PATH, DEFAULT_SNAPSHOT_PATH),
                fallback_snapshot_paths=device_config.get(
                    ATTR_FALLBACK_SNAPSHOT_PATHS,
                    list(FALLBACK_SNAPSHOT_PATHS),
                ),
                verify_ssl=bool(device_config.get(ATTR_VERIFY_SSL, False)),
                frame_interval=float(
                    device_config.get(ATTR_FRAME_INTERVAL, DEFAULT_FRAME_INTERVAL)
                ),
            )
        )

    if entities:
        async_add_entities(entities)
    return True


class MyHOMEGatewayCamera(Camera):
    """Expose the web snapshot of a MyHOME video gateway as a native camera."""

    def __init__(
        self,
        hass,
        gateway,
        device_id: str,
        name: str | None,
        manufacturer: str | None,
        model: str | None,
        where: int | str,
        host: str,
        password: str | None,
        snapshot_path: str,
        fallback_snapshot_paths: list[str] | tuple[str, ...],
        verify_ssl: bool,
        frame_interval: float,
    ) -> None:
        super().__init__()
        self.hass = hass
        self._hass = hass
        self._gateway_handler = gateway
        self._platform = PLATFORM
        self._device_id = device_id
        self._where = str(where)
        self._host = str(host)
        self._password = password
        self._verify_ssl = bool(verify_ssl)
        self._frame_interval = max(0.5, float(frame_interval))
        self._snapshot_path = str(snapshot_path).lstrip("/")
        self._fallback_snapshot_paths = [
            str(path).lstrip("/")
            for path in fallback_snapshot_paths
            if str(path).strip()
        ]

        if self._snapshot_path not in self._fallback_snapshot_paths:
            self._fallback_snapshot_paths.insert(0, self._snapshot_path)

        self._manufacturer = manufacturer or "BTicino S.p.A."
        self._model = model or DEFAULT_CAMERA_MODEL
        self._last_image: bytes | None = None
        self._last_update = datetime.min
        self._update_lock = None

        self._attr_has_entity_name = False
        self._attr_name = name or DEFAULT_VIDEO_CAMERA_NAME.format(model=gateway.model)
        self._attr_unique_id = f"{gateway.mac}-{device_id}"
        self._attr_should_poll = False
        self._attr_brand = self._manufacturer
        self._attr_model = self._model
        self._attr_frame_interval = self._frame_interval
        self._attr_available = True
        self.content_type = "image/jpeg"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{gateway.mac}-{device_id}")},
            "name": self._attr_name,
            "manufacturer": self._manufacturer,
            "model": self._model,
            "via_device": (DOMAIN, self._gateway_handler.unique_id),
        }
        self._attr_extra_state_attributes = {
            "gateway_host": self._host,
            "gateway_mac": self._gateway_handler.mac,
            "camera_where": int(self._where),
            "snapshot_path": self._snapshot_path,
            "verify_ssl": self._verify_ssl,
        }

    async def async_added_to_hass(self) -> None:
        self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
            self._platform
        ][self._device_id][CONF_ENTITIES][self._platform] = self

    async def async_will_remove_from_hass(self) -> None:
        if (
            self._platform
            in self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES]
        ):
            del self._hass.data[DOMAIN][self._gateway_handler.mac][CONF_PLATFORMS][
                self._platform
            ][self._device_id][CONF_ENTITIES][self._platform]

    async def async_camera_image(
        self,
        width: int | None = None,
        height: int | None = None,
    ) -> bytes | None:
        del width, height

        if (
            self._last_image is not None
            and datetime.now() - self._last_update < timedelta(seconds=self._frame_interval)
        ):
            return self._last_image

        if self._update_lock is None:
            import asyncio

            self._update_lock = asyncio.Lock()

        async with self._update_lock:
            if (
                self._last_image is not None
                and datetime.now() - self._last_update
                < timedelta(seconds=self._frame_interval)
            ):
                return self._last_image

            client = get_async_client(self._hass, verify_ssl=self._verify_ssl)
            last_error: Exception | None = None

            for snapshot_path in self._fallback_snapshot_paths:
                snapshot_url = _build_snapshot_url(
                    self._host,
                    snapshot_path,
                    self._password,
                )
                try:
                    response = await client.get(
                        snapshot_url,
                        follow_redirects=True,
                        timeout=10.0,
                    )
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    if "image" not in content_type.lower():
                        raise httpx.HTTPError(
                            f"Unexpected content type `{content_type}` for {snapshot_url}"
                        )

                    self._snapshot_path = snapshot_path
                    self._last_image = response.content
                    self._last_update = datetime.now()
                    self._attr_available = True
                    self._attr_extra_state_attributes.update(
                        {
                            "snapshot_path": self._snapshot_path,
                            "last_fetch": self._last_update.isoformat(),
                        }
                    )
                    return self._last_image
                except (httpx.RequestError, httpx.HTTPStatusError, httpx.TimeoutException) as err:
                    last_error = err
                    continue

            if self._last_image is None:
                self._attr_available = False
            if last_error is not None:
                LOGGER.debug(
                    "%s Camera snapshot fetch failed for `%s`: %s",
                    self._gateway_handler.log_id,
                    self._attr_name,
                    last_error,
                )
            return self._last_image
