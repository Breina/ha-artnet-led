"""sACN (E1.31) protocol implementation."""

import asyncio
import logging
import time
from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from custom_components.dmx.io.dmx_io import DmxUniverse
from custom_components.dmx.protocols.base import ProtocolServer, UniverseConfig
from custom_components.dmx.server import PortAddress
from custom_components.dmx.server.sacn_merge import SacnMerger
from custom_components.dmx.server.sacn_packet import SacnPacket
from custom_components.dmx.server.sacn_server import SacnReceiver, SacnServer, SacnServerConfig, create_sacn_receiver
from custom_components.dmx.setup.config_processor import (
    CONF_ANIMATION,
    CONF_ENABLE_PREVIEW_DATA,
    CONF_INTERFACE_IP,
    CONF_MAX_FPS,
    CONF_MAX_FPS_DEFAULT,
    CONF_MULTICAST_TTL,
    CONF_MULTICAST_TTL_DEFAULT,
    CONF_PRIORITY,
    CONF_PRIORITY_DEFAULT,
    CONF_RATE_LIMIT,
    CONF_RATE_LIMIT_DEFAULT,
    CONF_REFRESH_EVERY,
    CONF_REFRESH_EVERY_DEFAULT,
    CONF_SOURCE_NAME,
    CONF_SOURCE_NAME_DEFAULT,
    CONF_SYNC_ADDRESS,
    CONF_UNICAST_ADDRESSES,
    CONF_UNIVERSES,
)
from custom_components.dmx.util.rate_limiter import RateLimiter

log = logging.getLogger(__name__)

SOURCE_CHECK_INTERVAL = 0.5
"""Seconds between checks for what happens by remote sources staying silent, such as being lost."""


class _ReceivingUniverse:
    """What's kept per universe to merge what's being received into it."""

    def __init__(self, universe: DmxUniverse, limiter: RateLimiter, merger: SacnMerger) -> None:
        self.universe = universe
        self.limiter = limiter
        self.merger = merger


class SacnProtocol(ProtocolServer):
    """sACN (E1.31) protocol server implementation."""

    def __init__(self, hass: HomeAssistant, entry: config_entries.ConfigEntry[dict[str, Any]]):
        super().__init__(hass, entry)
        self.sacn_server: SacnServer | None = None
        self.sacn_receiver: SacnReceiver | None = None
        self._config: SacnServerConfig | None = None
        self._rate_limit = CONF_RATE_LIMIT_DEFAULT
        self._receiving: dict[int, _ReceivingUniverse] = {}
        self._source_watcher: asyncio.Task[None] | None = None

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
            interface_ip=config.get(CONF_INTERFACE_IP),
            multicast_ttl=config.get(CONF_MULTICAST_TTL, CONF_MULTICAST_TTL_DEFAULT),
            enable_preview_data=config.get(CONF_ENABLE_PREVIEW_DATA, False),
            retransmit_interval=config.get(CONF_REFRESH_EVERY, CONF_REFRESH_EVERY_DEFAULT),
        )

        self._rate_limit = config.get(CONF_RATE_LIMIT, CONF_RATE_LIMIT_DEFAULT)

        # Create sACN server and receiver
        self.sacn_server = SacnServer(self.hass, self._config)
        self.sacn_server.start_server()

        self.sacn_receiver = await create_sacn_receiver(
            self.hass, self._handle_packet, self._config.cid, self._config.interface_ip
        )
        self._source_watcher = self.hass.async_create_background_task(
            self._watch_sources(), name="sACN remote source watcher"
        )

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
        if self._source_watcher:
            self._source_watcher.cancel()
            self._source_watcher = None

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

        merger = SacnMerger()

        def update_callback() -> None:
            self.hass.async_create_task(universe.set_received(merger.merge()))

        limiter = RateLimiter(
            self.hass,
            update_method=update_callback,
            update_interval=self._rate_limit,
            force_update_after=self._rate_limit * 4,
        )
        self._receiving[universe_id] = _ReceivingUniverse(universe, limiter, merger)

        return universe

    def _handle_packet(self, packet: SacnPacket) -> None:
        receiving = self._receiving.get(packet.universe)
        if receiving is None:
            log.warning(f"Received sACN data for unknown universe: {packet.universe}")
            return

        if receiving.merger.handle_packet(packet, time.monotonic()):
            receiving.limiter.schedule_update()

    async def _watch_sources(self) -> None:
        while True:
            await asyncio.sleep(SOURCE_CHECK_INTERVAL)
            now = time.monotonic()
            for receiving in self._receiving.values():
                if receiving.merger.expire(now):
                    receiving.limiter.schedule_update()

    def get_sacn_server(self) -> SacnServer | None:
        """Get the sACN server instance."""
        return self.sacn_server

    def get_sacn_receiver(self) -> SacnReceiver | None:
        """Get the sACN receiver instance."""
        return self.sacn_receiver
