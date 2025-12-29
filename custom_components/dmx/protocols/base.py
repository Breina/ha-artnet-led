"""Base protocol interface for DMX protocols."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.dmx.io.dmx_io import DmxUniverse
from custom_components.dmx.server import PortAddress


class ProtocolServer(ABC):
    """Abstract base class for DMX protocol servers."""

    def __init__(self, hass: HomeAssistant, entry: config_entries.ConfigEntry[dict[str, Any]]):
        self.hass = hass
        self.entry = entry
        self.universes: dict[PortAddress, DmxUniverse] = {}

    @abstractmethod
    async def setup(self, config: dict[str, Any]) -> None:
        """Setup the protocol server."""

    @abstractmethod
    def start_server(self) -> None:
        """Start the protocol server."""

    @abstractmethod
    def stop_server(self) -> None:
        """Stop the protocol server."""

    @abstractmethod
    def add_universe(self, universe_config: dict[str, Any]) -> DmxUniverse:
        """Add a universe to the server and return the DmxUniverse instance."""

    @abstractmethod
    def create_state_callback(self, rate_limit: float) -> Callable[[PortAddress, bytearray, str | None], None]:
        """Create a callback function for handling DMX data updates."""

    def get_universes(self) -> dict[PortAddress, DmxUniverse]:
        """Get all configured universes."""
        return self.universes

    @property
    @abstractmethod
    def protocol_name(self) -> str:
        """Return the protocol name."""


class UniverseConfig:
    """Configuration for a universe."""

    def __init__(self, universe_id: int, config: dict[str, Any]):
        self.universe_id = universe_id
        self.config = config
        self.devices = config.get("devices", [])
        self.compatibility = config.get("compatibility", {})
