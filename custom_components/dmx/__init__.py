"""ARTNET LED"""
import logging
from os import walk
from typing import Any

import Levenshtein
import homeassistant.helpers.config_validation as cv
import unicodedata
import voluptuous as vol
from homeassistant.components.light import ATTR_TRANSITION
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_MODE, Platform, CONF_SOURCE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import IntegrationError
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import ConfigType

from custom_components.dmx.bridge.artnet_controller import ArtNetController, DiscoveredNode
from custom_components.dmx.client import PortAddress
from custom_components.dmx.const import DOMAIN, HASS_DATA_ENTITIES, ARTNET_CONTROLLER, CONF_DATA, UNDO_UPDATE_LISTENER
from custom_components.dmx.fixture.parser import parse
from custom_components.dmx.fixture_delegator.delegator import create_entities
from custom_components.fixtures.ha_fixture import parse_json
from custom_components.fixtures.model import HaFixture

log = logging.getLogger(__name__)

CONF_NODE_TYPE_ARTNET = "artnet"
CONF_MAX_FPS = "max_fps"
CONF_REFRESH_EVERY = "refresh_every"
CONF_UNIVERSES = "universes"
CONF_COMPATIBILITY = "compatibility"
CONF_SEND_PARTIAL_UNIVERSE = "send_partial_universe"
CONF_MANUAL_NODES = "manual_nodes"
CONF_DEVICES = "devices"
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
CONF_START_ADDRESS = 'start_address'
CONF_FIXTURE = 'fixture'
CONF_FIXTURES = 'fixtures'
CONF_FOLDER = 'folder'

DEFAULT_FIXTURES_FOLDER = 'fixtures'

PLATFORMS = [Platform.NUMBER, Platform.SELECT, Platform.LIGHT]

FIXTURES = {}

ARTNET_CONTROLLER = None


class UnknownFixtureError(IntegrationError):
    def __init__(self, desired_fixture: str, discovered_fixtures: list[str], *args: object) -> None:
        super().__init__(*args)
        self._fixture = desired_fixture
        self._discovered_fixtures = discovered_fixtures

        max_ratio = 0
        to_match = unicodedata.normalize('NFKC', desired_fixture.lower())
        self._best_match = None
        for discovered_fixture in discovered_fixtures:
            to_test = unicodedata.normalize('NFKC', discovered_fixture.lower())
            ratio = Levenshtein.ratio(to_match, to_test, score_cutoff=0.8)
            if ratio > max_ratio:
                max_ratio = ratio
                self._best_match = discovered_fixture

    def __str__(self) -> str:
        if not self._discovered_fixtures:
            return "Didn't discover any fixtures. Put them in the fixtures folder as defined by " \
                   "config `dmx.fixtures.folder`"
        elif not self._best_match:
            return f"Could not find any fixture named '{self._fixture}'. " \
                   f"Note that first the fixture's `fixtureKey` is matched, if that's not " \
                   f"available `shortnName`, or finally `name`."
        else:
            return f"Could not find a fixture named '{self._fixture}', did you mean '{self._best_match}'? " \
                   f"Note that first the fixture's `fixtureKey` is matched first, if that's not " \
                   f"available `shortnName`, or finally `name`."


def load_fixtures(hass: HomeAssistant, platform_config: ConfigType):
    fixtures_config = platform_config.get(CONF_FIXTURES, {})
    folder = fixtures_config.get(CONF_FOLDER)
    path = f"{hass.config.config_dir}/{folder}"

    filenames = next(walk(path), (None, None, []))[2]

    for filename in filenames:
        fixture = parse_json(f"{path}/{filename}")
        FIXTURES[fixture.fixture_key] = fixture


def get_fixture(name: str) -> HaFixture:
    fixture = FIXTURES.get(name)
    if not fixture:
        raise UnknownFixtureError(name, list(FIXTURES.keys()))
    return fixture


def port_address_config(value: Any) -> PortAddress:
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


async def reload_configuration_yaml(event: dict, hass: HomeAssistant):
    """Reload configuration.yaml."""
    await hass.services.async_call("homeassistant", "check_config", {})


async def async_update_options(hass, config_entry: ConfigEntry):
    """Update options."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Your controller/hub specific code."""

    if DOMAIN not in config:
        return True

    discovery_flow.async_create_flow(
        hass,
        DOMAIN,
        context={CONF_SOURCE: SOURCE_IMPORT},
        data=config
    )

    # hass.data.setdefault(DOMAIN, {})
    #
    # artnet_controller = None
    #
    # def _discovered_node(discovered_node: DiscoveredNode):
    #     print(f"Found some! {discovered_node.long_name}")
    #     discovery_flow.async_create_flow(
    #         hass,
    #         DOMAIN,
    #         context={"source": SOURCE_INTEGRATION_DISCOVERY},
    #         data={
    #             ARTNET_CONTROLLER: artnet_controller,
    #             CONF_DATA: config[DOMAIN]
    #         },
    #     )
    #
    # artnet_controller = ArtNetController(hass, new_node_callback=_discovered_node, max_fps=43)
    # artnet_controller.start()
    #
    # # TODO parse config manual node discover also

    print(f"end of async_setup")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the component."""


    # print(f"async_setup_entry: {config_entry}")
    hass.data.setdefault(DOMAIN, {})

    fixture = parse("fixtures/hydrabeam-300-rgbw.json")
    channels = fixture.select_mode("42-channel")

    # fixture = parse("fixtures/dj_scan_led.json")
    # channels = fixture.select_mode("Normal")

    # fixture = parse("fixtures/hotbox-rgbw.json")
    # channels = fixture.select_mode("9-channel B")

    # fixture = parse("fixtures/jbled-a7.json")
    # channels = fixture.select_mode("Standard 16bit")

    device = DeviceInfo(
        configuration_url=fixture.config_url,
        model=fixture.short_name,
        identifiers={(DOMAIN, fixture.short_name)},  # TODO use user's name
        name=fixture.name
    )

    entities = create_entities(100, channels, device)

    # log.info(f"The data: {entry.data}")
    # entry.data[DOMAIN]['entities'] = entities
    hass.data[DOMAIN][entry.entry_id] = {
        'entities': entities
    }

    # fixtures_path = data.get(CONF_FIXTURES, {}).get(CONF_FOLDER, DEFAULT_FIXTURES_FOLDER)
    # for (dirpath, dirnames, filenames) in walk(fixtures_path):
    #     for filename in filenames:
    #         parser.parse(fixtures_path + "/" + filename)
    #
    # # This will reload any changes the user made to any YAML configurations.
    # # Called during 'quick reload' or hass.reload_config_entry
    # hass.bus.async_listen("hass.config.entry_updated", reload_configuration_yaml)
    #
    # undo_listener = config_entry.add_update_listener(async_update_options)
    # data[config_entry.entry_id] = {UNDO_UPDATE_LISTENER: undo_listener}

    for platform in PLATFORMS:
        await hass.config_entries.async_forward_entry_setup(entry, platform)

    return True


# async def async_unload_entry(hass, config_entry: ConfigEntry) -> bool:
#     """Unload a config entry."""
#     unload_ok = await hass.config_entries.async_forward_entry_unload(
#         config_entry,
#         PLATFORMS,
#     )
#     data = hass.data[DOMAIN]
#     data[config_entry.entry_id][UNDO_UPDATE_LISTENER]()
#     if unload_ok:
#         data.pop(config_entry.entry_id)
#
#     data.pop(DOMAIN)
#
#     return unload_ok


#
#     print(hass.config_entries.async_entries(DOMAIN))
#
#     # for platform in PLATFORMS:
#     #     hass.async_create_task(
#     #         )
#     #     )
#
#     hass.async_add_job(hass.config_entries.flow.async_init(
#         DOMAIN, context={"source": SOURCE_INTEGRATION_DISCOVERY}, data={}
#     ))
#
#
#
#     return True

#
# platform_config = config.get(DOMAIN)
#
# load_fixtures(hass, platform_config)
#
# entities = []
#
# artnet_config = platform_config.get(CONF_NODE_TYPE_ARTNET)
# if artnet_config:
#     max_fps = artnet_config.get(CONF_MAX_FPS)
#     refresh_interval = artnet_config.get(CONF_REFRESH_EVERY)
#
#     node = ArtNetController(hass, max_fps=max_fps, refresh_every=refresh_interval)
#
#     universes_config = artnet_config.get(CONF_UNIVERSES)
#     for universe_config in universes_config:
#         port_address: PortAddress = next(iter(universe_config.keys()))
#         port_config = next(iter(universe_config.values()))
#
#         universe = node.add_universe(port_address.universe)
#
#         devices_config = port_config.get(CONF_DEVICES)
#         for device_config in devices_config:
#             device_name: str = next(iter(device_config.keys()))
#             fixture_config = next(iter(device_config.values()))
#
#             start_address = fixture_config[CONF_START_ADDRESS]
#             fixture_name = fixture_config[CONF_FIXTURE]
#             mode = fixture_config.get(CONF_MODE)
#
#             fixture = get_fixture(fixture_name)
#
#             new_entities = implement(fixture, device_name, port_address, universe, start_address, mode)
#             entities.extend(new_entities)
#
# hass.data.setdefault(DOMAIN, {})
# hass.data[DOMAIN][HASS_DATA_ENTITIES] = entities
#
# log.info(f"Found {len(entities)} entities")
#
# for platform in PLATFORMS:
#     hass.async_create_task(
#         hass.helpers.discovery.async_load_platform(platform, DOMAIN, {}, config)
#     )

# hass.helpers.discovery.load_platform('sensor', DOMAIN, {}, config)
#
# return True
#
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

DEVICE_CONFIG = \
    vol.Schema(
        {
            vol.Required(CONF_START_ADDRESS): vol.All(vol.Coerce(int), vol.Range(min=0, max=511)),
            vol.Required(CONF_FIXTURE): cv.string,
            vol.Optional(CONF_MODE): vol.Any(None, cv.string)
        }
    )

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_FIXTURES): vol.Schema(
                    {
                        vol.Optional(CONF_FOLDER, default=DEFAULT_FIXTURES_FOLDER): cv.string
                    }
                ),
                vol.Optional(CONF_NODE_TYPE_ARTNET): vol.Schema(
                    {
                        vol.Optional(CONF_MAX_FPS, default=30): vol.All(vol.Coerce(int), vol.Range(min=0, max=43)),
                        vol.Optional(CONF_REFRESH_EVERY, default=0.8): cv.positive_float,

                        vol.Optional(CONF_UNIVERSES): vol.Schema(
                            [{
                                port_address_config: vol.Schema(
                                    {
                                        vol.Optional(CONF_COMPATIBILITY): COMPATIBILITY_SCHEMA,
                                        vol.Required(CONF_DEVICES): vol.Schema(
                                            [{
                                                cv.string: DEVICE_CONFIG
                                            }]
                                        )
                                    }
                                )
                            }],
                        ),

                        # vol.Optional(CONF_TRIGGERS): vol.Schema(
                        #     vol.Optional
                        # )
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
