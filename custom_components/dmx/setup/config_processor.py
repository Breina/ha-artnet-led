"""Configuration processing for DMX integration."""

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import CONF_HOST, CONF_MODE, CONF_PORT
from homeassistant.core import HomeAssistant

from custom_components.dmx.fixture.fixture import Fixture
from custom_components.dmx.server import PortAddress

log = logging.getLogger(__name__)

# Configuration constants
CONF_NODE_TYPE_ARTNET = "artnet"
CONF_NODE_TYPE_SACN = "sacn"
CONF_ANIMATION = "animation"
CONF_MAX_FPS = "max_fps"
CONF_MAX_FPS_DEFAULT = 30
CONF_RATE_LIMIT = "rate_limit"
CONF_RATE_LIMIT_DEFAULT = 0.5
CONF_REFRESH_EVERY = "refresh_every"
CONF_REFRESH_EVERY_DEFAULT = 0.8
CONF_UNIVERSES = "universes"
CONF_SOURCE_NAME = "source_name"
CONF_SOURCE_NAME_DEFAULT = "HA sACN Controller"
CONF_PRIORITY = "priority"
CONF_PRIORITY_DEFAULT = 100
CONF_MULTICAST_TTL = "multicast_ttl"
CONF_MULTICAST_TTL_DEFAULT = 64
CONF_SYNC_ADDRESS = "sync_address"
CONF_ENABLE_PREVIEW_DATA = "enable_preview_data"
CONF_UNICAST_ADDRESSES = "unicast_addresses"
CONF_COMPATIBILITY = "compatibility"
CONF_SEND_PARTIAL_UNIVERSE = "send_partial_universe"
CONF_MANUAL_NODES = "manual_nodes"
CONF_DEVICES = "devices"
CONF_INTERFACE_IP = "interface_ip"
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
CONF_TRIGGERS = "triggers"
CONF_SCENES = "scenes"
CONF_SCENE_ENTITY_ID = "scene_entity_id"
CONF_SHOWS = "shows"
CONF_OEM = "oem"
CONF_TEXT = "text"
CONF_START_ADDRESS = "start_address"
CONF_FIXTURE = "fixture"
CONF_FIXTURES = "fixtures"
CONF_FOLDER = "folder"
CONF_FOLDER_DEFAULT = "fixtures"
CONF_ENTITY_ID_PREFIX = "entity_id_prefix"


def port_address_config(value: Any) -> int:
    """Validate that the given Port Address string is valid."""

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
            raise vol.Invalid(f"Port address '{value}' could not be parsed as numbers because of: '{e}'") from e

        universe = address_ints[2] if not universe_only else address_ints[0]

    if not (0x000 <= universe <= 0x1FF):
        raise vol.Invalid(
            f"Port address '{value}' Universe must be within the range [{0x000}, {0x1FF}], but was {universe}. "
            f"If that's not enough, please use Net and Sub-Net as part of the addressing."
        )

    if universe_only:
        return PortAddress(0, 0, universe).port_address

    net = address_ints[0]
    if not (0x0 <= net <= 0xF):
        raise vol.Invalid(f"Port address '{value}' Net must be within the range [{0x0}, {0xF}], but was {net}")

    sub_net = address_ints[1]
    if not (0x0 <= sub_net <= 0xF):
        raise vol.Invalid(f"Port address '{value}' Sub-Net must be within the range [{0x0}, {0xF}], but was {sub_net}")

    return PortAddress(net, sub_net, universe).port_address


async def process_fixtures(hass: HomeAssistant, fixture_folder: str) -> dict[str, Fixture]:
    """Process fixtures from the configured folder using the fixture registry."""
    from custom_components.dmx.fixture.registry import get_fixture_registry

    registry = get_fixture_registry(hass)

    try:
        # Use the registry's improved loading with caching and validation
        fixture_map = await registry.load_fixtures_from_folder(fixture_folder)

        # Log cache statistics
        cache_stats = registry.get_cache_stats()
        log.info(f"Fixture loading complete - Cache stats: {cache_stats}")

        return fixture_map

    except Exception as e:
        log.error(f"Error processing fixtures from {fixture_folder}: {e}")
        return {}


ARTNET_COMPATIBILITY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SEND_PARTIAL_UNIVERSE, default=True): cv.boolean,
        vol.Optional(CONF_MANUAL_NODES): vol.Schema(
            [{vol.Required(CONF_HOST): cv.string, vol.Optional(CONF_PORT, default=6454): cv.port}]
        ),
    }
)

SACN_COMPATIBILITY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_UNICAST_ADDRESSES): vol.Schema(
            [{vol.Required(CONF_HOST): cv.string, vol.Optional(CONF_PORT, default=5568): cv.port}]
        )
    }
)

DEVICE_CONFIG = vol.Schema(
    {
        vol.Required(CONF_START_ADDRESS): vol.All(vol.Coerce(int), vol.Range(min=0, max=511)),
        vol.Required(CONF_FIXTURE): cv.string,
        vol.Optional(CONF_MODE): vol.Any(None, cv.string),
        vol.Optional(CONF_ENTITY_ID_PREFIX): vol.Any(None, cv.string),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_FIXTURES): vol.Schema({vol.Optional(CONF_FOLDER, default=CONF_FOLDER_DEFAULT): cv.string}),
        vol.Optional(CONF_ANIMATION): vol.Schema(
            {
                vol.Optional(CONF_MAX_FPS, default=CONF_MAX_FPS_DEFAULT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=43)
                )
            }
        ),
        vol.Optional(CONF_NODE_TYPE_ARTNET): vol.Schema(
            {
                vol.Optional(CONF_REFRESH_EVERY, default=CONF_REFRESH_EVERY_DEFAULT): cv.positive_float,
                vol.Optional(CONF_RATE_LIMIT, default=CONF_RATE_LIMIT_DEFAULT): cv.positive_float,
                vol.Required(CONF_UNIVERSES): vol.Schema(
                    [
                        {
                            port_address_config: vol.Schema(
                                {
                                    vol.Optional(CONF_COMPATIBILITY): ARTNET_COMPATIBILITY_SCHEMA,
                                    vol.Required(CONF_DEVICES): vol.Schema([{cv.string: DEVICE_CONFIG}]),
                                }
                            )
                        }
                    ]
                ),
            }
        ),
        vol.Optional(CONF_NODE_TYPE_SACN): vol.Schema(
            {
                vol.Optional(CONF_SOURCE_NAME, default=CONF_SOURCE_NAME_DEFAULT): cv.string,
                vol.Optional(CONF_PRIORITY, default=CONF_PRIORITY_DEFAULT): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=200)
                ),
                vol.Optional(CONF_INTERFACE_IP): cv.string,
                vol.Optional(CONF_SYNC_ADDRESS, default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=63999)),
                vol.Optional(CONF_MULTICAST_TTL, default=CONF_MULTICAST_TTL_DEFAULT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=255)
                ),
                vol.Optional(CONF_ENABLE_PREVIEW_DATA, default=False): cv.boolean,
                vol.Optional(CONF_RATE_LIMIT, default=CONF_RATE_LIMIT_DEFAULT): cv.positive_float,
                vol.Required(CONF_UNIVERSES): vol.Schema(
                    [
                        {
                            vol.All(vol.Coerce(int), vol.Range(min=1, max=63999)): vol.Schema(
                                {
                                    vol.Optional(CONF_COMPATIBILITY): SACN_COMPATIBILITY_SCHEMA,
                                    vol.Required(CONF_DEVICES): vol.Schema([{cv.string: DEVICE_CONFIG}]),
                                }
                            )
                        }
                    ]
                ),
            }
        ),
    }
)
