"""Code to handle a MyHome Gateway."""
import asyncio
import re
from typing import Dict, List, Optional

from homeassistant.const import (
    CONF_ENTITIES,
    CONF_HOST,
    CONF_PORT,
    CONF_PASSWORD,
    CONF_NAME,
    CONF_MAC,
    CONF_FRIENDLY_NAME,
)
from homeassistant.components.light import DOMAIN as LIGHT
from homeassistant.components.switch import (
    SwitchDeviceClass,
    DOMAIN as SWITCH,
)
from homeassistant.components.button import DOMAIN as BUTTON
from homeassistant.components.cover import DOMAIN as COVER
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    DOMAIN as BINARY_SENSOR,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    DOMAIN as SENSOR,
)
from homeassistant.components.climate import DOMAIN as CLIMATE

from OWNd.connection import OWNSession, OWNEventSession, OWNCommandSession, OWNGateway
from OWNd.message import (
    OWNMessage,
    OWNScenarioEvent,
    OWNLightingEvent,
    OWNLightingCommand,
    OWNEnergyEvent,
    OWNAutomationEvent,
    OWNAlarmEvent,
    OWNDryContactEvent,
    OWNAuxEvent,
    OWNHeatingEvent,
    OWNHeatingCommand,
    OWNCENPlusEvent,
    OWNCENEvent,
    OWNSceneEvent,
    OWNGatewayEvent,
    OWNGatewayCommand,
    OWNCommand,
    OWNSignaling,
)

from .const import (
    CONF_PLATFORMS,
    CONF_FIRMWARE,
    CONF_SSDP_LOCATION,
    CONF_SSDP_ST,
    CONF_DEVICE_TYPE,
    CONF_MANUFACTURER,
    CONF_MANUFACTURER_URL,
    CONF_UDN,
    CONF_SHORT_PRESS,
    CONF_SHORT_RELEASE,
    CONF_LONG_PRESS,
    CONF_LONG_RELEASE,
    CONF_WHO,
    CONF_WHERE,
    DOMAIN,
    LOGGER,
)
from .myhome_device import MyHOMEEntity
from .button import (
    DisableCommandButtonEntity,
    EnableCommandButtonEntity,
)
from .audio import MyHOMEAudioState
from .alarm_request import parse_alarm_frame
from .gateway_info import build_gateway_event_payload
from .energy import EVENT_ENERGY, parse_energy_frame
from .light_management import (
    EVENT_LIGHT_MANAGEMENT,
    MyHOMELightManagementState,
    parse_light_management_frame,
)
from .thermo import EVENT_THERMO, MyHOMEThermoState


class _RawOWNMessage:
    """Wrap raw frames so entity handlers can safely inspect them."""

    def __init__(self, raw_message: str):
        self._raw_message = raw_message
        self.message_type = None

    def __str__(self) -> str:
        return self._raw_message


class MyHOMEGatewayHandler:
    """Manages a single MyHOME Gateway."""

    AUDIO_AREA_SOURCE_EVENT_RE = re.compile(r"^\*22\*(?:21|2)#(?P<mmtype>\d+)#(?P<area>\d+)\*5#2#(?P<source_id>\d+)##$")
    AUDIO_SPEAKER_STATE_EVENT_RE = re.compile(r"^\*#22\*3#(?P<area>\d+)#(?P<point>\d+)\*12\*(?P<device_state>\d+)\*(?P<mmtype>\d+)##$")
    AUDIO_SPEAKER_VOLUME_EVENT_RE = re.compile(r"^\*#22\*3#(?P<area>\d+)#(?P<point>\d+)\*1\*(?P<volume>\d+)\*?##$")
    AUDIO_SPEAKER_VOLUME_EVENT_ALT_RE = re.compile(r"^\*#16\*(?P<where>\d{2,3})\*1\*(?P<volume>\d+)\*?##$")
    AUDIO_SPEAKER_HIGH_TONES_EVENT_RE = re.compile(r"^\*#22\*3#(?P<area>\d+)#(?P<point>\d+)\*2\*(?P<value>\d+)##$")
    AUDIO_SPEAKER_MID_TONES_EVENT_RE = re.compile(r"^\*#22\*3#(?P<area>\d+)#(?P<point>\d+)\*3\*(?P<value>\d+)##$")
    AUDIO_SPEAKER_LOW_TONES_EVENT_RE = re.compile(r"^\*#22\*3#(?P<area>\d+)#(?P<point>\d+)\*4\*(?P<value>\d+)##$")
    AUDIO_SPEAKER_BALANCE_EVENT_RE = re.compile(r"^\*#22\*3#(?P<area>\d+)#(?P<point>\d+)\*17\*(?P<value>\d+)##$")
    AUDIO_SPEAKER_3D_EVENT_RE = re.compile(r"^\*#22\*3#(?P<area>\d+)#(?P<point>\d+)\*18\*(?P<value>\d+)##$")
    AUDIO_SPEAKER_PRESET_EVENT_RE = re.compile(r"^\*#22\*3#(?P<area>\d+)#(?P<point>\d+)\*19\*(?P<value>\d+)##$")
    AUDIO_SPEAKER_LOUDNESS_EVENT_RE = re.compile(r"^\*#22\*3#(?P<area>\d+)#(?P<point>\d+)\*20\*(?P<value>\d+)##$")
    AUDIO_SPEAKER_EQUALIZATION_EVENT_RE = re.compile(r"^\*#22\*5#3#(?P<area>\d+)#(?P<point>\d+)\*21#(?P<equalization>[1-3])\*(?P<bands>.+)##$")
    AUDIO_SOURCE_DEVICE_STATE_EVENT_RE = re.compile(r"^\*#22\*(?:5#2#|2#)(?P<source_id>\d+)\*12\*(?P<device_state>\d+)\*(?P<mmtype>\d+)##$")
    AUDIO_SOURCE_FREQUENCY_EVENT_RE = re.compile(r"^\*#22\*(?:5#2#|2#)(?P<source_id>\d+)\*5\*(?P<modulation>\d+)\*(?P<frequency>\d+)##$")
    AUDIO_SOURCE_STATION_EVENT_RE = re.compile(r"^\*#22\*(?:5#2#|2#)(?P<source_id>\d+)\*6\*(?P<station>\d+)##$")
    AUDIO_SOURCE_FREQUENCY_STATION_EVENT_RE = re.compile(r"^\*#22\*5#2#(?P<source_id>\d+)\*11\*(?P<modulation>\d+)\*(?P<frequency>\d+)\*(?P<station>\d+)##$")
    AUDIO_SOURCE_RDS_EVENT_RE = re.compile(r"^\*#22\*(?:5#2#|2#)(?P<source_id>\d+)\*10(?:\*(?P<segments>.*))?##$")

    AUDIO_SOURCE_COMMAND_RE = re.compile(r"^\*22\*35#(?P<mmtype>\d+)#(?P<area>\d+)#(?P<source_id>\d+)\*3#(?P=area)#(?P<point>\d+)##$")
    AUDIO_OFF_COMMAND_RE = re.compile(r"^\*22\*0#(?P<mmtype>\d+)#(?P<area>\d+)\*3#(?P=area)#(?P<point>\d+)##$")
    AUDIO_VOLUME_SET_COMMAND_RE = re.compile(r"^\*#22\*3#(?P<area>\d+)#(?P<point>\d+)\*#1\*(?P<volume>\d+)##$")
    AUDIO_VOLUME_UP_COMMAND_RE = re.compile(r"^\*22\*3#(?P<step>\d+)\*3#(?P<area>\d+)#(?P<point>\d+)##$")
    AUDIO_VOLUME_DOWN_COMMAND_RE = re.compile(r"^\*22\*4#(?P<step>\d+)\*3#(?P<area>\d+)#(?P<point>\d+)##$")
    LOAD_CONTROL_STATUS_REQUEST_RE = re.compile(r"^\*#18\*(?P<where>\d+)(?:#0)?\*(?P<dimension>\d+(?:#\d+)?)##$")
    LOAD_CONTROL_RAW_RESPONSE_RE = re.compile(r"^\*#18\*(?P<where>\d+)(?:#0)?\*")
    LOAD_CONTROL_RAW_DIMENSION_RE = re.compile(r"^\*#18\*(?P<where>\d+)(?:#0)?\*(?P<dimension>\d+(?:#\d+)?)\*")

    def __init__(self, hass, config_entry, generate_events=False):
        build_info = {
            "address": config_entry.data[CONF_HOST],
            "port": config_entry.data[CONF_PORT],
            "password": config_entry.data[CONF_PASSWORD],
            "ssdp_location": config_entry.data[CONF_SSDP_LOCATION],
            "ssdp_st": config_entry.data[CONF_SSDP_ST],
            "deviceType": config_entry.data[CONF_DEVICE_TYPE],
            "friendlyName": config_entry.data[CONF_FRIENDLY_NAME],
            "manufacturer": config_entry.data[CONF_MANUFACTURER],
            "manufacturerURL": config_entry.data[CONF_MANUFACTURER_URL],
            "modelName": config_entry.data[CONF_NAME],
            "modelNumber": config_entry.data[CONF_FIRMWARE],
            "serialNumber": config_entry.data[CONF_MAC],
            "UDN": config_entry.data[CONF_UDN],
        }
        self.hass = hass
        self.config_entry = config_entry
        self.generate_events = generate_events
        self.gateway = OWNGateway(build_info)
        self._terminate_listener = False
        self._terminate_sender = False
        self.is_connected = False
        self.listening_worker: asyncio.tasks.Task = None
        self.sending_workers: List[asyncio.tasks.Task] = []
        self.send_buffer = asyncio.Queue()
        self.active_sends = 0
        self.audio = MyHOMEAudioState()
        self.light_management = MyHOMELightManagementState()
        self.thermo = MyHOMEThermoState()

    @property
    def mac(self) -> str:
        return self.gateway.serial

    @property
    def unique_id(self) -> str:
        return self.mac

    @property
    def log_id(self) -> str:
        return self.gateway.log_id

    @property
    def manufacturer(self) -> str:
        return self.gateway.manufacturer

    @property
    def name(self) -> str:
        return f"{self.gateway.model_name} Gateway"

    @property
    def model(self) -> str:
        return self.gateway.model_name

    @property
    def firmware(self) -> str:
        return self.gateway.firmware

    @property
    def pending_messages(self) -> int:
        return self.send_buffer.qsize() + self.active_sends

    async def test(self) -> Dict:
        return await OWNSession(gateway=self.gateway, logger=LOGGER).test_connection()

    def _build_message_payload(self, message, is_status_request: bool | None = None) -> Dict:
        raw_message = None if message is None else str(message)
        payload = {
            "gateway": str(self.gateway.host),
            "raw_message": raw_message,
        }
        if is_status_request is not None:
            payload["is_status_request"] = is_status_request
        if isinstance(message, OWNMessage):
            try:
                payload.update(message.event_content)
            except Exception:  # pylint: disable=broad-except
                payload["message"] = raw_message
        elif raw_message is not None:
            payload["message"] = raw_message
        return payload

    def _parse_audio_feedback(self, raw_message: Optional[str]) -> Optional[Dict]:
        if not raw_message:
            return None

        match = self.AUDIO_AREA_SOURCE_EVENT_RE.match(raw_message)
        if match:
            return {
                "kind": "area_source",
                "area": int(match.group("area")),
                "source_id": int(match.group("source_id")),
                "mmtype": int(match.group("mmtype")),
            }

        match = self.AUDIO_SPEAKER_STATE_EVENT_RE.match(raw_message)
        if match:
            area = int(match.group("area"))
            point = int(match.group("point"))
            return {
                "kind": "speaker_state",
                "area": area,
                "point": point,
                "zone_key": f"{area}_{point}",
                "on_state": "off" if int(match.group("device_state")) == 0 else "on",
                "device_state": int(match.group("device_state")),
                "mmtype": int(match.group("mmtype")),
            }

        match = self.AUDIO_SPEAKER_VOLUME_EVENT_RE.match(raw_message)
        if match:
            area = int(match.group("area"))
            point = int(match.group("point"))
            return {
                "kind": "speaker_volume",
                "area": area,
                "point": point,
                "zone_key": f"{area}_{point}",
                "volume": int(match.group("volume")),
            }

        match = self.AUDIO_SPEAKER_VOLUME_EVENT_ALT_RE.match(raw_message)
        if match:
            where = match.group("where")
            if len(where) < 2:
                return None
            area = int(where[:-1])
            point = int(where[-1])
            return {
                "kind": "speaker_volume",
                "area": area,
                "point": point,
                "zone_key": f"{area}_{point}",
                "volume": int(match.group("volume")),
                "legacy": True,
            }

        for pattern, kind in (
            (self.AUDIO_SPEAKER_HIGH_TONES_EVENT_RE, "speaker_high_tones"),
            (self.AUDIO_SPEAKER_MID_TONES_EVENT_RE, "speaker_mid_tones"),
            (self.AUDIO_SPEAKER_LOW_TONES_EVENT_RE, "speaker_low_tones"),
            (self.AUDIO_SPEAKER_BALANCE_EVENT_RE, "speaker_balance"),
            (self.AUDIO_SPEAKER_3D_EVENT_RE, "speaker_3d"),
            (self.AUDIO_SPEAKER_PRESET_EVENT_RE, "speaker_preset"),
            (self.AUDIO_SPEAKER_LOUDNESS_EVENT_RE, "speaker_loudness"),
        ):
            match = pattern.match(raw_message)
            if match:
                area = int(match.group("area"))
                point = int(match.group("point"))
                return {
                    "kind": kind,
                    "area": area,
                    "point": point,
                    "zone_key": f"{area}_{point}",
                    "value": int(match.group("value")),
                }

        match = self.AUDIO_SPEAKER_EQUALIZATION_EVENT_RE.match(raw_message)
        if match:
            area = int(match.group("area"))
            point = int(match.group("point"))
            bands = [segment for segment in match.group("bands").split("*") if segment != ""]
            return {
                "kind": "speaker_equalization",
                "area": area,
                "point": point,
                "zone_key": f"{area}_{point}",
                "equalization": int(match.group("equalization")),
                "bands": bands,
            }

        match = self.AUDIO_SOURCE_DEVICE_STATE_EVENT_RE.match(raw_message)
        if match:
            return {
                "kind": "source_device_state",
                "source_id": int(match.group("source_id")),
                "device_state": int(match.group("device_state")),
                "mmtype": int(match.group("mmtype")),
            }


        match = self.AUDIO_SOURCE_FREQUENCY_STATION_EVENT_RE.match(raw_message)
        if match:
            return {
                "kind": "source_frequency_station",
                "source_id": int(match.group("source_id")),
                "modulation": int(match.group("modulation")),
                "frequency": int(match.group("frequency")),
                "station": int(match.group("station")),
            }

        match = self.AUDIO_SOURCE_FREQUENCY_EVENT_RE.match(raw_message)
        if match:
            return {
                "kind": "source_frequency",
                "source_id": int(match.group("source_id")),
                "modulation": int(match.group("modulation")),
                "frequency": int(match.group("frequency")),
            }

        match = self.AUDIO_SOURCE_STATION_EVENT_RE.match(raw_message)
        if match:
            return {
                "kind": "source_station",
                "source_id": int(match.group("source_id")),
                "station": int(match.group("station")),
            }

        match = self.AUDIO_SOURCE_RDS_EVENT_RE.match(raw_message)
        if match:
            segments = [
                segment for segment in (match.group("segments") or "").split("*")
                if segment != ""
            ]
            return {
                "kind": "source_rds",
                "source_id": int(match.group("source_id")),
                "segments": segments,
                "text": " ".join(segments) if segments else None,
            }
        return None

    def _parse_audio_command(self, raw_message: Optional[str]) -> Optional[Dict]:
        if not raw_message:
            return None

        match = self.AUDIO_SOURCE_COMMAND_RE.match(raw_message)
        if match:
            area = int(match.group("area"))
            point = int(match.group("point"))
            return {
                "kind": "audio_source_command",
                "area": area,
                "point": point,
                "zone_key": f"{area}_{point}",
                "source_id": int(match.group("source_id")),
                "mmtype": int(match.group("mmtype")),
            }

        match = self.AUDIO_OFF_COMMAND_RE.match(raw_message)
        if match:
            area = int(match.group("area"))
            point = int(match.group("point"))
            return {
                "kind": "audio_off_command",
                "area": area,
                "point": point,
                "zone_key": f"{area}_{point}",
                "mmtype": int(match.group("mmtype")),
            }

        match = self.AUDIO_VOLUME_SET_COMMAND_RE.match(raw_message)
        if match:
            area = int(match.group("area"))
            point = int(match.group("point"))
            return {
                "kind": "audio_volume_set",
                "area": area,
                "point": point,
                "zone_key": f"{area}_{point}",
                "volume": int(match.group("volume")),
            }

        match = self.AUDIO_VOLUME_UP_COMMAND_RE.match(raw_message)
        if match:
            area = int(match.group("area"))
            point = int(match.group("point"))
            return {
                "kind": "audio_volume_up",
                "area": area,
                "point": point,
                "zone_key": f"{area}_{point}",
                "step": int(match.group("step")),
            }

        match = self.AUDIO_VOLUME_DOWN_COMMAND_RE.match(raw_message)
        if match:
            area = int(match.group("area"))
            point = int(match.group("point"))
            return {
                "kind": "audio_volume_down",
                "area": area,
                "point": point,
                "zone_key": f"{area}_{point}",
                "step": int(match.group("step")),
            }

        return None

    def _dispatch_raw_load_control_message(self, message) -> bool:
        """Dispatch raw WHO=18 responses not parsed by OWNd."""
        raw_message = str(message).strip()
        match = self.LOAD_CONTROL_RAW_RESPONSE_RE.match(raw_message)
        if match is None:
            return False

        where = match.group("where")
        handled = False

        for platform, platform_entities in self.hass.data[DOMAIN][self.mac][
            CONF_PLATFORMS
        ].items():
            if platform == BUTTON:
                continue

            for device_config in platform_entities.values():
                if not isinstance(device_config, dict):
                    continue
                if (
                    device_config.get(CONF_WHO) != "18"
                    or device_config.get(CONF_WHERE) != where
                ):
                    continue

                for entity in device_config.get(CONF_ENTITIES, {}).values():
                    if isinstance(entity, MyHOMEEntity) and hasattr(
                        entity, "handle_event"
                    ):
                        entity.handle_event(message)
                        handled = True

        return handled

    def _get_expected_status_response(self, message: OWNCommand | str) -> Optional[Dict[str, str]]:
        """Return the expected WHO=18 response signature for a status request."""
        match = self.LOAD_CONTROL_STATUS_REQUEST_RE.match(str(message).strip())
        if match is None:
            return None
        return {
            "where": match.group("where"),
            "dimension": match.group("dimension"),
        }

    def _matches_expected_status_response(
        self,
        message: OWNMessage | _RawOWNMessage,
        expected_response: Dict[str, str] | None,
    ) -> bool:
        """Check whether a response frame matches the WHO=18 request just sent."""
        if expected_response is None:
            return True

        match = self.LOAD_CONTROL_RAW_DIMENSION_RE.match(str(message).strip())
        if match is None:
            return False

        return (
            match.group("where") == expected_response["where"]
            and match.group("dimension") == expected_response["dimension"]
        )

    def _parse_incoming_frame(self, raw_message: str):
        """Parse a frame without letting OWNd parser exceptions break the session."""
        try:
            resulting_message = OWNMessage.parse(raw_message)
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.debug(
                "%s Could not parse frame `%s`: %s",
                self.log_id,
                raw_message,
                err,
            )
            return _RawOWNMessage(raw_message)

        if resulting_message is None or isinstance(resulting_message, str):
            return _RawOWNMessage(raw_message)

        return resulting_message

    async def _drain_command_session(self, command_session: OWNCommandSession) -> int:
        """Dispatch any late frames still queued on the command session."""
        drained = 0
        timeout = 0.12

        while True:
            try:
                raw_response = await asyncio.wait_for(
                    command_session._stream_reader.readuntil(OWNSession.SEPARATOR),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                break

            timeout = 0.02
            raw_response_text = raw_response.decode(errors="ignore").strip()
            resulting_message = self._parse_incoming_frame(raw_response_text)

            if isinstance(resulting_message, OWNSignaling):
                drained += 1
                continue

            LOGGER.debug(
                "%s Draining late command-session frame `%s` before a new request.",
                self.log_id,
                resulting_message,
            )
            await self._handle_incoming_message(resulting_message)
            drained += 1

        return drained

    async def _handle_incoming_message(self, message):
        LOGGER.debug("%s Message received: `%s`", self.log_id, message)

        raw_message = str(message).strip()
        _event_payload = self._build_message_payload(message)
        self.hass.bus.async_fire("myhome_raw_message_event", _event_payload)

        _thermo_update = self.thermo.handle_message(raw_message)
        if _thermo_update is not None:
            _thermo_update["gateway"] = str(self.gateway.host)
            _thermo_update["gateway_mac"] = self.mac
            self.hass.bus.async_fire(EVENT_THERMO, _thermo_update)

        _audio_feedback = self._parse_audio_feedback(_event_payload.get("raw_message"))
        if _audio_feedback is not None:
            self.audio.handle_feedback(_audio_feedback)
            _audio_feedback["gateway"] = str(self.gateway.host)
            _audio_feedback["gateway_mac"] = self.mac
            _audio_feedback["raw_message"] = _event_payload.get("raw_message")
            self.hass.bus.async_fire("myhome_audio_feedback_event", _audio_feedback)

        if self.generate_events:
            self.hass.bus.async_fire("myhome_message_event", _event_payload)

        if not isinstance(message, OWNMessage):
            if (
                raw_message.startswith("*#22*")
                or raw_message.startswith("*22*")
                or raw_message.startswith("*#16*")
                or raw_message.startswith("*16*")
            ):
                LOGGER.debug(
                    "%s Known raw frame received: `%s`",
                    self.log_id,
                    raw_message,
                )
                return

            if self._dispatch_raw_load_control_message(message):
                LOGGER.debug(
                    "%s Dispatched raw load-control frame `%s`.",
                    self.log_id,
                    raw_message,
                )
                return

            _energy_update = parse_energy_frame(raw_message)
            if _energy_update is not None:
                _energy_update["gateway"] = str(self.gateway.host)
                _energy_update["gateway_mac"] = self.mac
                _energy_update["raw_message"] = raw_message
                self.hass.bus.async_fire(EVENT_ENERGY, _energy_update)
                LOGGER.debug(
                    "%s Dispatched raw energy frame `%s`.",
                    self.log_id,
                    raw_message,
                )
                return

            _light_management_update = parse_light_management_frame(raw_message)
            if _light_management_update is not None:
                self.light_management.handle_feedback(_light_management_update)
                _light_management_update["gateway"] = str(self.gateway.host)
                _light_management_update["gateway_mac"] = self.mac
                _light_management_update["raw_message"] = raw_message
                self.hass.bus.async_fire(
                    EVENT_LIGHT_MANAGEMENT,
                    _light_management_update,
                )
                LOGGER.debug(
                    "%s Dispatched raw lighting-management frame `%s`.",
                    self.log_id,
                    raw_message,
                )
                return

            if _thermo_update is not None:
                LOGGER.debug(
                    "%s Dispatched raw thermo frame `%s`.",
                    self.log_id,
                    raw_message,
                )
                return

            LOGGER.warning(
                "%s Data received is not a message: `%s`",
                self.log_id,
                raw_message,
            )
        elif isinstance(message, OWNEnergyEvent):
            _handled = False
            for _platform in self.hass.data[DOMAIN][self.mac][CONF_PLATFORMS]:
                if _platform == BUTTON:
                    continue
                if message.entity not in self.hass.data[DOMAIN][self.mac][CONF_PLATFORMS][_platform]:
                    continue
                _handled = True
                for _entity in self.hass.data[DOMAIN][self.mac][CONF_PLATFORMS][
                    _platform
                ][message.entity][CONF_ENTITIES].values():
                    if isinstance(_entity, MyHOMEEntity) and hasattr(
                        _entity,
                        "handle_event",
                    ):
                        _entity.handle_event(message)
            if not _handled:
                return
        elif (
            isinstance(message, OWNLightingEvent)
            or isinstance(message, OWNAutomationEvent)
            or isinstance(message, OWNDryContactEvent)
            or isinstance(message, OWNAuxEvent)
            or isinstance(message, OWNHeatingEvent)
        ):
            if not message.is_translation:
                is_event = False
                if isinstance(message, OWNLightingEvent):
                    if message.is_general:
                        is_event = True
                        event = "on" if message.is_on else "off"
                        self.hass.bus.async_fire(
                            "myhome_general_light_event",
                            {"message": str(message), "event": event},
                        )
                        await asyncio.sleep(0.1)
                        await self.send_status_request(OWNLightingCommand.status("0"))
                    elif message.is_area:
                        is_event = True
                        event = "on" if message.is_on else "off"
                        self.hass.bus.async_fire(
                            "myhome_area_light_event",
                            {
                                "message": str(message),
                                "area": message.area,
                                "event": event,
                            },
                        )
                        await asyncio.sleep(0.1)
                        await self.send_status_request(OWNLightingCommand.status(message.area))
                    elif message.is_group:
                        is_event = True
                        event = "on" if message.is_on else "off"
                        self.hass.bus.async_fire(
                            "myhome_group_light_event",
                            {
                                "message": str(message),
                                "group": message.group,
                                "event": event,
                            },
                        )
                elif isinstance(message, OWNAutomationEvent):
                    if message.is_general:
                        is_event = True
                        if message.is_opening and not message.is_closing:
                            event = "open"
                        elif message.is_closing and not message.is_opening:
                            event = "close"
                        else:
                            event = "stop"
                        self.hass.bus.async_fire(
                            "myhome_general_automation_event",
                            {"message": str(message), "event": event},
                        )
                    elif message.is_area:
                        is_event = True
                        if message.is_opening and not message.is_closing:
                            event = "open"
                        elif message.is_closing and not message.is_opening:
                            event = "close"
                        else:
                            event = "stop"
                        self.hass.bus.async_fire(
                            "myhome_area_automation_event",
                            {
                                "message": str(message),
                                "area": message.area,
                                "event": event,
                            },
                        )
                    elif message.is_group:
                        is_event = True
                        if message.is_opening and not message.is_closing:
                            event = "open"
                        elif message.is_closing and not message.is_opening:
                            event = "close"
                        else:
                            event = "stop"
                        self.hass.bus.async_fire(
                            "myhome_group_automation_event",
                            {
                                "message": str(message),
                                "group": message.group,
                                "event": event,
                            },
                        )
                if not is_event:
                    if isinstance(message, OWNLightingEvent) and message.brightness_preset:
                        if isinstance(
                            self.hass.data[DOMAIN][self.mac][CONF_PLATFORMS][LIGHT][message.entity][CONF_ENTITIES][LIGHT],
                            MyHOMEEntity,
                        ):
                            await self.hass.data[DOMAIN][self.mac][CONF_PLATFORMS][LIGHT][message.entity][CONF_ENTITIES][LIGHT].async_update()
                    else:
                        for _platform in self.hass.data[DOMAIN][self.mac][CONF_PLATFORMS]:
                            if _platform != BUTTON and message.entity in self.hass.data[DOMAIN][self.mac][CONF_PLATFORMS][_platform]:
                                for _entity in self.hass.data[DOMAIN][self.mac][
                                    CONF_PLATFORMS
                                ][_platform][message.entity][CONF_ENTITIES].values():
                                    if (
                                        isinstance(_entity, MyHOMEEntity)
                                        and hasattr(_entity, "handle_event")
                                        and not isinstance(
                                            _entity,
                                            DisableCommandButtonEntity,
                                        )
                                        and not isinstance(
                                            _entity,
                                            EnableCommandButtonEntity,
                                        )
                                    ):
                                        _entity.handle_event(message)

            else:
                LOGGER.debug(
                    "%s Ignoring translation message `%s`",
                    self.log_id,
                    message,
                )
        elif isinstance(message, OWNHeatingCommand) and message.dimension is not None and message.dimension == 14:
            where = message.where[1:] if message.where.startswith("#") else message.where
            LOGGER.debug(
                "%s Received heating command, sending query to zone %s",
                self.log_id,
                where,
            )
            await self.send_status_request(OWNHeatingCommand.status(where))
        elif isinstance(message, OWNCENPlusEvent):
            event = None
            if message.is_short_pressed:
                event = CONF_SHORT_PRESS
            elif message.is_held or message.is_still_held:
                event = CONF_LONG_PRESS
            elif message.is_released:
                event = CONF_LONG_RELEASE
            else:
                event = None
            self.hass.bus.async_fire(
                "myhome_cenplus_event",
                {
                    "gateway_mac": self.mac,
                    "object": int(message.object),
                    "pushbutton": int(message.push_button),
                    "event": event,
                },
            )
            LOGGER.info(
                "%s %s",
                self.log_id,
                message.human_readable_log,
            )
        elif isinstance(message, OWNCENEvent):
            event = None
            if message.is_pressed:
                event = CONF_SHORT_PRESS
            elif message.is_released_after_short_press:
                event = CONF_SHORT_RELEASE
            elif message.is_held:
                event = CONF_LONG_PRESS
            elif message.is_released_after_long_press:
                event = CONF_LONG_RELEASE
            else:
                event = None
            self.hass.bus.async_fire(
                "myhome_cen_event",
                {
                    "gateway_mac": self.mac,
                    "object": int(message.object),
                    "pushbutton": int(message.push_button),
                    "event": event,
                },
            )
            LOGGER.info(
                "%s %s",
                self.log_id,
                message.human_readable_log,
            )
        elif isinstance(message, OWNScenarioEvent):
            self.hass.bus.async_fire(
                "myhome_scenario_event",
                {
                    "gateway_mac": self.mac,
                    "scenario": int(message.scenario),
                    "control_panel": int(message.control_panel),
                },
            )
            LOGGER.info(
                "%s %s",
                self.log_id,
                message.human_readable_log,
            )
        elif isinstance(message, OWNSceneEvent):
            self.hass.bus.async_fire(
                "myhome_scene_event",
                {
                    "gateway_mac": self.mac,
                    "scene": int(message.scenario),
                    "state": int(message.state),
                    "is_on": message.is_on,
                    "is_enabled": message.is_enabled,
                },
            )
            LOGGER.info(
                "%s %s",
                self.log_id,
                message.human_readable_log,
            )
        elif isinstance(message, OWNAlarmEvent):
            self.hass.bus.async_fire(
                "myhome_alarm_event",
                {
                    "gateway_mac": self.mac,
                    "state_code": getattr(message, "_state_code", None),
                    "state_name": getattr(message, "_state", None),
                    "general": message.general,
                    "zone": message.zone,
                    "sensor": message.sensor,
                    "is_alarm": message.is_alarm,
                    "is_active": message.is_active,
                    "is_engaged": message.is_engaged,
                    "message": str(message),
                },
            )
            LOGGER.info(
                "%s %s",
                self.log_id,
                message.human_readable_log,
            )
        elif isinstance(message, _RawOWNMessage):
            alarm_payload = parse_alarm_frame(str(message))
            if alarm_payload is not None and alarm_payload.get("kind") == "alarm":
                alarm_payload.update(
                    {
                        "gateway_mac": self.mac,
                        "message": str(message),
                    }
                )
                self.hass.bus.async_fire("myhome_alarm_event", alarm_payload)
            LOGGER.info(
                "%s Unsupported message type: `%s`",
                self.log_id,
                message,
            )
        elif isinstance(message, OWNGatewayEvent) or isinstance(message, OWNGatewayCommand):
            payload = build_gateway_event_payload(message)
            if payload is not None:
                payload["gateway_mac"] = self.mac
                payload["gateway"] = str(self.gateway.host)
                payload["message"] = str(message)
                self.hass.bus.async_fire("myhome_gateway_event", payload)
            LOGGER.info(
                "%s %s",
                self.log_id,
                message.human_readable_log,
            )
        else:
            LOGGER.info(
                "%s Unsupported message type: `%s`",
                self.log_id,
                message,
            )

    async def _send_status_request_and_dispatch(self, command_session: OWNCommandSession, message: OWNCommand | str):
        """Send a status request and dispatch any direct reply read on the command session."""
        raw_message = str(message)
        expected_response = self._get_expected_status_response(message)
        attempts = 2 if expected_response is not None else 1

        try:
            for attempt in range(1, attempts + 1):
                drained = await self._drain_command_session(command_session)
                if drained:
                    LOGGER.debug(
                        "%s Drained %s pending frame(s) before status request `%s` attempt %s.",
                        self.log_id,
                        drained,
                        message,
                        attempt,
                    )

                command_session._stream_writer.write(raw_message.encode())
                await command_session._stream_writer.drain()

                saw_ack = False
                matched_expected_response = expected_response is None
                deadline = self.hass.loop.time() + 3
                while True:
                    timeout = deadline - self.hass.loop.time()
                    if timeout <= 0:
                        break
                    try:
                        raw_response = await asyncio.wait_for(
                            command_session._stream_reader.readuntil(OWNSession.SEPARATOR),
                            timeout=timeout,
                        )
                    except asyncio.TimeoutError:
                        break

                    raw_response_text = raw_response.decode(errors="ignore").strip()
                    resulting_message = self._parse_incoming_frame(raw_response_text)
                    if isinstance(resulting_message, OWNSignaling):
                        if resulting_message.is_nack():
                            LOGGER.error(
                                "%s Could not send message `%s`.",
                                self.log_id,
                                message,
                            )
                            return False
                        if resulting_message.is_ack():
                            saw_ack = True
                            deadline = self.hass.loop.time() + 0.8
                            continue
                        continue

                    if isinstance(resulting_message, _RawOWNMessage):
                        LOGGER.debug(
                            "%s Status request `%s` returned unparsed response `%s`.",
                            self.log_id,
                            message,
                            resulting_message,
                        )
                    else:
                        LOGGER.debug(
                            "%s Status request `%s` received direct response `%s`.",
                            self.log_id,
                            message,
                            resulting_message,
                        )

                    await self._handle_incoming_message(resulting_message)
                    if self._matches_expected_status_response(
                        resulting_message,
                        expected_response,
                    ):
                        matched_expected_response = True
                        deadline = self.hass.loop.time() + 0.2
                    else:
                        deadline = self.hass.loop.time() + 0.8

                if matched_expected_response:
                    if saw_ack:
                        LOGGER.debug(
                            "%s Message `%s` was successfully sent.",
                            self.log_id,
                            message,
                        )
                    return True

                LOGGER.debug(
                    "%s Status request `%s` did not receive the expected WHO=18 response on attempt %s/%s.",
                    self.log_id,
                    message,
                    attempt,
                    attempts,
                )
                if attempt < attempts:
                    await asyncio.sleep(0.15)
            return False
        except (ConnectionResetError, asyncio.IncompleteReadError):
            LOGGER.debug(
                "%s Command session connection reset during status request, retrying...",
                self.log_id,
            )
            await command_session.connect()
            return await self._send_status_request_and_dispatch(
                command_session,
                message,
            )
        except Exception:  # pylint: disable=broad-except
            LOGGER.exception("%s Command session crashed during status request.", self.log_id)
            return False

    async def listening_loop(self):
        self._terminate_listener = False

        LOGGER.debug("%s Creating listening worker.", self.log_id)

        _event_session = OWNEventSession(gateway=self.gateway, logger=LOGGER)
        await _event_session.connect()
        self.is_connected = True

        while not self._terminate_listener:
            try:
                message = await _event_session.get_next()
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception(
                    "%s Event session failed while parsing an incoming frame.",
                    self.log_id,
                )
                await asyncio.sleep(0.1)
                continue
            await self._handle_incoming_message(message)

        await _event_session.close()
        self.is_connected = False

        LOGGER.debug("%s Destroying listening worker.", self.log_id)
        self.listening_worker.cancel()

    async def sending_loop(self, worker_id: int):
        self._terminate_sender = False

        LOGGER.debug(
            "%s Creating sending worker %s",
            self.log_id,
            worker_id,
        )

        _command_session = OWNCommandSession(gateway=self.gateway, logger=LOGGER)
        await _command_session.connect()

        while not self._terminate_sender:
            task = await self.send_buffer.get()
            self.active_sends += 1
            LOGGER.debug(
                "%s Message `%s` was successfully unqueued by worker %s.",
                self.log_id,
                task["message"],
                worker_id,
            )
            try:
                result = False
                if task["is_status_request"]:
                    result = await self._send_status_request_and_dispatch(
                        _command_session,
                        task["message"],
                    )
                else:
                    await _command_session.send(
                        message=task["message"],
                        is_status_request=task["is_status_request"],
                    )
                    result = True
                if task.get("done_future") is not None and not task["done_future"].done():
                    task["done_future"].set_result(result)
            finally:
                self.active_sends = max(0, self.active_sends - 1)
                self.send_buffer.task_done()

        await _command_session.close()

        LOGGER.debug(
            "%s Destroying sending worker %s",
            self.log_id,
            worker_id,
        )
        self.sending_workers[worker_id].cancel()

    async def close_listener(self) -> bool:
        LOGGER.info("%s Closing event listener", self.log_id)
        self._terminate_sender = True
        self._terminate_listener = True

        return True

    async def send(self, message: OWNCommand | str):
        payload = self._build_message_payload(message, is_status_request=False)
        self.hass.bus.async_fire("myhome_command_sent_event", payload)
        _audio_command = self._parse_audio_command(payload.get("raw_message"))
        if _audio_command is not None:
            self.audio.handle_command(_audio_command)
            _audio_command["gateway"] = str(self.gateway.host)
            _audio_command["gateway_mac"] = self.mac
            _audio_command["raw_message"] = payload.get("raw_message")
            self.hass.bus.async_fire("myhome_audio_command_event", _audio_command)
        await self.send_buffer.put({"message": message, "is_status_request": False})
        LOGGER.debug(
            "%s Message `%s` was successfully queued.",
            self.log_id,
            message,
        )

    async def send_status_request(
        self,
        message: OWNCommand,
        wait_for_completion: bool = False,
    ):
        payload = self._build_message_payload(message, is_status_request=True)
        self.hass.bus.async_fire("myhome_command_sent_event", payload)
        done_future = (
            self.hass.loop.create_future() if wait_for_completion else None
        )
        await self.send_buffer.put(
            {
                "message": message,
                "is_status_request": True,
                "done_future": done_future,
            }
        )
        LOGGER.debug(
            "%s Message `%s` was successfully queued.",
            self.log_id,
            message,
        )
        if done_future is not None:
            return await done_future

    async def send_status_request_collect(
        self,
        message: OWNCommand | str,
        *,
        timeout: float = 3.0,
    ) -> dict:
        """Send a read-only request, dispatch replies, and collect raw frames."""
        command_session = OWNCommandSession(gateway=self.gateway, logger=LOGGER)
        raw_frames: list[str] = []
        payload = self._build_message_payload(message, is_status_request=True)
        self.hass.bus.async_fire("myhome_command_sent_event", payload)

        try:
            await command_session.connect()
            raw_message = str(message)
            expected_response = self._get_expected_status_response(message)
            attempts = 2 if expected_response is not None else 1

            for attempt in range(1, attempts + 1):
                await self._drain_command_session(command_session)
                command_session._stream_writer.write(raw_message.encode())
                await command_session._stream_writer.drain()

                saw_ack = False
                matched_expected_response = expected_response is None
                deadline = self.hass.loop.time() + timeout

                while True:
                    remaining = deadline - self.hass.loop.time()
                    if remaining <= 0:
                        break
                    try:
                        raw_response = await asyncio.wait_for(
                            command_session._stream_reader.readuntil(
                                OWNSession.SEPARATOR
                            ),
                            timeout=remaining,
                        )
                    except asyncio.TimeoutError:
                        break

                    raw_response_text = raw_response.decode(errors="ignore").strip()
                    resulting_message = self._parse_incoming_frame(raw_response_text)

                    if isinstance(resulting_message, OWNSignaling):
                        if resulting_message.is_nack():
                            return {
                                "success": False,
                                "acknowledged": False,
                                "raw_frames": raw_frames,
                            }
                        if resulting_message.is_ack():
                            saw_ack = True
                            deadline = self.hass.loop.time() + 2.0
                            continue
                        continue

                    raw_frames.append(raw_response_text)
                    await self._handle_incoming_message(resulting_message)

                    if self._matches_expected_status_response(
                        resulting_message,
                        expected_response,
                    ):
                        matched_expected_response = True
                        deadline = self.hass.loop.time() + 0.2
                    else:
                        deadline = self.hass.loop.time() + 1.2

                if matched_expected_response:
                    return {
                        "success": saw_ack or bool(raw_frames),
                        "acknowledged": saw_ack,
                        "raw_frames": raw_frames,
                    }

                LOGGER.debug(
                    "%s Collected request `%s` did not receive the expected response on attempt %s/%s.",
                    self.log_id,
                    message,
                    attempt,
                    attempts,
                )
                if attempt < attempts:
                    await asyncio.sleep(0.15)

            return {
                "success": False,
                "acknowledged": False,
                "raw_frames": raw_frames,
            }
        except Exception:  # pylint: disable=broad-except
            LOGGER.exception(
                "%s Command session crashed during collected status request.",
                self.log_id,
            )
            return {
                "success": False,
                "acknowledged": False,
                "raw_frames": raw_frames,
            }
        finally:
            await command_session.close()
