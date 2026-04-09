"""Validator for the MyHome configuration file."""
import re

from voluptuous import (
    Schema,
    Optional,
    Required,
    Coerce,
    Boolean,
    Any,
    All,
    In,
    Invalid,
    Range,
)
from homeassistant.helpers.device_registry import format_mac as ha_format_mac
from homeassistant.components.light import DOMAIN as LIGHT
from homeassistant.components.camera import DOMAIN as CAMERA
from homeassistant.components.switch import (
    SwitchDeviceClass,
    DOMAIN as SWITCH,
)
from homeassistant.components.button import DOMAIN as BUTTON
from homeassistant.components.number import DOMAIN as NUMBER
from homeassistant.components.select import DOMAIN as SELECT
from homeassistant.components.text import DOMAIN as TEXT
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
from homeassistant.components.alarm_control_panel import DOMAIN as ALARM_CONTROL_PANEL
from homeassistant.const import CONF_NAME, CONF_MAC

from .const import (
    CONF_PLATFORMS,
    CONF_WHO,
    CONF_WHERE,
    CONF_OPERATION,
    CONF_SENSOR_ADDRESS,
    CONF_BUS_INTERFACE,
    CONF_ENTITIES,
    CONF_ENTITY_NAME,
    CONF_ICON,
    CONF_ICON_ON,
    CONF_ZONE,
    CONF_FAN_SUPPORT,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_CLASS,
    CONF_DIMMABLE,
    CONF_ADVANCED_SHUTTER,
    CONF_INVERTED,
    CONF_HEATING_SUPPORT,
    CONF_COOLING_SUPPORT,
    CONF_STANDALONE,
    CONF_CENTRAL,
)


def format_mac(address: str) -> str:
    mac = re.sub("[.:-]", "", address).upper()
    mac = "".join(mac.split())
    if len(mac) != 12 or not mac.isalnum() or re.search("[G-Z]", mac) is not None:
        return None
    return ha_format_mac(mac)


class MacAddress(object):
    def __init__(self, msg=None):
        self.msg = msg

    def __call__(self, v):
        v = format_mac(v)
        if v is None:
            raise Invalid("Invalid MAC address")
        return format_mac(v)

    def __repr__(self):
        return "MacAddress(%s, msg=%r)" % ("String", self.msg)


class General(object):
    def __init__(self, msg=None):
        self.msg = msg

    def __call__(self, v):
        if type(v) == str and v == "0":
            return v
        else:
            raise Invalid(f"Invalid General WHERE {v}, it must be 0.")

    def __repr__(self):
        return "Where(%s, msg=%r)" % ("String", self.msg)


class Area(object):
    def __init__(self, msg=None):
        self.msg = msg

    def __call__(self, v):
        if type(v) == str and v in ["00", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]:
            return v
        else:
            raise Invalid(f"Invalid Area WHERE {v}, it must be a string in [00, 1-9, 10].")

    def __repr__(self):
        return "Where(%s, msg=%r)" % ("String", self.msg)


class Group(object):
    def __init__(self, msg=None):
        self.msg = msg

    def __call__(self, v):
        if type(v) == str and v.startswith("#") and v[1:].isdigit() and int(v[1:]) >= 1 and int(v[1:]) <= 255:
            return f"#{int(v[1:])}"
        else:
            raise Invalid(f"Invalid Group WHERE {v}, it must be a string like '#[1-255]'.")

    def __repr__(self):
        return "Where(%s, msg=%r)" % ("String", self.msg)


class PointToPoint(object):
    def __init__(self, msg=None):
        self.msg = msg

    def __call__(self, v):
        if type(v) == str and v.isdigit():
            _length = len(v)
            if _length == 2 or _length == 4:
                _a = v[0 : _length // 2]
                _pl = v[_length // 2 :]
                if int(_a) >= 0 and int(_a) <= 10 and int(_pl) >= 0 and int(_pl) <= 15:
                    return f"{_a}{_pl}"
                else:
                    raise Invalid(f"Invalid WHERE {v}, A must be [0-10] and PL must be [0-15].")
            else:
                raise Invalid(f"Invalid WHERE {v} length, it must be a string of 2 or 4 digits.")
        else:
            raise Invalid(f"Invalid WHERE {v}, it must be a string of 2 or 4 digits.")

    def __repr__(self):
        return "Where(%s, msg=%r)" % ("String", self.msg)


class SpecialWhere(object):
    def __init__(self, msg=None):
        self.msg = msg

    def __call__(self, v):
        if type(v) == str and v.isdigit():
            return v
        else:
            raise Invalid(f"Invalid WHERE {v}, it must be a string of digits.")

    def __repr__(self):
        return "Where(%s, msg=%r)" % ("String", self.msg)


class LightManagementWhere(object):
    def __init__(self, msg=None):
        self.msg = msg

    def __call__(self, v):
        if (
            type(v) == str
            and re.fullmatch(r"\d+(?:#\d+)*", v) is not None
        ):
            return v
        raise Invalid(
            f"Invalid lighting-management WHERE {v}, it must be digits optionally separated by '#'."
        )

    def __repr__(self):
        return "Where(%s, msg=%r)" % ("String", self.msg)


class BusInterface(object):
    def __init__(self, msg=None):
        self.msg = msg

    def __call__(self, v):
        if type(v) == str and v.isdigit() and len(v) == 2:
            if int(v) > 15:
                raise Invalid(f"Invalid Bus Interface number {v}, it must be between 00 and 15.")
        elif v is not None:
            raise Invalid(f"Invalid Bus Interface number {v}, it must be a string of 2 digits.")
        return v

    def __repr__(self):
        return "BusInterface(%s, msg=%r)" % ("String", self.msg)


class MyHomeConfigSchema(Schema):
    def __call__(self, data):
        data = super().__call__(data)
        _rekeyed_data = {}
        for gateway in data:
            _rekeyed_data[data[gateway][CONF_MAC]] = {}
            _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS] = {}
            for platform in data[gateway]:
                if platform != CONF_MAC:
                    _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS][platform] = data[gateway][platform]

            if (
                (LIGHT in _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS])
                or (SWITCH in _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS])
                or (COVER in _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS])
            ):
                _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS].setdefault(
                    BUTTON, {}
                )
                if LIGHT in _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS]:
                    for key, value in _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS][LIGHT].items():
                        if not value[CONF_WHERE].startswith("#"):
                            _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS][BUTTON][key] = value
                if SWITCH in _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS]:
                    for key, value in _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS][SWITCH].items():
                        if value[CONF_WHO] == "17":
                            continue
                        if not value[CONF_WHERE].startswith("#"):
                            _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS][BUTTON][key] = value
                if COVER in _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS]:
                    for key, value in _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS][COVER].items():
                        if not value[CONF_WHERE].startswith("#"):
                            _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS][BUTTON][key] = value

            if SWITCH in _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS]:
                _load_switches_configured = any(
                    value[CONF_WHO] == "18"
                    for value in _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS][SWITCH].values()
                )
                if _load_switches_configured:
                    _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS].setdefault(NUMBER, {})
                    _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS].setdefault(SENSOR, {})
                    _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS].setdefault(BINARY_SENSOR, {})

            if BINARY_SENSOR in _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS]:
                _lighting_motion_sensors_configured = any(
                    value[CONF_WHO] == "1"
                    and value.get(CONF_DEVICE_CLASS) == BinarySensorDeviceClass.MOTION
                    for value in _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS][BINARY_SENSOR].values()
                )
                if _lighting_motion_sensors_configured:
                    _rekeyed_data[data[gateway][CONF_MAC]][CONF_PLATFORMS].setdefault(SENSOR, {})

        return _rekeyed_data


class MyHomeDeviceSchema(Schema):
    def __call__(self, data):
        data = super().__call__(data)
        _rekeyed_data = {}

        for device in data:
            data[device][CONF_ENTITIES] = {}
            if CONF_OPERATION in data[device]:
                if CONF_WHERE in data[device]:
                    _new_key = (
                        f"{data[device][CONF_WHO]}-"
                        f"{data[device][CONF_WHERE]}-"
                        f"{data[device][CONF_OPERATION]}"
                    )
                else:
                    _new_key = (
                        f"{data[device][CONF_WHO]}-"
                        f"{data[device][CONF_OPERATION]}"
                    )
                _rekeyed_data[_new_key] = data[device]
            elif CONF_WHERE in data[device]:
                _new_key = (
                    f"{data[device][CONF_WHO]}-{data[device][CONF_WHERE]}#4#{data[device][CONF_BUS_INTERFACE]}"
                    if CONF_BUS_INTERFACE in data[device] and data[device][CONF_BUS_INTERFACE] is not None
                    else f"{data[device][CONF_WHO]}-{data[device][CONF_WHERE]}"
                )
                _rekeyed_data[_new_key] = data[device]
            elif CONF_ZONE in data[device]:
                _new_key = f"{data[device][CONF_WHO]}-{data[device][CONF_ZONE]}"
                data[device][CONF_ZONE] = f"#0#{data[device][CONF_ZONE]}" if data[device][CONF_CENTRAL] and data[device][CONF_ZONE] != "#0" else data[device][CONF_ZONE]
                data[device][CONF_NAME] = (
                    data[device][CONF_NAME] if CONF_NAME in data[device] else "Central unit" if data[device][CONF_ZONE].startswith("#0") else f"Zone {data[device][CONF_ZONE]}"
                )
                _rekeyed_data[_new_key] = data[device]
            if CONF_DEVICE_MODEL not in data[device]:
                data[device][CONF_DEVICE_MODEL] = None
            if CONF_ICON not in data[device]:
                data[device][CONF_ICON] = None
            if CONF_ICON_ON not in data[device]:
                data[device][CONF_ICON_ON] = None
            if CONF_ENTITY_NAME not in data[device]:
                data[device][CONF_ENTITY_NAME] = None

        return _rekeyed_data


class MyHomeSensorSchema(Schema):
    def __call__(self, data):
        data = super().__call__(data)
        _rekeyed_data = {}

        for device in data:
            data[device][CONF_ENTITIES] = {}
            if CONF_OPERATION in data[device]:
                if data[device].get(CONF_WHO) != "24":
                    raise Invalid("invalid sensor operation for selected who")
            elif CONF_DEVICE_CLASS not in data[device]:
                raise Invalid("sensor requires either class or operation")

            if CONF_DEVICE_CLASS in data[device]:
                if data[device][CONF_DEVICE_CLASS] in [
                    SensorDeviceClass.POWER,
                    SensorDeviceClass.ENERGY,
                ]:
                    if CONF_WHO not in data[device]:
                        data[device][CONF_WHO] = "18"
                    elif data[device][CONF_WHO] != "18":
                        raise Invalid("invalid sensor class for selected who")
                    data[device][CONF_ENTITIES][f"daily-{SensorDeviceClass.ENERGY}"] = {}
                    data[device][CONF_ENTITIES][f"monthly-{SensorDeviceClass.ENERGY}"] = {}
                    data[device][CONF_ENTITIES][f"total-{SensorDeviceClass.ENERGY}"] = {}
                    if data[device][CONF_DEVICE_CLASS] in [SensorDeviceClass.POWER]:
                        data[device][CONF_ENTITIES][f"{SensorDeviceClass.POWER}"] = {}
                elif data[device][CONF_DEVICE_CLASS] in [SensorDeviceClass.TEMPERATURE]:
                    if CONF_WHO not in data[device]:
                        data[device][CONF_WHO] = "4"
                    elif data[device][CONF_WHO] != "4":
                        raise Invalid("invalid sensor class for selected who")
                elif data[device][CONF_DEVICE_CLASS] in [SensorDeviceClass.ILLUMINANCE]:
                    if CONF_WHO not in data[device]:
                        data[device][CONF_WHO] = "1"
                    elif data[device][CONF_WHO] != "1":
                        raise Invalid("invalid sensor class for selected who")
            if data[device].get(CONF_WHO) == "24":
                data[device][CONF_WHERE] = LightManagementWhere()(data[device][CONF_WHERE])
            else:
                data[device][CONF_WHERE] = SpecialWhere()(data[device][CONF_WHERE])
            if CONF_WHERE in data[device]:
                _new_key = (
                    f"{data[device][CONF_WHO]}-{data[device][CONF_WHERE]}-{data[device][CONF_OPERATION]}"
                    if CONF_OPERATION in data[device]
                    else (
                        f"{data[device][CONF_WHO]}-{data[device][CONF_WHERE]}#4#{data[device][CONF_BUS_INTERFACE]}"
                        if CONF_BUS_INTERFACE in data[device] and data[device][CONF_BUS_INTERFACE] is not None
                        else f"{data[device][CONF_WHO]}-{data[device][CONF_WHERE]}"
                    )
                )
                _rekeyed_data[_new_key] = data[device]
            if CONF_DEVICE_MODEL not in data[device]:
                data[device][CONF_DEVICE_MODEL] = None
            if CONF_ENTITY_NAME not in data[device]:
                data[device][CONF_ENTITY_NAME] = None

        return _rekeyed_data


class MyHomeAlarmSchema(Schema):
    def __call__(self, data):
        data = super().__call__(data)
        _rekeyed_data = {}

        for device in data:
            data[device][CONF_ENTITIES] = {}
            if CONF_DEVICE_MODEL not in data[device]:
                data[device][CONF_DEVICE_MODEL] = None
            if CONF_ENTITY_NAME not in data[device]:
                data[device][CONF_ENTITY_NAME] = None
            _rekeyed_data[device] = data[device]

        return _rekeyed_data


light_schema = MyHomeDeviceSchema(
    {
        Required(str): {
            Optional(CONF_WHO, default="1"): "1",
            Required(CONF_WHERE): All(
                Coerce(str), Any(General(), Area(), Group(), PointToPoint(), msg="Invalid <WHERE>, expecting a valid General, Area, Group or Point-to-Point <WHERE>")
            ),
            Optional(CONF_BUS_INTERFACE): All(Coerce(str), BusInterface()),
            Required(CONF_NAME): str,
            Optional(CONF_ENTITY_NAME): str,
            Optional(CONF_ICON): str,
            Optional(CONF_ICON_ON): str,
            Optional(CONF_DIMMABLE, default=False): Boolean(),
            Optional(CONF_MANUFACTURER, default="BTicino S.p.A."): str,
            Optional(CONF_DEVICE_MODEL): Coerce(str),
        }
    }
)

switch_schema = MyHomeDeviceSchema(
    {
        Required(str): {
            Optional(CONF_WHO, default="1"): In(["1", "17", "18", "24"]),
            Required(CONF_WHERE): All(
                Coerce(str), Any(
                    General(),
                    Area(),
                    Group(),
                    PointToPoint(),
                    LightManagementWhere(),
                    msg="Invalid <WHERE>, expecting a valid General, Area, Group, Point-to-Point or WHO=24 lighting-management <WHERE>",
                )
            ),
            Optional(CONF_BUS_INTERFACE): All(Coerce(str), BusInterface()),
            Required(CONF_NAME): str,
            Optional(CONF_ENTITY_NAME): str,
            Optional(CONF_OPERATION): In(["active", "enabled", "auto_switch_on", "auto_switch_off"]),
            Optional(CONF_ICON): str,
            Optional(CONF_ICON_ON): str,
            Optional(CONF_DEVICE_CLASS, default=SwitchDeviceClass.SWITCH): In(
                [
                    SwitchDeviceClass.OUTLET,
                    SwitchDeviceClass.SWITCH,
                ]
            ),
            Optional(CONF_MANUFACTURER, default="BTicino S.p.A."): str,
            Optional(CONF_DEVICE_MODEL): Coerce(str),
        }
    }
)

cover_schema = MyHomeDeviceSchema(
    {
        Required(str): {
            Optional(CONF_WHO, default="2"): "2",
            Required(CONF_WHERE): All(
                Coerce(str), Any(General(), Area(), Group(), PointToPoint(), msg="Invalid <WHERE>, expecting a valid General, Area, Group or Point-to-Point <WHERE>")
            ),
            Optional(CONF_BUS_INTERFACE): All(Coerce(str), BusInterface()),
            Required(CONF_NAME): str,
            Optional(CONF_ENTITY_NAME): str,
            Optional(CONF_ADVANCED_SHUTTER, default=False): Boolean(),
            Optional(CONF_MANUFACTURER, default="BTicino S.p.A."): str,
            Optional(CONF_DEVICE_MODEL): Coerce(str),
        }
    }
)

button_schema = MyHomeDeviceSchema(
    {
        Required(str): {
            Required(CONF_WHO): In(["7", "17"]),
            Optional(CONF_WHERE): All(Coerce(str), SpecialWhere()),
            Required(CONF_NAME): str,
            Optional(CONF_ENTITY_NAME): str,
            Required(CONF_OPERATION): Coerce(str),
            Optional(CONF_MANUFACTURER, default="BTicino S.p.A."): str,
            Optional(CONF_DEVICE_MODEL): Coerce(str),
        }
    }
)

number_schema = MyHomeDeviceSchema(
    {
        Required(str): {
            Required(CONF_WHO): In(["24"]),
            Required(CONF_WHERE): All(Coerce(str), LightManagementWhere()),
            Required(CONF_NAME): str,
            Optional(CONF_ENTITY_NAME): str,
            Required(CONF_OPERATION): In(
                [
                    "switch_on_value",
                    "max_lux",
                    "maintained_lux",
                    "switch_on_delay",
                    "switch_off_delay",
                    "delay_timer",
                    "standby_timer",
                    "standby_value",
                    "off_value",
                    "slave_offset",
                ]
            ),
            Optional(CONF_MANUFACTURER, default="BTicino S.p.A."): str,
            Optional(CONF_DEVICE_MODEL): Coerce(str),
        }
    }
)

select_schema = MyHomeDeviceSchema(
    {
        Required(str): {
            Required(CONF_WHO): In(["24"]),
            Required(CONF_WHERE): All(Coerce(str), LightManagementWhere()),
            Required(CONF_NAME): str,
            Optional(CONF_ENTITY_NAME): str,
            Required(CONF_OPERATION): In(["mode", "exit_condition"]),
            Optional(CONF_MANUFACTURER, default="BTicino S.p.A."): str,
            Optional(CONF_DEVICE_MODEL): Coerce(str),
        }
    }
)

text_schema = MyHomeDeviceSchema(
    {
        Required(str): {
            Optional(CONF_WHO, default="22"): "22",
            Required(CONF_WHERE): All(Coerce(str), LightManagementWhere()),
            Required(CONF_NAME): str,
            Optional(CONF_ENTITY_NAME): str,
            Required(CONF_OPERATION): In(
                ["equalization_1", "equalization_2", "equalization_3"]
            ),
            Optional(CONF_MANUFACTURER, default="BTicino S.p.A."): str,
            Optional(CONF_DEVICE_MODEL): Coerce(str),
        }
    }
)

binary_sensor_schema = MyHomeDeviceSchema(
    {
        Required(str): {
            Optional(CONF_WHO, default="25"): In(["1", "9", "25"]),
            Required(CONF_WHERE): All(Coerce(str), SpecialWhere()),
            Required(CONF_NAME): str,
            Optional(CONF_ENTITY_NAME): str,
            Optional(CONF_INVERTED, default=False): Boolean(),
            Optional(CONF_DEVICE_CLASS): In(
                [
                    BinarySensorDeviceClass.BATTERY,
                    BinarySensorDeviceClass.BATTERY_CHARGING,
                    BinarySensorDeviceClass.COLD,
                    BinarySensorDeviceClass.CONNECTIVITY,
                    BinarySensorDeviceClass.DOOR,
                    BinarySensorDeviceClass.GARAGE_DOOR,
                    BinarySensorDeviceClass.GAS,
                    BinarySensorDeviceClass.HEAT,
                    BinarySensorDeviceClass.LIGHT,
                    BinarySensorDeviceClass.LOCK,
                    BinarySensorDeviceClass.MOISTURE,
                    BinarySensorDeviceClass.MOTION,
                    BinarySensorDeviceClass.MOVING,
                    BinarySensorDeviceClass.OCCUPANCY,
                    BinarySensorDeviceClass.OPENING,
                    BinarySensorDeviceClass.PLUG,
                    BinarySensorDeviceClass.POWER,
                    BinarySensorDeviceClass.PRESENCE,
                    BinarySensorDeviceClass.PROBLEM,
                    BinarySensorDeviceClass.SAFETY,
                    BinarySensorDeviceClass.SMOKE,
                    BinarySensorDeviceClass.SOUND,
                    BinarySensorDeviceClass.VIBRATION,
                    BinarySensorDeviceClass.WINDOW,
                ]
            ),
            Optional(CONF_MANUFACTURER, default="BTicino S.p.A."): str,
            Optional(CONF_DEVICE_MODEL): Coerce(str),
        }
    }
)

sensor_schema = MyHomeSensorSchema(
    {
        Required(str): {
            Optional(CONF_WHO): In(["1", "4", "18", "24"]),
            Required(CONF_WHERE): All(
                Coerce(str),
                Any(SpecialWhere(), LightManagementWhere()),
            ),
            Required(CONF_NAME): str,
            Optional(CONF_ENTITY_NAME): str,
            Optional(CONF_DEVICE_CLASS): In(
                [
                    SensorDeviceClass.TEMPERATURE,
                    SensorDeviceClass.POWER,
                    SensorDeviceClass.ENERGY,
                    SensorDeviceClass.ILLUMINANCE,
                ]
            ),
            Optional(CONF_OPERATION): In(
                [
                    "state_time",
                    "centralized_lux",
                    "sensor_address",
                    "error_name",
                ]
            ),
            Optional(CONF_SENSOR_ADDRESS): Coerce(str),
            Optional(CONF_MANUFACTURER, default="BTicino S.p.A."): str,
            Optional(CONF_DEVICE_MODEL): Coerce(str),
        }
    }
)

climate_schema = MyHomeDeviceSchema(
    {
        Required(str): {
            Optional(CONF_WHO, default="4"): "4",
            Optional(CONF_ZONE, default="#0"): Coerce(str),
            Optional(CONF_NAME): str,
            Optional(CONF_HEATING_SUPPORT, default=True): Boolean(),
            Optional(CONF_COOLING_SUPPORT, default=False): Boolean(),
            Optional(CONF_FAN_SUPPORT, default=False): Boolean(),
            Optional(CONF_STANDALONE, default=False): Boolean(),
            Optional(CONF_CENTRAL, default=False): Boolean(),
            Optional(CONF_MANUFACTURER, default="BTicino S.p.A."): str,
            Optional(CONF_DEVICE_MODEL): Coerce(str),
        }
    }
)

alarm_control_panel_schema = MyHomeAlarmSchema(
    {
        Required(str): {
            Required(CONF_NAME): str,
            Optional(CONF_ENTITY_NAME): str,
            Optional("control_channel"): All(Coerce(int), Range(min=1, max=255)),
            Optional("arm_channel"): All(Coerce(int), Range(min=1, max=255)),
            Optional("disarm_channel"): All(Coerce(int), Range(min=1, max=255)),
            Optional(CONF_MANUFACTURER, default="BTicino S.p.A."): str,
            Optional(CONF_DEVICE_MODEL): Coerce(str),
        }
    }
)

camera_schema = MyHomeDeviceSchema(
    {
        Required(str): {
            Optional(CONF_WHO, default="7"): "7",
            Optional(CONF_WHERE, default="0"): All(Coerce(str), SpecialWhere()),
            Required(CONF_NAME): str,
            Optional(CONF_ENTITY_NAME): str,
            Optional(CONF_MANUFACTURER, default="BTicino S.p.A."): str,
            Optional(CONF_DEVICE_MODEL): Coerce(str),
        }
    }
)

gateway_schema = Schema(
    {
        Required(CONF_MAC): MacAddress(),
        Optional(CAMERA): camera_schema,
        Optional(LIGHT): light_schema,
        Optional(SWITCH): switch_schema,
        Optional(BUTTON): button_schema,
        Optional(NUMBER): number_schema,
        Optional(SELECT): select_schema,
        Optional(TEXT): text_schema,
        Optional(COVER): cover_schema,
        Optional(BINARY_SENSOR): binary_sensor_schema,
        Optional(SENSOR): sensor_schema,
        Optional(CLIMATE): climate_schema,
        Optional(ALARM_CONTROL_PANEL): alarm_control_panel_schema,
    }
)

config_schema = MyHomeConfigSchema({Required(str): gateway_schema})
