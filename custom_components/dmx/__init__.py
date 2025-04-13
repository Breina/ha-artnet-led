"""ARTNET LED"""
import dataclasses
import json
import logging
import os
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
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType

from custom_components.dmx.bridge.artnet_controller import ArtNetController, DiscoveredNode
from custom_components.dmx.client import PortAddress, ArtPollReply
from custom_components.dmx.client.artnet_server import ArtNetServer, Node, ManualNode
from custom_components.dmx.const import DOMAIN, HASS_DATA_ENTITIES, ARTNET_CONTROLLER, CONF_DATA, UNDO_UPDATE_LISTENER
from custom_components.dmx.fixture.fixture import Fixture
from custom_components.dmx.fixture.parser import parse
from custom_components.dmx.fixture_delegator.delegator import create_entities
from custom_components.dmx.io.dmx_io import DmxUniverse
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

PLATFORMS = [Platform.NUMBER, Platform.SELECT, Platform.LIGHT, Platform.SENSOR, Platform.BINARY_SENSOR]

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


def port_address_config(value: Any) -> int:
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
        return PortAddress(0, 0, universe).port_address

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

    return PortAddress(net, sub_net, universe).port_address


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


def process_fixtures(fixture_folder: str) -> dict[str, Fixture]:
    fixture_map = {}

    if not os.path.isdir(fixture_folder):
        log.warning(f"Fixture folder does not exist: {fixture_folder}")
        return fixture_map

    for filename in os.listdir(fixture_folder):
        if not filename.endswith('.json'):
            continue

        file_path = os.path.join(fixture_folder, filename)

        try:
            fixture = parse(file_path)
            fixture_map[fixture.short_name] = fixture

        except json.JSONDecodeError as e:
            log.warning("Invalid JSON in file %s: %s", filename, str(e))
        except Exception as e:
            log.warning("Error processing file %s: %s", filename, str(e))

    return fixture_map


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the component."""

    hass.data.setdefault(DOMAIN, {})

    dmx_yaml = entry.data[DOMAIN]

    fixtures_yaml = dmx_yaml[CONF_FIXTURES]
    fixture_folder = fixtures_yaml[CONF_FOLDER]

    log.debug("Processing fixtures folder: %s/...", fixture_folder)
    fixtures = process_fixtures(fixture_folder)
    log.debug("Found %d fixtures", len(fixtures))

    entities: list[Entity] = []
    universes = {}

    # Process ArtNet
    if (artnet_yaml := dmx_yaml.get(CONF_NODE_TYPE_ARTNET)) is not None:

        max_fps = artnet_yaml[CONF_MAX_FPS]
        refresh_every = artnet_yaml[CONF_REFRESH_EVERY]

        def state_callback(port_address: PortAddress, data: bytearray):
            """
            Callback for incoming ArtNet DMX data.

            Args:
                port_address: The port address (universe) the data is for
                data: The DMX data (512 bytes)
            """
            # Find the corresponding universe
            callback_universe = universes.get(port_address)
            if callback_universe is None:
                log.warning(f"Received DMX data for unknown universe: {port_address}")
                return

            # Update channel values in the universe
            # Only update channels that have a non-zero value or have changed
            for channel, value in enumerate(data, start=1):  # DMX channels are 1-based
                if value > 0 or callback_universe.get_channel_value(channel) != value:
                    hass.async_create_task(callback_universe.update_value(channel, value))

        controller = ArtNetServer(hass, state_callback, retransmit_time_ms=refresh_every * 1000)

        def _get_node_handler():
            from custom_components.dmx.entity.node_handler import DynamicNodeHandler
            return DynamicNodeHandler

        DynamicNodeHandler = _get_node_handler()
        node_handler = DynamicNodeHandler(hass, entry, controller)

        def node_new_callback(artpoll_reply: ArtPollReply):
            hass.async_create_task(node_handler.handle_new_node(artpoll_reply))

        controller.node_new_callback = node_new_callback

        def node_update_callback(artpoll_reply: ArtPollReply):
            hass.async_create_task(node_handler.update_node(artpoll_reply))

        controller.node_update_callback = node_update_callback

        def node_lost_callback(node: Node):
            hass.async_create_task(node_handler.disable_node(node))

        controller.node_lost_callback = node_lost_callback

        for universe_dict in artnet_yaml[CONF_UNIVERSES]:
            (universe_str, universe_yaml), = universe_dict.items()
            port_address = PortAddress.parse(universe_str)

            universe = DmxUniverse(port_address, controller)
            universes[port_address] = universe

            controller.add_port(port_address)

            # manual_nodes: list[ManualNode] = []
            if (compatibility_yaml := universe_yaml.get(CONF_COMPATIBILITY)) is not None:
                send_partial_universe = compatibility_yaml[CONF_SEND_PARTIAL_UNIVERSE]
                if (manual_nodes_yaml := compatibility_yaml.get(CONF_MANUAL_NODES)) is not None:
                    for manual_node_yaml in manual_nodes_yaml:
                        controller.add_manual_node(ManualNode(port_address, manual_node_yaml[CONF_HOST], manual_node_yaml[CONF_PORT]))
                        # manual_nodes.append(ManualNode(manual_node_yaml[CONF_HOST], manual_node_yaml[CONF_PORT]))

            else:
                send_partial_universe = True

            devices_yaml = universe_yaml[CONF_DEVICES]
            for device_dict in devices_yaml:
                (device_name, device_yaml), = device_dict.items()

                start_address = device_yaml[CONF_START_ADDRESS]
                fixture_name = device_yaml[CONF_FIXTURE]
                mode = device_yaml.get(CONF_MODE)

                if fixture_name not in fixtures:
                    log.warning("Could not find fixture '%s'. Ignoring device %s", fixture_name, device_name)
                    continue

                fixture = fixtures[fixture_name]
                if not mode:
                    assert len(fixture.modes) > 0
                    mode = next(iter(fixture.modes.keys()))

                channels = fixture.select_mode(mode)

                device = DeviceInfo(
                    configuration_url=fixture.config_url,
                    model=fixture.name,
                    identifiers={(DOMAIN, device_name)},
                    name=device_name,
                )

                entities.extend(create_entities(device_name, start_address, channels, device, universe))

        controller.start_server()

    hass.data[DOMAIN][entry.entry_id] = {
        'entities': entities
    }

    for platform in PLATFORMS:
        await hass.config_entries.async_forward_entry_setup(entry, platform)

    return True


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

                        vol.Required(CONF_UNIVERSES): vol.Schema(
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
