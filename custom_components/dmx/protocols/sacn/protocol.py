"""sACN (E1.31) protocol implementation."""

import logging
from collections.abc import Callable
from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from custom_components.dmx.io.dmx_io import DmxUniverse
from custom_components.dmx.protocols.base import ProtocolServer, UniverseConfig
from custom_components.dmx.server import PortAddress
from custom_components.dmx.server.sacn_server import SacnReceiver, SacnServer, SacnServerConfig, create_sacn_receiver
from custom_components.dmx.setup.config_processor import (
    CONF_ANIMATION,
    CONF_ENABLE_PREVIEW_DATA,
    CONF_MAX_FPS,
    CONF_MAX_FPS_DEFAULT,
    CONF_MULTICAST_TTL,
    CONF_MULTICAST_TTL_DEFAULT,
    CONF_PRIORITY,
    CONF_PRIORITY_DEFAULT,
    CONF_RATE_LIMIT,
    CONF_RATE_LIMIT_DEFAULT,
    CONF_SOURCE_NAME,
    CONF_SOURCE_NAME_DEFAULT,
    CONF_SYNC_ADDRESS,
    CONF_UNICAST_ADDRESSES,
    CONF_UNIVERSES,
)
from custom_components.dmx.util.rate_limiter import RateLimiter

log = logging.getLogger(__name__)


class SacnProtocol(ProtocolServer):
    """sACN (E1.31) protocol server implementation."""

    def __init__(self, hass: HomeAssistant, entry: config_entries.ConfigEntry[dict[str, Any]]):
        super().__init__(hass, entry)
        self.sacn_server: SacnServer | None = None
        self.sacn_receiver: SacnReceiver | None = None
        self._config: SacnServerConfig | None = None
        self._rate_limit = CONF_RATE_LIMIT_DEFAULT
        self._universe_rate_limiters: dict[PortAddress, tuple[RateLimiter, dict[int, int]]] = {}

    @property
    def protocol_name(self) -> str:
        """Return the protocol name."""
        return "sACN"

    async def setup(self, config: dict[str, Any]) -> None:
        """Setup the sACN server."""
        self._config = SacnServerConfig(
            source_name=config.get(CONF_SOURCE_NAME, CONF_SOURCE_NAME_DEFAULT),
            priority=config.get(CONF_PRIORITY, CONF_PRIORITY_DEFAULT),
            sync_address=config.get(CONF_SYNC_ADDRESS, 0),
            multicast_ttl=config.get(CONF_MULTICAST_TTL, CONF_MULTICAST_TTL_DEFAULT),
            enable_preview_data=config.get(CONF_ENABLE_PREVIEW_DATA, False),
        )

        self._rate_limit = config.get(CONF_RATE_LIMIT, CONF_RATE_LIMIT_DEFAULT)

        # Create sACN server and receiver
        self.sacn_server = SacnServer(self.hass, self._config)
        self.sacn_server.start_server()

        callback_fn = self.create_state_callback(self._rate_limit)
        self.sacn_receiver = await create_sacn_receiver(self.hass, callback_fn, self._config.source_name)

        # Process universes
        for universe_dict in config[CONF_UNIVERSES]:
            ((universe_value, universe_yaml),) = universe_dict.items()
            universe_config = UniverseConfig(int(universe_value), universe_yaml)
            self.add_universe(universe_config)

        log.info(f"sACN server started with source name: {self._config.source_name}")
        log.info("sACN receiver started for multicast reception")

    def start_server(self) -> None:
        """Start the sACN server."""
        if self.sacn_server:
            self.sacn_server.start_server()
            log.info("sACN server started")

    def stop_server(self) -> None:
        """Stop the sACN server."""
        if self.sacn_server:
            # sACN server doesn't have an explicit stop method in the current implementation
            log.info("sACN server stopped")

    def add_universe(self, universe_config: UniverseConfig | dict[str, Any]) -> DmxUniverse:
        """Add a universe to the sACN server."""
        if not self.sacn_server or not self.sacn_receiver:
            raise RuntimeError("sACN server not initialized")

        if isinstance(universe_config, dict):
            universe_value, universe_yaml = next(iter(universe_config.items()))
            universe_config = UniverseConfig(int(universe_value), universe_yaml)

        universe_id = universe_config.universe_id

        # Handle unicast addresses if configured
        unicast_addresses = []
        compatibility_yaml = universe_config.compatibility
        if compatibility_yaml and (unicast_yaml := compatibility_yaml.get(CONF_UNICAST_ADDRESSES)):
            for unicast_yaml_item in unicast_yaml:
                unicast_addresses.append(
                    {"host": unicast_yaml_item[CONF_HOST], "port": unicast_yaml_item.get(CONF_PORT, 5568)}
                )

        port_address = PortAddress(0, 0, universe_id if universe_id <= 511 else universe_id % 512)

        # Add universe to sACN server with unicast addresses
        unicast_hosts = [addr["host"] for addr in unicast_addresses] if unicast_addresses else None
        self.sacn_server.add_universe(universe_id, unicast_hosts)

        # Subscribe receiver to this universe for incoming multicast data
        self.sacn_receiver.subscribe_universe(universe_id)
        log.info(f"Subscribed sACN receiver to universe {universe_id}")

        # Get animation config for max_fps
        animation_yaml = self.entry.data.get("dmx", {}).get(CONF_ANIMATION, {})
        max_fps = animation_yaml.get(CONF_MAX_FPS, CONF_MAX_FPS_DEFAULT)

        # Create universe with sACN support, passing the actual sACN universe ID
        universe = DmxUniverse(port_address, None, True, self.sacn_server, universe_id, self.hass, max_fps)
        self.universes[port_address] = universe

        return universe

    def create_state_callback(self, rate_limit: float) -> Callable[[PortAddress, bytearray, str | None], None]:
        """Create a callback function for handling sACN DMX data updates."""

        def sacn_state_callback(port_address: PortAddress, data: bytearray, source: str | None = None) -> None:
            log.debug(
                f"sACN state callback triggered for {port_address} from source '{source}' with {len(data)} channels"
            )

            callback_universe = self.universes.get(port_address)
            if callback_universe is None:
                log.warning(f"Received sACN data for unknown universe: {port_address}")
                return

            if port_address not in self._universe_rate_limiters:
                updates_dict: dict[int, int] = {}

                async def process_updates() -> None:
                    nonlocal updates_dict
                    updates_to_process = updates_dict.copy()
                    updates_dict.clear()

                    if updates_to_process:
                        log.debug(f"Processing {len(updates_to_process)} sACN channel updates for {port_address}")
                        await callback_universe.update_multiple_values(updates_to_process, source, send_update=False)

                def update_callback() -> None:
                    self.hass.async_create_task(process_updates())

                limiter = RateLimiter(
                    self.hass,
                    update_method=update_callback,
                    update_interval=rate_limit,
                    force_update_after=rate_limit * 4,
                )

                self._universe_rate_limiters[port_address] = (limiter, updates_dict)

            limiter, updates_dict = self._universe_rate_limiters[port_address]

            changes_detected = False

            for channel, value in enumerate(data, start=1):  # DMX channels are 1-based
                if value > 0 or callback_universe.get_channel_value(channel) != value:
                    updates_dict[channel] = value
                    changes_detected = True

            if changes_detected:
                log.debug(
                    f"Detected changes in {len([k for k, v in updates_dict.items()])} channels for {port_address}"
                )
                limiter.schedule_update()
            else:
                log.debug(f"No changes detected for {port_address}")

        return sacn_state_callback

    def get_sacn_server(self) -> SacnServer | None:
        """Get the sACN server instance."""
        return self.sacn_server

    def get_sacn_receiver(self) -> SacnReceiver | None:
        """Get the sACN receiver instance."""
        return self.sacn_receiver
