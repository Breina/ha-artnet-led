"""ARTNET LED"""
import logging
from functools import partial
from typing import Any, Union

import homeassistant.helpers.config_validation as cv
import pyartnet
import voluptuous as vol
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.light import ATTR_TRANSITION
from homeassistant.components.number.const import NumberDeviceClass
from homeassistant.components.sensor.device_trigger import CONF_VALUE
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_NAME, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
import homeassistant.util.color as color_util

from custom_components.dmx.client import PortAddress
from custom_components.dmx.const import DOMAIN

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

CONF_NODE_TYPE_ARTNET = "artnet"
CONF_MAX_FPS = "max_fps"
CONF_REFRESH_EVERY = "refresh_every"
CONF_UNIVERSES = "universes"
CONF_COMPATIBILITY = "compatibility"
CONF_SEND_PARTIAL_UNIVERSE = "send_partial_universe"
CONF_MANUAL_NODES = "manual_nodes"
CONF_CHANNELS = "channels"
CONF_NODE_TYPE = "node_type"
CONF_NODE_MAX_FPS = "max_fps"
CONF_NODE_REFRESH = "refresh_every"
CONF_NODE_UNIVERSES = "universes"
CONF_DEVICE_CHANNEL = "channel"
CONF_OUTPUT_CORRECTION = "output_correction"
CONF_CHANNEL_SIZE = "channel_size"
CONF_BYTE_ORDER = "byte_order"
CONF_DEVICE_MIN_TEMP = "min_temp"
CONF_DEVICE_MAX_TEMP = "max_temp"
CONF_CHANNEL_SETUP = "channel_setup"
CONF_CLASS = "class"
CONF_THRESHOLD = "threshold"
CONF_TRANSITION = ATTR_TRANSITION
CONF_TRIGGERS = "triggers"
CONF_SCENES = "scenes"
CONF_SCENE_ENTITY_ID = "scene_entity_id"
CONF_SHOWS = "shows"
CONF_OEM = "oem"
CONF_TEXT = "text"

CONF_TYPE_VALUES = ["fixed", "binary", "dimmer", "rgb", "rgbw", "rgbww", "color_temp",
                    "fan", "binary_sensor", "number", "switch"
                    ]
AVAILABLE_CORRECTIONS = {"linear": pyartnet.output_correction.linear, "quadratic": pyartnet.output_correction.quadratic,
                         "cubic": pyartnet.output_correction.cubic, "quadruple": pyartnet.output_correction.quadruple}

CHANNEL_SIZE = {
    "8bit": (1, 1),
    "16bit": (2, 256),
    "24bit": (3, 256 ** 2),
    "32bit": (4, 256 ** 3),
}


def port_address(value: Any) -> PortAddress:
    """Validate that the given Port Address string is valid"""

    if isinstance(value, int):
        universe = value
        universe_only = True

    else:
        if not isinstance(value, str):
            raise vol.Invalid(f"Not a string value: {value}")

        address_parts = value.split("/")

        if len(address_parts) != 1 and len(address_parts) != 3:
            raise vol.Invalid(
                f"Port address '{value}' should be either just a Universe number (i.e. '1'), "
                f"or contain Net, SubNet and Universe respectively as such '3/2/1'."
            )

        universe_only = len(address_parts) == 1

        try:
            address_ints = list(map(int, address_parts))
        except ValueError as e:
            raise vol.Invalid(
                f"Port address '{value}' could not be parsed as numbers because of: '{e}'"
            )

        universe = address_ints[2] if not universe_only else address_ints[0]

    if not (0x000 <= universe <= 0x1FF):
        raise vol.Invalid(
            f"Port address '{value}' Universe must be within the range [{0x000}, {0x1FF}], but was {universe}. "
            f"If that's not enough, please use Net and Sub-Net as part of the addressing."
        )

    if universe_only:
        return PortAddress(0, 0, universe)

    net = address_ints[0]
    if not (0x0 <= net <= 0xF):
        raise vol.Invalid(
            f"Port address '{value}' Net must be within the range [{0x0}, {0xF}], but was {net}"
        )

    sub_net = address_ints[1]
    if not (0x0 <= sub_net <= 0xF):
        raise vol.Invalid(
            f"Port address '{value}' Sub-Net must be within the range [{0x0}, {0xF}], but was {sub_net}"
        )

    return PortAddress(net, sub_net, universe)


def channel_setup(allowed_chars: str, value: Any) -> [Union[str, int]]:
    if isinstance(value, str):
        value = [*value]
    elif not isinstance(value, list):
        raise vol.Invalid(f"Not a string or list value: {value}")

    for c in value:
        if isinstance(c, int):
            if not (0x00 < c < 0xFF):
                vol.Invalid(f"Channel setup {value} numbers should be in the range [{0x00}, {0xFF}], but was {c}")
        elif c not in allowed_chars:
            raise vol.Invalid(f"Channel setup {value} contains invalid letter {c}")

    return value

def color_temp(value: Any) -> int:
    if not isinstance(value, str):
        raise vol.Invalid(f"Not a string: {value}")

    if value[-1] != 'K':
        raise vol.Invalid(f"Kelvin temperature {value} should end on capital 'K', but was {value[-1]}")

    try:
        return int(value[:-1])
    except ValueError as e:
        raise vol.Invalid(f"Could not interpret kelvin temprature {value} as a number: {e}")

def setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Your controller/hub specific code."""

    log.info(f"Started setup {config}")

    platform_configs = config.get(DOMAIN)

    for platform_config in platform_configs:
        log.info(f"Platform config: {platform_config}")

    # hass.helpers.discovery.load_platform('sensor', DOMAIN, {}, config)

    return True

    # {
    #     vol.Required(CONF_NODE_HOST): cv.string,
    #     vol.Required(CONF_NODE_UNIVERSES): {
    #         vol.All(int, vol.Range(min=0, max=1024)): {
    #             vol.Optional(CONF_SEND_PARTIAL_UNIVERSE, default=True): cv.boolean,
    #             vol.Optional(CONF_OUTPUT_CORRECTION, default='linear'): vol.Any(
    #                 None, vol.In(AVAILABLE_CORRECTIONS)
    #             ),
    #             CONF_DEVICES: vol.All(
    #                 cv.ensure_list,
    #                 [
    #                     {
    #                         vol.Required(CONF_DEVICE_CHANNEL): vol.All(
    #                             vol.Coerce(int), vol.Range(min=1, max=512)
    #                         ),
    #                         vol.Required(CONF_DEVICE_NAME): cv.string,
    #                         vol.Optional(CONF_DEVICE_FRIENDLY_NAME): cv.string,
    #                         vol.Optional(CONF_DEVICE_TYPE, default='dimmer'): vol.In(
    #                             [k.CONF_TYPE for k in __CLASS_LIST]
    #                         ),
    #                         vol.Optional(CONF_DEVICE_TRANSITION, default=0): vol.All(
    #                             vol.Coerce(float), vol.Range(min=0, max=999)
    #                         ),
    #                         vol.Optional(CONF_OUTPUT_CORRECTION, default='linear'): vol.Any(
    #                             None, vol.In(AVAILABLE_CORRECTIONS)
    #                         ),
    #                         vol.Optional(CONF_CHANNEL_SIZE, default='8bit'): vol.Any(
    #                             None, vol.In(CHANNEL_SIZE)
    #                         ),
    #                         vol.Optional(CONF_BYTE_ORDER, default='big'): vol.Any(
    #                             None, vol.In(['little', 'big'])
    #                         ),
    #                         vol.Optional(CONF_DEVICE_MIN_TEMP, default='2700K'): vol.Match(
    #                             "\\d+(k|K)"
    #                         ),
    #                         vol.Optional(CONF_DEVICE_MAX_TEMP, default='6500K'): vol.Match(
    #                             "\\d+(k|K)"
    #                         ),
    #                         vol.Optional(CONF_CHANNEL_SETUP, default=None): vol.Any(
    #                             None, cv.string, cv.ensure_list
    #                         ),
    #                     }
    #                 ],
    #             )
    #         },
    #     },
    #     vol.Optional(CONF_NODE_PORT, default=6454): cv.port,
    #     vol.Optional(CONF_NODE_MAX_FPS, default=25): vol.All(
    #         vol.Coerce(int), vol.Range(min=1, max=50)
    #     ),
    #     vol.Optional(CONF_NODE_REFRESH, default=120): vol.All(
    #         vol.Coerce(int), vol.Range(min=0, max=9999)
    #     ),
    #     vol.Optional(CONF_NODE_TYPE, default="artnet-direct"): vol.Any(
    #         None, vol.In(["artnet-direct", "artnet-controller", "sacn", "kinet"])
    #     ),
    # },
    # required = True,
    # extra = vol.PREVENT_EXTRA,


#

COMPATIBILITY_SCHEMA = \
    vol.Schema(
        {
            vol.Optional(CONF_SEND_PARTIAL_UNIVERSE, default=True): cv.boolean,
            vol.Optional(CONF_MANUAL_NODES): vol.Schema(
                [{
                    vol.Required(CONF_HOST): cv.string,
                    vol.Optional(CONF_PORT, default=6454): cv.port
                }]
            )
        }
    )

CHANNEL_BASE_SCHEMA = \
    vol.Schema(
        {
            vol.Required(CONF_NAME): cv.string,
            vol.Optional(CONF_CHANNEL_SIZE, default='8bit'): vol.Any(None, vol.In(CHANNEL_SIZE)),
            vol.Optional(CONF_BYTE_ORDER, default='big'): vol.Any(None, vol.In(['little', 'big'])),
        }
    )

BINARY_SENSOR_SCHEMA = CHANNEL_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): "binary_sensor",
        vol.Optional(CONF_CLASS, default=None): vol.Any(None, vol.In([e.value for e in BinarySensorDeviceClass])),
        vol.Optional(CONF_THRESHOLD, default=1): cv.positive_int
    }
)

NUMBER_SCHEMA = CHANNEL_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): "number",
        vol.Optional(CONF_CLASS, default=None): vol.Any(None, vol.In([e.value for e in NumberDeviceClass]))
    }
)

SWITCH_SCHEM = CHANNEL_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): "switch",
        vol.Optional(CONF_VALUE): cv.positive_int
    }
)

FAN_SCHEMA = CHANNEL_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): "fan"
    }
)

LIGHT_BASE_SCHEMA = CHANNEL_BASE_SCHEMA.extend(
    {
        vol.Optional(CONF_OUTPUT_CORRECTION, default='linear'): vol.Any(None, vol.In(AVAILABLE_CORRECTIONS)),
        vol.Optional(CONF_TRANSITION, default=0): vol.All(vol.Coerce(float), cv.positive_int),
    }
)

FIXED_LIGHT_SCHEMA = LIGHT_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): "fixed",
        vol.Optional(CONF_CHANNEL_SETUP): partial(channel_setup, '')
    }
)

BINARY_LIGHT_SCHEMA = LIGHT_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): "binary",
        vol.Optional(CONF_CHANNEL_SETUP): partial(channel_setup, '')
    }
)

DIMMER_LIGHT_SCHEMA = LIGHT_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): "dimmer",
        vol.Optional(CONF_CHANNEL_SETUP): partial(channel_setup, 'd')
    }
)

CUSTOM_WHITE_LIGHT_SCHEMA = LIGHT_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): "custom_white",
        vol.Optional(CONF_CHANNEL_SETUP): partial(channel_setup, 'dcChHtT'),
        vol.Optional(CONF_DEVICE_MIN_TEMP): color_temp
    }
)

RGB_LIGHT_SCHEMA = LIGHT_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): "rgb",
        vol.Optional(CONF_CHANNEL_SETUP): partial(channel_setup, 'drRgGbBwW')
    }
)

RGBW_LIGHT_SCHEMA = LIGHT_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): "rgbw",
        vol.Optional(CONF_CHANNEL_SETUP): partial(channel_setup, 'drRgGbBwW')
    }
)

RGBWW_LIGHT_SCHEMA = LIGHT_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): "rgbww",
        vol.Optional(CONF_CHANNEL_SETUP): partial(channel_setup, 'dcChHtTrRgGbB')
    }
)

CHANNEL_CONFIG = vol.Any(BINARY_SENSOR_SCHEMA, NUMBER_SCHEMA, SWITCH_SCHEM, FAN_SCHEMA, FIXED_LIGHT_SCHEMA,
                  BINARY_LIGHT_SCHEMA, DIMMER_LIGHT_SCHEMA, CUSTOM_WHITE_LIGHT_SCHEMA, RGB_LIGHT_SCHEMA,
                  RGBW_LIGHT_SCHEMA, RGBWW_LIGHT_SCHEMA)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_NODE_TYPE_ARTNET): vol.Schema(
                    {
                        vol.Optional(CONF_MAX_FPS, default=30): vol.All(vol.Coerce(int), vol.Range(min=0, max=43)),
                        vol.Optional(CONF_REFRESH_EVERY, default=0.8): cv.positive_float,

                        vol.Optional(CONF_UNIVERSES): vol.Schema(
                            [{
                                port_address: vol.Schema(
                                    {
                                        vol.Optional(CONF_COMPATIBILITY): COMPATIBILITY_SCHEMA,
                                        vol.Required(CONF_CHANNELS): vol.Schema(
                                            [{
                                                cv.positive_int: CHANNEL_CONFIG
                                            }]
                                        )
                                    }
                                )
                            }],
                        ),

                        vol.Optional(CONF_TRIGGERS): vol.Schema(
                            vol.Optional
                        )
                    },
                )
                # vol.Required(CONF_DEVICE): cv.string,
                # vol.Required(CONF_PORT): cv.port,
                # vol.Optional(CONF_IP_ADDRESS): cv.string,
            },
            extra=vol.ALLOW_EXTRA
        )
    },
    extra=vol.ALLOW_EXTRA
)
