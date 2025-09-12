import asyncio
import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo, Entity

from custom_components.dmx.server import (
    ArtPollReply,
    BootProcess,
    FailsafeState,
    IndicatorState,
    PortAddressProgrammingAuthority,
    StyleCode,
)

_LOGGER = logging.getLogger(__name__)


def bind_index_str(artpoll_reply: ArtPollReply) -> str:
    if artpoll_reply.bind_index == 0:
        return ""
    return f" {artpoll_reply.bind_index}"


class ArtNetEntity(Entity):
    """Representation of an ArtNet entity."""

    def __init__(
        self,
        art_poll_reply: ArtPollReply,
        name: str,
        entity_id_suffix: str,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the entity."""
        super().__init__()
        self.art_poll_reply = art_poll_reply

        # Store immutable IP + bind_index for entity identity verification
        self._source_ip = tuple(art_poll_reply.source_ip)
        self._bind_index = art_poll_reply.bind_index

        # Entity-level lock to prevent concurrent reference updates
        self._update_lock = asyncio.Lock()

        self._attr_name = name
        self._attr_unique_id = f"{self._mac_address}_{art_poll_reply.bind_index}_{entity_id_suffix}"
        self._attr_device_info = device_info

    @property
    def _mac_address(self) -> str:
        """Return MAC address as a string."""
        if hasattr(self.art_poll_reply, "mac_address"):
            mac = self.art_poll_reply.mac_address
            return ":".join(f"{b:02x}" for b in mac)
        return "unknown"

    async def update_from_artpoll_reply(self, new_artpoll_reply: ArtPollReply) -> bool:
        """
        Safely update entity from ArtPollReply with IP + bind_index validation.
        This method handles the common validation and locking, then calls the entity-specific update.
        """
        async with self._update_lock:
            new_source_ip = tuple(new_artpoll_reply.source_ip)
            new_bind_index = new_artpoll_reply.bind_index

            if new_source_ip != self._source_ip or new_bind_index != self._bind_index:
                _LOGGER.debug(
                    f"Entity {self._attr_unique_id} rejected update from "
                    f"IP={new_source_ip}, bind_index={new_bind_index}"
                    f"(expected IP={self._source_ip}, bind_index={self._bind_index})"
                )
                return False

            # Let the entity handle its own value extraction
            self._update_from_artpoll_reply(new_artpoll_reply)
            return True

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """
        Entity-specific method to extract and update values from ArtPollReply.
        Must be implemented by each entity type.
        """
        raise NotImplementedError("Entities must implement _update_from_artpoll_reply")


class ArtNetOnlineBinarySensor(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet device online status."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo) -> None:
        """Initialize the binary sensor."""
        # Store the online status and extra state attributes at creation time
        self._connected = True
        self._ip_address = ".".join(str(b) for b in art_poll_reply.source_ip)
        self._short_name = art_poll_reply.short_name
        self._long_name = art_poll_reply.long_name
        try:
            style_value = int(art_poll_reply.style)  # type: ignore[call-overload]
            self._style_name = next((s.value[1] for s in StyleCode if s.value[0] == style_value), "Unknown")
        except (TypeError, ValueError):
            self._style_name = "Unknown"

        super().__init__(
            art_poll_reply, f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Online", "online", device_info
        )
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update online status from ArtPollReply."""
        self._connected = True  # If we're getting updates, the node is online
        self._ip_address = ".".join(str(b) for b in artpoll_reply.source_ip)
        self._short_name = artpoll_reply.short_name
        self._long_name = artpoll_reply.long_name
        try:
            style_value = int(artpoll_reply.style)  # type: ignore[call-overload]
            self._style_name = next((s.value[1] for s in StyleCode if s.value[0] == style_value), "Unknown")
        except (TypeError, ValueError):
            self._style_name = "Unknown"

    def set_offline(self) -> None:
        """Mark this entity as offline."""
        self._connected = False

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self._connected

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs = {
            "IP address": self._ip_address,
            "Short name": self._short_name,
            "Long name": self._long_name,
            "Style": self._style_name,
        }
        return attrs

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetIndicatorStateSensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet device indicator state."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo) -> None:
        """Initialize the sensor."""
        self._indicator_state_name = art_poll_reply.indicator_state.name

        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Indicator",
            "indicator",
            device_info,
        )
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_icon = "mdi:lightbulb"
        self._attr_options = [member.name for member in IndicatorState]
        self._attr_entity_category = EntityCategory(EntityCategory.DIAGNOSTIC)

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update indicator state from ArtPollReply."""
        self._indicator_state_name = artpoll_reply.indicator_state.name

    @property
    def native_value(self) -> str:
        """Return the native value of the sensor."""
        return self._indicator_state_name

    @property
    def platform_type(self) -> str:
        return "sensor"


class ArtNetBootProcessSensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet device boot process."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo) -> None:
        """Initialize the sensor."""
        self._boot_process_name = art_poll_reply.boot_process.name

        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Boot Process",
            "boot_process",
            device_info,
        )
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = [member.name for member in BootProcess]
        self._attr_entity_category = EntityCategory(EntityCategory.DIAGNOSTIC)

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update boot process from ArtPollReply."""
        self._boot_process_name = artpoll_reply.boot_process.name

    @property
    def native_value(self) -> str:
        """Return the native value of the sensor."""
        return self._boot_process_name

    @property
    def platform_type(self) -> str:
        return "sensor"


class ArtNetRDMBinarySensor(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet device RDM support status."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo) -> None:
        """Initialize the binary sensor."""
        self._supports_rdm = art_poll_reply.supports_rdm
        self._supports_rdm_through_artnet = art_poll_reply.supports_rdm_through_artnet

        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} RDM Support",
            "rdm_support",
            device_info,
        )
        self._attr_entity_category = EntityCategory(EntityCategory.DIAGNOSTIC)

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update RDM values from ArtPollReply."""
        self._supports_rdm = artpoll_reply.supports_rdm
        self._supports_rdm_through_artnet = artpoll_reply.supports_rdm_through_artnet

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self._supports_rdm

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "Supports RDM through Art-Net": self._supports_rdm_through_artnet,
        }

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetDHCPBinarySensor(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet device DHCP status."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo) -> None:
        """Initialize the binary sensor."""
        self._dhcp_configured = art_poll_reply.dhcp_configured
        self._dhcp_capable = art_poll_reply.dhcp_capable

        super().__init__(
            art_poll_reply, f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} DHCP", "dhcp", device_info
        )
        self._attr_icon = "mdi:network"
        self._attr_entity_category = EntityCategory(EntityCategory.DIAGNOSTIC)

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update DHCP values from ArtPollReply."""
        self._dhcp_configured = artpoll_reply.dhcp_configured
        self._dhcp_capable = artpoll_reply.dhcp_capable

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self._dhcp_configured

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "DHCP capable": self._dhcp_capable,
        }

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetPortInputBinarySensor(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet port input status."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo, port_index: int) -> None:
        """Initialize the binary sensor."""
        self.port_index = port_index

        if port_index < len(art_poll_reply.ports):
            port = art_poll_reply.ports[port_index]
            self._data_received = port.good_input.data_received
            self._is_available = port.input and not port.good_input.input_disabled
            self._includes_dmx512_test_packets = port.good_input.includes_dmx512_test_packets
            self._includes_dmx512_sips = port.good_input.includes_dmx512_sips
            self._includes_dmx512_text_packets = port.good_input.includes_dmx512_text_packets
            self._receive_errors_detected = port.good_input.receive_errors_detected
            self._last_input_seen = port.last_input_seen.isoformat()
            self._port_type_name = port.type.name
        else:
            self._data_received = False
            self._is_available = False
            self._includes_dmx512_test_packets = False
            self._includes_dmx512_sips = False
            self._includes_dmx512_text_packets = False
            self._receive_errors_detected = False
            self._last_input_seen = ""
            self._port_type_name = "Unknown"

        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port {port_index + 1} Input Active",
            f"port_{port_index}_input_active",
            device_info,
        )
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_icon = "mdi:arrow-down-bold"
        self._attr_entity_category = EntityCategory(EntityCategory.DIAGNOSTIC)

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update input values from ArtPollReply."""
        if self.port_index < len(artpoll_reply.ports):
            port = artpoll_reply.ports[self.port_index]
            self._data_received = port.good_input.data_received
            self._is_available = port.input and not port.good_input.input_disabled
            self._includes_dmx512_test_packets = port.good_input.includes_dmx512_test_packets
            self._includes_dmx512_sips = port.good_input.includes_dmx512_sips
            self._includes_dmx512_text_packets = port.good_input.includes_dmx512_text_packets
            self._receive_errors_detected = port.good_input.receive_errors_detected
            self._last_input_seen = port.last_input_seen.isoformat()
            self._port_type_name = port.type.name
        else:
            self._data_received = False
            self._is_available = False
            self._includes_dmx512_test_packets = False
            self._includes_dmx512_sips = False
            self._includes_dmx512_text_packets = False
            self._receive_errors_detected = False
            self._last_input_seen = ""
            self._port_type_name = "Unknown"

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self._data_received

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._is_available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "Includes DMX512 test packets": self._includes_dmx512_test_packets,
            "Includes DMX512 sips": self._includes_dmx512_sips,
            "Includes DMX512 text packets": self._includes_dmx512_text_packets,
            "Receive errors detected": self._receive_errors_detected,
            "Last input seen": self._last_input_seen,
            "Port type": self._port_type_name,
        }

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetPortOutputBinarySensor(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet port output status."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo, port_index: int) -> None:
        """Initialize the binary sensor."""
        self.port_index = port_index

        if port_index < len(art_poll_reply.ports):
            port = art_poll_reply.ports[port_index]
            self._data_being_transmitted = port.good_output_a.data_being_transmitted
            self._is_available = port.output
            self._includes_dmx512_test_packets = port.good_output_a.includes_dmx512_test_packets
            self._includes_dmx512_sips = port.good_output_a.includes_dmx512_sips
            self._includes_dmx512_text_packets = port.good_output_a.includes_dmx512_text_packets
            self._merging_enabled = port.good_output_a.merging_enabled
            self._short_detected = port.good_output_a.short_detected
            self._port_type_name = port.type.name
        else:
            self._data_being_transmitted = False
            self._is_available = False
            self._includes_dmx512_test_packets = False
            self._includes_dmx512_sips = False
            self._includes_dmx512_text_packets = False
            self._merging_enabled = False
            self._short_detected = False
            self._port_type_name = "Unknown"

        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port {port_index + 1} Output Active",
            f"port_{port_index}_output_active",
            device_info,
        )
        self._attr_icon = "mdi:arrow-up-bold"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_entity_category = EntityCategory(EntityCategory.DIAGNOSTIC)

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update output values from ArtPollReply."""
        if self.port_index < len(artpoll_reply.ports):
            port = artpoll_reply.ports[self.port_index]
            self._data_being_transmitted = port.good_output_a.data_being_transmitted
            self._is_available = port.output
            self._includes_dmx512_test_packets = port.good_output_a.includes_dmx512_test_packets
            self._includes_dmx512_sips = port.good_output_a.includes_dmx512_sips
            self._includes_dmx512_text_packets = port.good_output_a.includes_dmx512_text_packets
            self._merging_enabled = port.good_output_a.merging_enabled
            self._short_detected = port.good_output_a.short_detected
            self._port_type_name = port.type.name
        else:
            self._data_being_transmitted = False
            self._is_available = False
            self._includes_dmx512_test_packets = False
            self._includes_dmx512_sips = False
            self._includes_dmx512_text_packets = False
            self._merging_enabled = False
            self._short_detected = False
            self._port_type_name = "Unknown"

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self._data_being_transmitted

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._is_available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "Includes DMX512 test packets": self._includes_dmx512_test_packets,
            "Includes DMX512 sips": self._includes_dmx512_sips,
            "Includes DMX512 text packets": self._includes_dmx512_text_packets,
            "Merging enabled": self._merging_enabled,
            "Short detected": self._short_detected,
            "Port type": self._port_type_name,
        }

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetPortMergeModeSelect(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet port merge mode."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo, port_index: int) -> None:
        """Initialize the sensor."""
        self.port_index = port_index

        if port_index < len(art_poll_reply.ports):
            port = art_poll_reply.ports[port_index]
            self._merging_enabled = port.good_output_a.merging_enabled
            self._merge_mode = "LTP" if port.good_output_a.merge_is_ltp else "HTP"
            self._is_available = port.output
        else:
            self._merging_enabled = False
            self._merge_mode = "HTP"
            self._is_available = False

        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port {port_index + 1} Merge Mode",
            f"port_{port_index}_merge_mode",
            device_info,
        )
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_entity_category = EntityCategory(EntityCategory.DIAGNOSTIC)

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update merge mode from ArtPollReply."""
        if self.port_index < len(artpoll_reply.ports):
            port = artpoll_reply.ports[self.port_index]
            self._merging_enabled = port.good_output_a.merging_enabled
            self._merge_mode = "LTP" if port.good_output_a.merge_is_ltp else "HTP"
            self._is_available = port.output
        else:
            self._merging_enabled = False
            self._merge_mode = "HTP"
            self._is_available = False

    @property
    def is_on(self) -> bool:
        """Return the state of the sensor indicating if merging is enabled."""
        return self._merging_enabled

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return merge mode as extra state attributes."""
        return {"Merge mode": self._merge_mode}

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._is_available

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetPortSACNBinarySensor(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet port sACN mode status."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo, port_index: int) -> None:
        """Initialize the binary sensor."""
        self.port_index = port_index

        if port_index < len(art_poll_reply.ports):
            port = art_poll_reply.ports[port_index]
            self._use_sacn = port.good_output_a.use_sacn
            self._is_available = port.output and art_poll_reply.supports_switching_to_sacn
        else:
            self._use_sacn = False
            self._is_available = False

        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port {port_index + 1} sACN Mode",
            f"port_{port_index}_sacn_mode",
            device_info,
        )
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_entity_category = EntityCategory(EntityCategory.DIAGNOSTIC)

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update sACN mode from ArtPollReply."""
        if self.port_index < len(artpoll_reply.ports):
            port = artpoll_reply.ports[self.port_index]
            self._use_sacn = port.good_output_a.use_sacn
            self._is_available = port.output and artpoll_reply.supports_switching_to_sacn
        else:
            self._use_sacn = False
            self._is_available = False

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self._use_sacn

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._is_available

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetPortRDMBinarySensor(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet port RDM enabled status."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo, port_index: int) -> None:
        """Initialize the binary sensor."""
        self.port_index = port_index

        # Extract and store the RDM status and availability at creation time
        if port_index < len(art_poll_reply.ports):
            port = art_poll_reply.ports[port_index]
            self._rdm_enabled = port.rdm_enabled
            self._is_available = port.output and art_poll_reply.supports_rdm
        else:
            self._rdm_enabled = False
            self._is_available = False

        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port {port_index + 1} RDM",
            f"port_{port_index}_rdm",
            device_info,
        )
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_entity_category = EntityCategory(EntityCategory.DIAGNOSTIC)

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update RDM status from ArtPollReply."""
        if self.port_index < len(artpoll_reply.ports):
            port = artpoll_reply.ports[self.port_index]
            self._rdm_enabled = port.rdm_enabled
            self._is_available = port.output and artpoll_reply.supports_rdm
        else:
            self._rdm_enabled = False
            self._is_available = False

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self._rdm_enabled

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._is_available

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetPortOutputModeSensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet port output mode."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo, port_index: int) -> None:
        """Initialize the sensor."""
        self.port_index = port_index

        # Extract and store the output mode and availability at creation time
        if port_index < len(art_poll_reply.ports):
            port = art_poll_reply.ports[port_index]
            self._output_mode = "Continuous" if port.output_continuous else "Non-continuous"
            self._is_available = port.output
        else:
            self._output_mode = "Non-continuous"
            self._is_available = False

        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port {port_index + 1} Output Mode",
            f"port_{port_index}_output_mode",
            device_info,
        )
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["Continuous", "Non-continuous"]
        self._attr_entity_category = EntityCategory(EntityCategory.DIAGNOSTIC)

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update output mode from ArtPollReply."""
        if self.port_index < len(artpoll_reply.ports):
            port = artpoll_reply.ports[self.port_index]
            self._output_mode = "Continuous" if port.output_continuous else "Non-continuous"
            self._is_available = port.output
        else:
            self._output_mode = "Non-continuous"
            self._is_available = False

    @property
    def native_value(self) -> str:
        """Return the native value of the sensor."""
        return self._output_mode

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._is_available

    @property
    def platform_type(self) -> str:
        return "sensor"


class ArtNetPortUniverseSensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet port universe number."""

    def __init__(
        self, art_poll_reply: ArtPollReply, device_info: DeviceInfo, port_index: int, is_input: bool = True
    ) -> None:
        """Initialize the sensor."""
        self.port_index = port_index
        self.is_input = is_input
        direction = "Input" if is_input else "Output"

        port = art_poll_reply.ports[port_index]
        universe = port.sw_in if is_input else port.sw_out
        self._universe_value = f"{art_poll_reply.net_switch}/{art_poll_reply.sub_switch}/{universe}"
        self._is_available = port.input if is_input else port.output

        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port {port_index + 1} {direction} Universe",
            f"port_{port_index}_{direction.lower()}_universe",
            device_info,
        )

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update universe value from ArtPollReply."""
        if self.port_index < len(artpoll_reply.ports):
            port = artpoll_reply.ports[self.port_index]
            universe = port.sw_in if self.is_input else port.sw_out
            new_universe_value = f"{artpoll_reply.net_switch}/{artpoll_reply.sub_switch}/{universe}"

            if self._universe_value != new_universe_value:
                _LOGGER.info(f"Universe updated for {self.unique_id}: {self._universe_value} -> {new_universe_value}")

            self._universe_value = new_universe_value
            self._is_available = port.input if self.is_input else port.output
        else:
            self._is_available = False

    @property
    def native_value(self) -> str:
        """Return the stored universe value."""
        return self._universe_value

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._is_available

    @property
    def platform_type(self) -> str:
        return "sensor"


class ArtNetFailsafeStateSensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet failsafe state."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo) -> None:
        """Initialize the sensor."""
        self._failsafe_state_name = art_poll_reply.failsafe_state.name

        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Failsafe State",
            "failsafe_state",
            device_info,
        )
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = [member.name for member in FailsafeState]
        self._attr_entity_category = EntityCategory(EntityCategory.DIAGNOSTIC)

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update failsafe state from ArtPollReply."""
        self._failsafe_state_name = artpoll_reply.failsafe_state.name

    @property
    def native_value(self) -> str:
        """Return the native value of the sensor."""
        return self._failsafe_state_name

    @property
    def platform_type(self) -> str:
        return "sensor"


class ArtNetACNPrioritySensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet ACN priority number."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo) -> None:
        """Initialize the sensor."""
        self._acn_priority = art_poll_reply.acn_priority

        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} ACN Priority",
            "acn_priority",
            device_info,
        )
        self._attr_entity_category = EntityCategory(EntityCategory.DIAGNOSTIC)

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update ACN priority from ArtPollReply."""
        self._acn_priority = artpoll_reply.acn_priority

    @property
    def native_value(self) -> int:
        """Return the value reported by the sensor."""
        return self._acn_priority

    @property
    def platform_type(self) -> str:
        return "sensor"


class ArtNetNodeReportSensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet node report text."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo) -> None:
        """Initialize the sensor."""
        self._node_report = art_poll_reply.node_report

        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Node Report",
            "node_report",
            device_info,
        )
        self._attr_entity_category = EntityCategory(EntityCategory.DIAGNOSTIC)

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update node report from ArtPollReply."""
        self._node_report = artpoll_reply.node_report

    @property
    def native_value(self) -> str:
        """Return the value reported by the sensor."""
        return self._node_report

    @property
    def platform_type(self) -> str:
        return "sensor"


class ArtNetPortAddressProgrammingAuthoritySensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet port address programming authority."""

    def __init__(self, art_poll_reply: ArtPollReply, device_info: DeviceInfo) -> None:
        """Initialize the sensor."""
        self._port_address_programming_authority_name = art_poll_reply.port_address_programming_authority.name

        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port Programming Authority",
            "port_programming_authority",
            device_info,
        )
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = [member.name for member in PortAddressProgrammingAuthority]
        self._attr_entity_category = EntityCategory(EntityCategory.DIAGNOSTIC)

    def _update_from_artpoll_reply(self, artpoll_reply: ArtPollReply) -> None:
        """Update port address programming authority from ArtPollReply."""
        self._port_address_programming_authority_name = artpoll_reply.port_address_programming_authority.name

    @property
    def native_value(self) -> str:
        """Return the native value of the sensor."""
        return self._port_address_programming_authority_name

    @property
    def platform_type(self) -> str:
        return "sensor"
