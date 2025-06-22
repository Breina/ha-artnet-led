import logging
from typing import Dict, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.helpers.entity_registry import RegistryEntryDisabler

from custom_components.dmx import ArtPollReply, DOMAIN, Node
from custom_components.dmx.const import CONF_NODE_ENTITIES
from custom_components.dmx.entity.node import ArtNetOnlineBinarySensor, ArtNetIndicatorStateSensor, ArtNetBootProcessSensor, ArtNetRDMBinarySensor, ArtNetDHCPBinarySensor, \
    ArtNetFailsafeStateSensor, ArtNetACNPrioritySensor, ArtNetNodeReportSensor, ArtNetPortAddressProgrammingAuthoritySensor, ArtNetPortInputBinarySensor, \
    ArtNetPortUniverseSensor, ArtNetPortOutputBinarySensor, ArtNetPortMergeModeSelect, ArtNetPortSACNBinarySensor, ArtNetPortRDMBinarySensor, ArtNetPortOutputModeSensor

log = logging.getLogger(__name__)


class DynamicNodeHandler:
    """Handler for dynamically discovered ArtNet nodes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, controller) -> None:
        """Initialize the dynamic node handler."""
        self.hass = hass
        self.entry = entry
        self.controller = controller
        self.discovered_nodes: Dict[str, Any] = {}  # Track discovered nodes by IP

    async def handle_new_node(self, artpoll_reply: ArtPollReply) -> None:
        """Handle a newly discovered ArtNet node."""
        unique_id = f"{artpoll_reply.mac_address}{artpoll_reply.bind_index}"

        if unique_id in self.discovered_nodes:
            # Previously disabled, but found again
            await self.reenable_node(artpoll_reply)
            return

        log.info(f"Discovered new ArtNet node: {artpoll_reply.short_name}")

        # Track this node to avoid duplicate processing
        self.discovered_nodes[unique_id] = artpoll_reply

        # Create a device for this node
        device_info = DeviceInfo(
            identifiers={(DOMAIN, f"artnet_node_{unique_id}")},
            name=artpoll_reply.long_name,
            manufacturer=f"ESTA ID: {artpoll_reply.esta:04x}" if artpoll_reply.esta else "Unknown",
            model=artpoll_reply.long_name,
            sw_version=f"{artpoll_reply.firmware_version}",
            connections={("mac", ":".join(f"{b:02x}" for b in artpoll_reply.mac_address))},
        )

        if artpoll_reply.supports_web_browser_configuration:
            device_info['configuration_url'] = f"http://{'.'.join(map(str, artpoll_reply.source_ip))}/"

        entities = []

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

    async def update_node(self, artpoll_reply: ArtPollReply) -> None:
        """Update an existing ArtNet node with new ArtPollReply data."""
        unique_id = f"{artpoll_reply.mac_address}{artpoll_reply.bind_index}"

        if unique_id not in self.discovered_nodes:
            return

        self.discovered_nodes[unique_id] = artpoll_reply

        if CONF_NODE_ENTITIES in self.hass.data[DOMAIN][self.entry.entry_id]:
            entities = self.hass.data[DOMAIN][self.entry.entry_id][CONF_NODE_ENTITIES]

            mac_string = ":".join(f"{b:02x}" for b in artpoll_reply.mac_address)
            for entity in entities:
                if not hasattr(entity, "hass") or entity.hass is None:
                    log.debug(f"Skipping entity {getattr(entity, 'unique_id', 'unknown')} - not yet initialized")
                    continue

                if (hasattr(entity, "_mac_address") and
                        entity._mac_address == mac_string and
                        hasattr(entity, "art_poll_reply") and
                        entity.art_poll_reply.bind_index == artpoll_reply.bind_index):

                    entity.art_poll_reply = artpoll_reply

                    if hasattr(entity, "async_schedule_update_ha_state"):
                        try:
                            entity.async_schedule_update_ha_state()
                        except Exception as e:
                            log.warning(f"Failed to schedule update for entity {entity.unique_id}: {e}")

        log.debug(f"Updated ArtNet node: {artpoll_reply.long_name}")

    async def disable_node(self, node: Node) -> None:
        unique_id = f"{node.mac_address}{node.bind_index}"

        if unique_id not in self.discovered_nodes:
            return

        entity_reg = er.async_get(self.hass)

        if CONF_NODE_ENTITIES in self.hass.data[DOMAIN][self.entry.entry_id]:
            entities = self.hass.data[DOMAIN][self.entry.entry_id][CONF_NODE_ENTITIES]

            # Find entities belonging to this node and update them
            mac_string = ":".join(f"{b:02x}" for b in node.mac_address)
            for entity in entities:
                # Check if this entity belongs to the node being updated
                if hasattr(entity, "_mac_address") and entity._mac_address == mac_string and \
                        hasattr(entity, "art_poll_reply") and \
                        entity.art_poll_reply.bind_index == node.bind_index:

                    if isinstance(entity, ArtNetOnlineBinarySensor):
                        entity.connected = False

                        if not self.hass:
                            log.debug(f"Not updating {self.controller} because it hasn't been added to hass yet.")

                        elif hasattr(entity, "async_schedule_update_ha_state"):
                            entity.async_schedule_update_ha_state()
                        continue

                    entity_reg.async_update_entity(entity.registry_entry, disabled_by=RegistryEntryDisabler.INTEGRATION)

    async def reenable_node(self, artpoll_reply: ArtPollReply) -> None:
        unique_id = f"{artpoll_reply.mac_address}{artpoll_reply.bind_index}"

        if unique_id not in self.discovered_nodes:
            return

        entity_reg = er.async_get(self.hass)

        if CONF_NODE_ENTITIES in self.hass.data[DOMAIN][self.entry.entry_id]:
            entities = self.hass.data[DOMAIN][self.entry.entry_id][CONF_NODE_ENTITIES]

            # Find entities belonging to this node and update them
            mac_string = ":".join(f"{b:02x}" for b in artpoll_reply.mac_address)
            for entity in entities:
                # Check if this entity belongs to the node being updated
                if hasattr(entity, "_mac_address") and entity._mac_address == mac_string and \
                        hasattr(entity, "art_poll_reply") and \
                        entity.art_poll_reply.bind_index == artpoll_reply.bind_index:

                    if isinstance(entity, ArtNetOnlineBinarySensor):
                        entity.connected = True

                        if not self.hass:
                            log.debug(f"Not updating {self.controller} because it hasn't been added to hass yet.")

                        elif hasattr(entity, "async_schedule_update_ha_state"):
                            entity.async_schedule_update_ha_state()
                        continue

                    entity_reg.async_update_entity(entity.registry_entry, disabled_by=None)

    async def _add_entities(self, entities) -> None:
        """Add entities to Home Assistant."""
        for platform in async_get_platforms(self.hass, DOMAIN):
            platform_entities = [e for e in entities if e.platform_type == platform.domain]
            if platform_entities:
                await platform.async_add_entities(platform_entities)

        if CONF_NODE_ENTITIES not in self.hass.data[DOMAIN][self.entry.entry_id]:
            self.hass.data[DOMAIN][self.entry.entry_id][CONF_NODE_ENTITIES] = []

        self.hass.data[DOMAIN][self.entry.entry_id][CONF_NODE_ENTITIES].extend(entities)
