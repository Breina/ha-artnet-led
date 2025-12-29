"""Server initialization and management using protocol abstraction."""

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.dmx.io.dmx_io import DmxUniverse
from custom_components.dmx.protocols.artnet.protocol import ArtNetProtocol
from custom_components.dmx.protocols.base import ProtocolServer
from custom_components.dmx.protocols.sacn.protocol import SacnProtocol
from custom_components.dmx.server import PortAddress
from custom_components.dmx.setup.config_processor import CONF_NODE_TYPE_ARTNET, CONF_NODE_TYPE_SACN

log = logging.getLogger(__name__)


class ServerManager:
    """Manages protocol servers using the abstraction layer."""

    def __init__(self, hass: HomeAssistant, entry: config_entries.ConfigEntry[dict[str, Any]]):
        self.hass = hass
        self.entry = entry
        self.protocol_servers: dict[str, ProtocolServer] = {}

    async def setup_protocols(self, dmx_yaml: dict[str, Any]) -> None:
        """Setup all configured protocol servers."""

        # Setup sACN protocol if configured
        if (sacn_yaml := dmx_yaml.get(CONF_NODE_TYPE_SACN)) is not None:
            sacn_protocol = SacnProtocol(self.hass, self.entry)
            await sacn_protocol.setup(sacn_yaml)
            self.protocol_servers["sacn"] = sacn_protocol
            log.info("sACN protocol configured")

        # Setup Art-Net protocol if configured
        if (artnet_yaml := dmx_yaml.get(CONF_NODE_TYPE_ARTNET)) is not None:
            artnet_protocol = ArtNetProtocol(self.hass, self.entry)
            await artnet_protocol.setup(artnet_yaml)
            artnet_protocol.start_server()
            self.protocol_servers["artnet"] = artnet_protocol
            log.info("Art-Net protocol configured")

    def get_universes(self) -> dict[PortAddress, DmxUniverse]:
        """Get all universes from all protocol servers."""
        all_universes: dict[PortAddress, DmxUniverse] = {}
        for protocol_server in self.protocol_servers.values():
            all_universes.update(protocol_server.get_universes())
        return all_universes

    def get_protocol_server(self, protocol_name: str) -> ProtocolServer | None:
        """Get a specific protocol server."""
        return self.protocol_servers.get(protocol_name.lower())

    def get_sacn_server(self) -> Any:
        """Get sACN server instance for backward compatibility."""
        sacn_protocol = self.get_protocol_server("sacn")
        if isinstance(sacn_protocol, SacnProtocol):
            return sacn_protocol.get_sacn_server()
        return None

    def get_artnet_controller(self) -> Any:
        """Get Art-Net controller instance for backward compatibility."""
        artnet_protocol = self.get_protocol_server("artnet")
        if isinstance(artnet_protocol, ArtNetProtocol):
            return artnet_protocol.get_controller()
        return None

    def stop_all_servers(self) -> None:
        """Stop all protocol servers."""
        for protocol_server in self.protocol_servers.values():
            try:
                protocol_server.stop_server()
            except Exception as e:
                log.error(f"Error stopping {protocol_server.protocol_name} server: {e}")
        self.protocol_servers.clear()
