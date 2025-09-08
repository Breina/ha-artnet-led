"""ARTNET LED"""
import json
import logging
import os
from pathlib import Path
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.light import ATTR_TRANSITION
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_MODE, Platform, CONF_SOURCE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import IntegrationError
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.helpers.typing import ConfigType

from custom_components.dmx.const import DOMAIN, HASS_DATA_ENTITIES, ARTNET_CONTROLLER, CONF_DATA, CONF_FIXTURE_ENTITIES
from custom_components.dmx.fixture.delegator import create_entities
from custom_components.dmx.fixture.fixture import Fixture
from custom_components.dmx.fixture.parser import parse_async
from custom_components.dmx.io.dmx_io import DmxUniverse
from custom_components.dmx.server import PortAddress, ArtPollReply
from custom_components.dmx.server.artnet_server import ArtNetServer, Node, ManualNode
from custom_components.dmx.server.sacn_server import SacnServer, SacnServerConfig, create_sacn_receiver
from custom_components.dmx.util.rate_limiter import RateLimiter
from custom_components.dmx.util.entity_cleanup import cleanup_obsolete_entities, store_fixture_fingerprints
from custom_components.dmx.util.fixture_fingerprint import generate_fixture_fingerprint

log = logging.getLogger(__name__)

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
CONF_FOLDER_DEFAULT = 'fixtures'
CONF_ENTITY_ID_PREFIX = 'entity_id_prefix'

PLATFORMS = [Platform.NUMBER, Platform.SELECT, Platform.LIGHT, Platform.SWITCH, Platform.BINARY_SENSOR, Platform.SENSOR]

FIXTURES = {}


class UnknownFixtureError(IntegrationError):
    def __init__(self, desired_fixture: str, discovered_fixtures: list[str], *args: object) -> None:
        super().__init__(*args)
        self._fixture = desired_fixture
        self._discovered_fixtures = discovered_fixtures

    def __str__(self) -> str:
        if not self._discovered_fixtures:
            return "Didn't discover any fixtures. Put them in the fixtures folder as defined by " \
                   "config `dmx.fixtures.folder`"
        else:
            return f"Could not find any fixture named '{self._fixture}, should be one of {self._discovered_fixtures}'. " \
                   f"Note that first the fixture's `fixtureKey` is matched, if that's not " \
                   f"available `shortName`, or finally `name`."


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

    return True


async def process_fixtures(hass: HomeAssistant, fixture_folder: str) -> dict[str, Fixture]:
    fixture_map = {}

    if not os.path.isdir(fixture_folder):
        log.warning(f"Fixture folder does not exist: {fixture_folder}")
        return fixture_map

    file_list = await hass.async_add_executor_job(os.listdir, fixture_folder)

    for filename in file_list:
        if not filename.endswith('.json'):
            continue

        file_path = os.path.join(fixture_folder, filename)

        try:
            fixture = await parse_async(file_path, hass)
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
    fixture_folder = fixtures_yaml.get(CONF_FOLDER, CONF_FOLDER_DEFAULT)

    log.debug("Processing fixtures folder: %s/...", str(Path(fixture_folder).absolute()))
    processed_fixtures = await process_fixtures(hass, fixture_folder)
    log.debug("Found %d fixtures", len(processed_fixtures))

    entities: list[Entity] = []
    universes: dict[PortAddress, DmxUniverse] = {}
    sacn_server = None
    sacn_receiver = None
    
    # Track fixture fingerprints for change detection
    device_fingerprints: dict[str, str] = {}

    # Initialize sACN server if configured
    if (sacn_yaml := dmx_yaml.get(CONF_NODE_TYPE_SACN)) is not None:
        sacn_config = SacnServerConfig(
            source_name=sacn_yaml.get(CONF_SOURCE_NAME, CONF_SOURCE_NAME_DEFAULT),
            priority=sacn_yaml.get(CONF_PRIORITY, CONF_PRIORITY_DEFAULT),
            sync_address=sacn_yaml.get(CONF_SYNC_ADDRESS, 0),
            multicast_ttl=sacn_yaml.get(CONF_MULTICAST_TTL, CONF_MULTICAST_TTL_DEFAULT),
            enable_preview_data=sacn_yaml.get(CONF_ENABLE_PREVIEW_DATA, False)
        )
        
        sacn_server = SacnServer(hass, sacn_config)
        sacn_server.start_server()
        log.info(f"sACN server started with source name: {sacn_config.source_name}")

        animation_yaml = dmx_yaml.get(CONF_ANIMATION, {})
        max_fps = animation_yaml.get(CONF_MAX_FPS, CONF_MAX_FPS_DEFAULT)
        rate_limit = sacn_yaml.get(CONF_RATE_LIMIT, CONF_RATE_LIMIT_DEFAULT)
        sacn_universe_rate_limiters = {}

        # Function to process sACN universe updates with rate limiting
        def sacn_state_callback(port_address: PortAddress, data: bytearray, source: str | None = None):
            log.debug(f"sACN state callback triggered for {port_address} from source '{source}' with {len(data)} channels")
            
            callback_universe: DmxUniverse = universes.get(port_address)
            if callback_universe is None:
                log.warning(f"Received sACN data for unknown universe: {port_address}")
                return

            if port_address not in sacn_universe_rate_limiters:
                updates_dict = {}

                async def process_updates():
                    nonlocal updates_dict
                    updates_to_process = updates_dict.copy()
                    updates_dict.clear()

                    if updates_to_process:
                        log.debug(f"Processing {len(updates_to_process)} sACN channel updates for {port_address}")
                        await callback_universe.update_multiple_values(updates_to_process, source, send_update=False)

                limiter = RateLimiter(
                    hass,
                    update_method=lambda: hass.async_create_task(process_updates()),
                    update_interval=rate_limit,
                    force_update_after=rate_limit * 4
                )

                sacn_universe_rate_limiters[port_address] = (limiter, updates_dict)

            limiter, updates_dict = sacn_universe_rate_limiters[port_address]

            changes_detected = False

            for channel, value in enumerate(data, start=1):  # DMX channels are 1-based
                if value > 0 or callback_universe.get_channel_value(channel) != value:
                    updates_dict[channel] = value
                    changes_detected = True

            if changes_detected:
                log.debug(f"Detected changes in {len([k for k, v in updates_dict.items()])} channels for {port_address}")
                limiter.schedule_update()
            else:
                log.debug(f"No changes detected for {port_address}")

        # Create sACN receiver for incoming multicast data
        sacn_receiver = await create_sacn_receiver(hass, sacn_state_callback, sacn_config.source_name)
        log.info("sACN receiver started for multicast reception")

        # Process sACN universes and devices
        for universe_dict in sacn_yaml[CONF_UNIVERSES]:
            (universe_value, universe_yaml), = universe_dict.items()
            universe_id = int(universe_value)
            
            # Handle unicast addresses if configured
            unicast_addresses = []
            if (compatibility_yaml := universe_yaml.get(CONF_COMPATIBILITY)) is not None:
                if (unicast_yaml := compatibility_yaml.get(CONF_UNICAST_ADDRESSES)) is not None:
                    for unicast_yaml_item in unicast_yaml:
                        unicast_addresses.append({
                            'host': unicast_yaml_item[CONF_HOST],
                            'port': unicast_yaml_item.get(CONF_PORT, 5568)
                        })
            
            port_address = PortAddress(0, 0, universe_id if universe_id <= 511 else universe_id % 512)
            
            # Add universe to sACN server with unicast addresses
            sacn_server.add_universe(universe_id, unicast_addresses)
            
            # Subscribe receiver to this universe for incoming multicast data
            sacn_receiver.subscribe_universe(universe_id)
            log.info(f"Subscribed sACN receiver to universe {universe_id}")
            
            # Create universe with sACN support, passing the actual sACN universe ID
            universe = DmxUniverse(port_address, None, True, sacn_server, universe_id, hass, max_fps)
            universes[port_address] = universe
            
            # Process devices for this sACN universe
            devices_yaml = universe_yaml[CONF_DEVICES]
            for device_dict in devices_yaml:
                (device_name, device_yaml), = device_dict.items()

                start_address = device_yaml[CONF_START_ADDRESS]
                fixture_name = device_yaml[CONF_FIXTURE]
                mode = device_yaml.get(CONF_MODE)
                entity_id_prefix = device_yaml.get(CONF_ENTITY_ID_PREFIX)

                if fixture_name not in processed_fixtures:
                    log.warning("Could not find fixture '%s'. Ignoring device %s", fixture_name, device_name)
                    continue

                fixture = processed_fixtures[fixture_name]
                if not mode:
                    assert len(fixture.modes) > 0
                    mode = next(iter(fixture.modes.keys()))

                channels = fixture.select_mode(mode)
                
                fixture_fingerprint = generate_fixture_fingerprint(fixture_name, mode, channels)
                device_fingerprints[device_name] = fixture_fingerprint

                identifiers = {(DOMAIN, device_name)}
                if entity_id_prefix is not None:
                    identifiers.add((DOMAIN, f"{entity_id_prefix}_{device_name}"))

                device = DeviceInfo(
                    configuration_url=fixture.config_url,
                    model=fixture.name,
                    identifiers=identifiers,
                    name=device_name,
                )

                entities.extend(create_entities(device_name, start_address, channels, device, universe, entity_id_prefix, fixture_name, mode))

    if (artnet_yaml := dmx_yaml.get(CONF_NODE_TYPE_ARTNET)) is not None:

        animation_yaml = dmx_yaml.get(CONF_ANIMATION, {})
        max_fps = animation_yaml.get(CONF_MAX_FPS, CONF_MAX_FPS_DEFAULT)
        refresh_every = artnet_yaml.get(CONF_REFRESH_EVERY, CONF_REFRESH_EVERY_DEFAULT)
        rate_limit = artnet_yaml.get(CONF_RATE_LIMIT, CONF_RATE_LIMIT_DEFAULT)

        universe_rate_limiters = {}

        # Function to process universe updates with rate limiting
        def state_callback(port_address: PortAddress, data: bytearray, source: str | None = None):
            callback_universe: DmxUniverse = universes.get(port_address)
            if callback_universe is None:
                log.warning(f"Received DMX data for unknown universe: {port_address}")
                return

            if port_address not in universe_rate_limiters:
                updates_dict = {}

                async def process_updates():
                    nonlocal updates_dict
                    updates_to_process = updates_dict.copy()
                    updates_dict.clear()

                    if updates_to_process:
                        await callback_universe.update_multiple_values(updates_to_process, source, send_update=False)

                limiter = RateLimiter(
                    hass,
                    update_method=lambda: hass.async_create_task(process_updates()),
                    update_interval=rate_limit,
                    force_update_after=rate_limit * 4
                )

                universe_rate_limiters[port_address] = (limiter, updates_dict)

            limiter, updates_dict = universe_rate_limiters[port_address]

            changes_detected = False

            for channel, value in enumerate(data, start=1):  # DMX channels are 1-based
                if value > 0 or callback_universe.get_channel_value(channel) != value:
                    updates_dict[channel] = value
                    changes_detected = True

            if changes_detected:
                limiter.schedule_update()

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
            (universe_value, universe_yaml), = universe_dict.items()
            port_address = PortAddress.parse(int(universe_value))

            if (compatibility_yaml := universe_yaml.get(CONF_COMPATIBILITY)) is not None:
                send_partial_universe = compatibility_yaml[CONF_SEND_PARTIAL_UNIVERSE]
                if (manual_nodes_yaml := compatibility_yaml.get(CONF_MANUAL_NODES)) is not None:
                    for manual_node_yaml in manual_nodes_yaml:
                        controller.add_manual_node(ManualNode(port_address, manual_node_yaml[CONF_HOST], manual_node_yaml[CONF_PORT]))

            else:
                send_partial_universe = True

            universe = DmxUniverse(port_address, controller, send_partial_universe, sacn_server, None, hass, max_fps)
            universes[port_address] = universe

            controller.add_port(port_address)

            devices_yaml = universe_yaml[CONF_DEVICES]
            for device_dict in devices_yaml:
                (device_name, device_yaml), = device_dict.items()

                start_address = device_yaml[CONF_START_ADDRESS]
                fixture_name = device_yaml[CONF_FIXTURE]
                mode = device_yaml.get(CONF_MODE)
                entity_id_prefix = device_yaml.get(CONF_ENTITY_ID_PREFIX)

                if fixture_name not in processed_fixtures:
                    log.warning("Could not find fixture '%s'. Ignoring device %s", fixture_name, device_name)
                    continue

                fixture = processed_fixtures[fixture_name]
                if not mode:
                    assert len(fixture.modes) > 0
                    mode = next(iter(fixture.modes.keys()))

                channels = fixture.select_mode(mode)
                
                fixture_fingerprint = generate_fixture_fingerprint(fixture_name, mode, channels)
                device_fingerprints[device_name] = fixture_fingerprint

                identifiers = {(DOMAIN, device_name)}
                if entity_id_prefix is not None:
                    identifiers.add((DOMAIN, f"{entity_id_prefix}_{device_name}"))

                device = DeviceInfo(
                    configuration_url=fixture.config_url,
                    model=fixture.name,
                    identifiers=identifiers,
                    name=device_name,
                )

                entities.extend(create_entities(device_name, start_address, channels, device, universe, entity_id_prefix, fixture_name, mode))

        controller.start_server()

    await cleanup_obsolete_entities(hass, entry, device_fingerprints)
    
    hass.data[DOMAIN][entry.entry_id] = {
        CONF_FIXTURE_ENTITIES: entities,
        "universes": universes
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    await store_fixture_fingerprints(hass, entry, device_fingerprints)
    
    return True


ARTNET_COMPATIBILITY_SCHEMA = \
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

SACN_COMPATIBILITY_SCHEMA = \
    vol.Schema(
        {
            vol.Optional(CONF_UNICAST_ADDRESSES): vol.Schema(
                [{
                    vol.Required(CONF_HOST): cv.string,
                    vol.Optional(CONF_PORT, default=5568): cv.port
                }]
            )
        }
    )

DEVICE_CONFIG = \
    vol.Schema(
        {
            vol.Required(CONF_START_ADDRESS): vol.All(vol.Coerce(int), vol.Range(min=0, max=511)),
            vol.Required(CONF_FIXTURE): cv.string,
            vol.Optional(CONF_MODE): vol.Any(None, cv.string),
            vol.Optional(CONF_ENTITY_ID_PREFIX): vol.Any(None, cv.string)
        }
    )

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_FIXTURES): vol.Schema(
                    {
                        vol.Optional(CONF_FOLDER, default=CONF_FOLDER_DEFAULT): cv.string
                    }
                ),
                vol.Optional(CONF_ANIMATION): vol.Schema(
                    {
                        vol.Optional(CONF_MAX_FPS, default=CONF_MAX_FPS_DEFAULT): vol.All(vol.Coerce(int), vol.Range(min=1, max=43))
                    }
                ),
                # TODO add ArtNet server name configuration
                vol.Optional(CONF_NODE_TYPE_ARTNET): vol.Schema(
                    {
                        vol.Optional(CONF_REFRESH_EVERY, default=CONF_REFRESH_EVERY_DEFAULT): cv.positive_float,
                        vol.Optional(CONF_RATE_LIMIT, default=CONF_RATE_LIMIT_DEFAULT): cv.positive_float,

                        vol.Required(CONF_UNIVERSES): vol.Schema(
                            [{
                                port_address_config: vol.Schema(
                                    {
                                        vol.Optional(CONF_COMPATIBILITY): ARTNET_COMPATIBILITY_SCHEMA,
                                        vol.Required(CONF_DEVICES): vol.Schema(
                                            [{
                                                cv.string: DEVICE_CONFIG
                                            }]
                                        )
                                    }
                                )
                            }]
                        )
                    }
                ),
                vol.Optional(CONF_NODE_TYPE_SACN): vol.Schema(
                    {
                        vol.Optional(CONF_SOURCE_NAME, default=CONF_SOURCE_NAME_DEFAULT): cv.string,
                        vol.Optional(CONF_PRIORITY, default=CONF_PRIORITY_DEFAULT): vol.All(vol.Coerce(int), vol.Range(min=0, max=200)),
                        vol.Optional(CONF_SYNC_ADDRESS, default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=63999)),
                        vol.Optional(CONF_MULTICAST_TTL, default=CONF_MULTICAST_TTL_DEFAULT): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
                        vol.Optional(CONF_ENABLE_PREVIEW_DATA, default=False): cv.boolean,
                        vol.Optional(CONF_RATE_LIMIT, default=CONF_RATE_LIMIT_DEFAULT): cv.positive_float,

                        vol.Required(CONF_UNIVERSES): vol.Schema(
                            [{
                                vol.All(vol.Coerce(int), vol.Range(min=1, max=63999)): vol.Schema(
                                    {
                                        vol.Optional(CONF_COMPATIBILITY): SACN_COMPATIBILITY_SCHEMA,
                                        vol.Required(CONF_DEVICES): vol.Schema(
                                            [{
                                                cv.string: DEVICE_CONFIG
                                            }]
                                        )
                                    }
                                )
                            }]
                        )
                    }
                )
            },
            extra=vol.ALLOW_EXTRA
        )
    },
    extra=vol.ALLOW_EXTRA
)
