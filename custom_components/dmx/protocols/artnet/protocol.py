"""Art-Net protocol implementation."""

import logging
from collections.abc import Callable
from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from custom_components.dmx.io.dmx_io import DmxUniverse
from custom_components.dmx.protocols.base import ProtocolServer, UniverseConfig
from custom_components.dmx.server import ArtPollReply, PortAddress
from custom_components.dmx.server.artnet_server import ArtNetServer, ManualNode, Node
from custom_components.dmx.setup.config_processor import (
    CONF_ANIMATION,
    CONF_MANUAL_NODES,
    CONF_MAX_FPS,
    CONF_MAX_FPS_DEFAULT,
    CONF_RATE_LIMIT,
    CONF_RATE_LIMIT_DEFAULT,
    CONF_REFRESH_EVERY,
    CONF_REFRESH_EVERY_DEFAULT,
    CONF_SEND_PARTIAL_UNIVERSE,
    CONF_UNIVERSES,
)
from custom_components.dmx.util.rate_limiter import RateLimiter

log = logging.getLogger(__name__)


class ArtNetProtocol(ProtocolServer):
    """Art-Net protocol server implementation."""

    def __init__(self, hass: HomeAssistant, entry: config_entries.ConfigEntry[dict[str, Any]]):
        super().__init__(hass, entry)
        self.controller: ArtNetServer | None = None
        self._rate_limit = CONF_RATE_LIMIT_DEFAULT
        self._universe_rate_limiters: dict[PortAddress, tuple[RateLimiter, dict[int, int]]] = {}

    @property
    def protocol_name(self) -> str:
        """Return the protocol name."""
        return "Art-Net"

    async def setup(self, config: dict[str, Any]) -> None:
        """Setup the Art-Net server."""
        refresh_every = config.get(CONF_REFRESH_EVERY, CONF_REFRESH_EVERY_DEFAULT)
        self._rate_limit = config.get(CONF_RATE_LIMIT, CONF_RATE_LIMIT_DEFAULT)

        # Create the controller with callback
        state_callback = self.create_state_callback(self._rate_limit)
        self.controller = ArtNetServer(self.hass, state_callback, retransmit_time_ms=refresh_every * 1000)

        # Setup node handlers
        self._setup_node_handlers()

        # Process universes
        for universe_dict in config[CONF_UNIVERSES]:
            ((universe_value, universe_yaml),) = universe_dict.items()
            universe_config = UniverseConfig(int(universe_value), universe_yaml)
            self.add_universe(universe_config)

    def _setup_node_handlers(self) -> None:
        """Setup Art-Net node event handlers."""
        if not self.controller:
            return

        def _get_node_handler() -> type[Any]:
            from custom_components.dmx.entity.node_handler import DynamicNodeHandler

            return DynamicNodeHandler

        dynamic_node_handler = _get_node_handler()
        node_handler = dynamic_node_handler(self.hass, self.entry, self.controller)

        def node_new_callback(artpoll_reply: ArtPollReply) -> None:
            self.hass.async_create_task(node_handler.handle_new_node(artpoll_reply))

        self.controller.node_new_callback = node_new_callback

        def node_update_callback(artpoll_reply: ArtPollReply) -> None:
            self.hass.async_create_task(node_handler.update_node(artpoll_reply))

        self.controller.node_update_callback = node_update_callback

        def node_lost_callback(node: Node) -> None:
            self.hass.async_create_task(node_handler.disable_node(node))

        self.controller.node_lost_callback = node_lost_callback

    def start_server(self) -> None:
        """Start the Art-Net server."""
        if self.controller:
            self.controller.start_server()
            log.info("Art-Net server started")

    def stop_server(self) -> None:
        """Stop the Art-Net server."""
        if self.controller:
            # Art-Net server doesn't have an explicit stop method in the current implementation
            log.info("Art-Net server stopped")

    def add_universe(self, universe_config: UniverseConfig | dict[str, Any]) -> DmxUniverse:
        """Add a universe to the Art-Net server."""
        if not self.controller:
            raise RuntimeError("Controller not initialized")

        if isinstance(universe_config, dict):
            universe_value, universe_yaml = next(iter(universe_config.items()))
            universe_config = UniverseConfig(int(universe_value), universe_yaml)

        port_address = PortAddress.parse(universe_config.universe_id)

        # Handle compatibility settings
        compatibility_yaml = universe_config.compatibility
        if compatibility_yaml:
            send_partial_universe = compatibility_yaml.get(CONF_SEND_PARTIAL_UNIVERSE, True)
            if manual_nodes_yaml := compatibility_yaml.get(CONF_MANUAL_NODES):
                for manual_node_yaml in manual_nodes_yaml:
                    self.controller.add_manual_node(
                        ManualNode(port_address, manual_node_yaml[CONF_HOST], manual_node_yaml[CONF_PORT])
                    )
        else:
            send_partial_universe = True

        # Get animation config for max_fps
        animation_yaml = self.entry.data.get("dmx", {}).get(CONF_ANIMATION, {})
        max_fps = animation_yaml.get(CONF_MAX_FPS, CONF_MAX_FPS_DEFAULT)

        # Create the universe
        universe = DmxUniverse(port_address, self.controller, send_partial_universe, None, None, self.hass, max_fps)
        self.universes[port_address] = universe

        self.controller.add_port(port_address)
        return universe

    def create_state_callback(self, rate_limit: float) -> Callable[[PortAddress, bytearray, str | None], None]:
        """Create a callback function for handling Art-Net DMX data updates."""

        def state_callback(port_address: PortAddress, data: bytearray, source: str | None = None) -> None:
            callback_universe = self.universes.get(port_address)
            if callback_universe is None:
                log.warning(f"Received DMX data for unknown universe: {port_address}")
                return

            if port_address not in self._universe_rate_limiters:
                updates_dict: dict[int, int] = {}

                async def process_updates() -> None:
                    nonlocal updates_dict
                    updates_to_process = updates_dict.copy()
                    updates_dict.clear()

                    if updates_to_process:
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
                limiter.schedule_update()

        return state_callback

    def get_controller(self) -> ArtNetServer | None:
        """Get the Art-Net controller instance."""
        return self.controller
