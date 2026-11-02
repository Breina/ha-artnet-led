import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import EntityPlatform, async_get_platforms

from custom_components.dmx.const import CONF_NODE_ENTITIES, DOMAIN
from custom_components.dmx.entity.node import (
    ArtNetACNPrioritySensor,
    ArtNetBootProcessSensor,
    ArtNetDHCPBinarySensor,
    ArtNetFailsafeStateSensor,
    ArtNetIndicatorStateSensor,
    ArtNetNodeReportSensor,
    ArtNetOnlineBinarySensor,
    ArtNetPortAddressProgrammingAuthoritySensor,
    ArtNetPortInputBinarySensor,
    ArtNetPortMergeModeSelect,
    ArtNetPortOutputBinarySensor,
    ArtNetPortOutputModeSensor,
    ArtNetPortRDMBinarySensor,
    ArtNetPortSACNBinarySensor,
    ArtNetPortUniverseSensor,
    ArtNetRDMBinarySensor,
)
from custom_components.dmx.server import ArtPollReply
from custom_components.dmx.server.artnet_server import Node

log = logging.getLogger(__name__)


class DynamicNodeHandler:
    """Handler for dynamically discovered ArtNet nodes."""

    def __init__(self, hass: HomeAssistant, entry: config_entries.ConfigEntry[dict[str, Any]], controller: Any) -> None:
        """Initialize the dynamic node handler."""
        self.hass = hass
        self.entry = entry
        self.controller = controller
        self.discovered_nodes: dict[str, Any] = {}  # Track discovered nodes by IP

    async def handle_new_node(self, artpoll_reply: ArtPollReply) -> None:
        """Handle a newly discovered ArtNet node."""
        unique_id = f"{artpoll_reply.mac_address!r}{artpoll_reply.bind_index}"

        if unique_id in self.discovered_nodes:
            log.debug(f"Node {artpoll_reply.short_name} is back")
            await self.update_node(artpoll_reply)
            return

        log.info(f"Discovered new ArtNet node: {artpoll_reply.short_name}, creating entities")

        # Track this node to avoid duplicate processing
        self.discovered_nodes[unique_id] = artpoll_reply

        # Create a device for this node
        device_info = DeviceInfo(
            identifiers={(DOMAIN, f"artnet_node_{unique_id}")},
            name=artpoll_reply.short_name,
            manufacturer=f"ESTA ID: {artpoll_reply.esta:04x}" if artpoll_reply.esta else "Unknown",
            model=artpoll_reply.long_name,
            sw_version=f"{artpoll_reply.firmware_version}",
            connections={("mac", ":".join(f"{b:02x}" for b in artpoll_reply.mac_address))},
        )

        if artpoll_reply.supports_web_browser_configuration:
            device_info["configuration_url"] = f"http://{'.'.join(str(b) for b in artpoll_reply.source_ip)}/"

        entities: list[Any] = []

        entities.append(ArtNetOnlineBinarySensor(artpoll_reply, device_info))
        entities.append(ArtNetIndicatorStateSensor(artpoll_reply, device_info))
        entities.append(ArtNetBootProcessSensor(artpoll_reply, device_info))
        entities.append(ArtNetRDMBinarySensor(artpoll_reply, device_info))
        entities.append(ArtNetDHCPBinarySensor(artpoll_reply, device_info))
        entities.append(ArtNetFailsafeStateSensor(artpoll_reply, device_info))
        entities.append(ArtNetACNPrioritySensor(artpoll_reply, device_info))
        entities.append(ArtNetNodeReportSensor(artpoll_reply, device_info))
        entities.append(ArtNetPortAddressProgrammingAuthoritySensor(artpoll_reply, device_info))

        for i, port in enumerate(artpoll_reply.ports):
            if port.input or port.output:  # Only add entities for valid ports
                entities.append(ArtNetPortInputBinarySensor(artpoll_reply, device_info, i))
                entities.append(ArtNetPortUniverseSensor(artpoll_reply, device_info, i, True))

                entities.append(ArtNetPortOutputBinarySensor(artpoll_reply, device_info, i))
                entities.append(ArtNetPortUniverseSensor(artpoll_reply, device_info, i, False))
                entities.append(ArtNetPortMergeModeSelect(artpoll_reply, device_info, i))
                entities.append(ArtNetPortSACNBinarySensor(artpoll_reply, device_info, i))
                entities.append(ArtNetPortRDMBinarySensor(artpoll_reply, device_info, i))
                entities.append(ArtNetPortOutputModeSensor(artpoll_reply, device_info, i))

        if entities:
            await self._add_entities(entities)
        else:
            log.warning(f"No entities created for node {artpoll_reply.short_name}")

    async def update_node(self, artpoll_reply: ArtPollReply) -> None:
        """Update an existing ArtNet node with new ArtPollReply data."""
        unique_id = f"{artpoll_reply.mac_address!r}{artpoll_reply.bind_index}"

        if unique_id not in self.discovered_nodes:
            return

        self.discovered_nodes[unique_id] = artpoll_reply

        for entity in self._node_entities():
            # Entities that are disabled in the registry never get added to hass.
            if entity.hass is not None and await entity.update_from_artpoll_reply(artpoll_reply):
                entity.async_schedule_update_ha_state()

        log.debug(f"Updated ArtNet node: {artpoll_reply.long_name}")

    async def handle_lost_node(self, node: Node) -> None:
        """Mark the entities of a node that stopped answering as offline, until we hear from it again."""
        mac_address = ":".join(f"{b:02x}" for b in node.mac_address)

        for entity in self._node_entities():
            if entity._mac_address == mac_address and entity.art_poll_reply.bind_index == node.bind_index:
                entity.set_offline()
                if entity.hass is not None:
                    entity.async_schedule_update_ha_state()

    def _node_entities(self) -> list[Any]:
        entities: list[Any] = self.hass.data[DOMAIN][self.entry.entry_id].get(CONF_NODE_ENTITIES, [])
        return entities

    async def _add_entities(self, entities: list[Any]) -> None:
        """Add entities to Home Assistant."""
        platforms: list[EntityPlatform] = list(async_get_platforms(self.hass, DOMAIN))

        for platform in platforms:
            platform_entities = [e for e in entities if e.platform_type == platform.domain]
            if platform_entities:
                log.debug(f"Adding {len(platform_entities)} entities to {platform.domain}")
                await platform.async_add_entities(platform_entities)

        if CONF_NODE_ENTITIES not in self.hass.data[DOMAIN][self.entry.entry_id]:
            self.hass.data[DOMAIN][self.entry.entry_id][CONF_NODE_ENTITIES] = []

        self.hass.data[DOMAIN][self.entry.entry_id][CONF_NODE_ENTITIES].extend(entities)
