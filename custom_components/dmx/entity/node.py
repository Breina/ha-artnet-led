import logging
from typing import Any, Dict

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo

from custom_components.dmx import ArtPollReply
from custom_components.dmx.server import StyleCode, IndicatorState, BootProcess, FailsafeState, PortAddressProgrammingAuthority

_LOGGER = logging.getLogger(__name__)

def bind_index_str(artpoll_reply: ArtPollReply):
    if artpoll_reply.bind_index == 0:
        return ""
    return f" {artpoll_reply.bind_index}"


class ArtNetEntity:
    """Representation of an ArtNet entity."""

    def __init__(
            self,
            art_poll_reply: ArtPollReply,
            name: str,
            entity_id_suffix: str,
            device_info: DeviceInfo,
    ):
        """Initialize the entity."""
        super().__init__()
        self.art_poll_reply = art_poll_reply
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


class ArtNetOnlineBinarySensor(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet device online status."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo):
        """Initialize the binary sensor."""
        super().__init__(art_poll_reply, f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Online", "online", device_info)
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self.connected = True

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self.connected

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        attrs = {
            "ip_address": ".".join(str(b) for b in self.art_poll_reply.source_ip),
            "short_name": self.art_poll_reply.short_name,
            "long_name": self.art_poll_reply.long_name,
            "style": next((s.value[1] for s in StyleCode if s.value[0] == self.art_poll_reply.style), "Unknown"),
        }
        return attrs

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetIndicatorStateSensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet device indicator state."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(art_poll_reply, f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Indicator", "indicator", device_info)
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_icon = "mdi:lightbulb"
        self._attr_options = [member.name for member in IndicatorState]
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str:
        """Return the native value of the sensor."""
        return self.art_poll_reply.indicator_state.name

    @property
    def platform_type(self) -> str:
        return "sensor"


class ArtNetBootProcessSensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet device boot process."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(art_poll_reply, f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Boot Process", "boot_process", device_info)
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = [member.name for member in BootProcess]
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str:
        """Return the native value of the sensor."""
        return self.art_poll_reply.boot_process.name

    @property
    def platform_type(self) -> str:
        return "sensor"


class ArtNetRDMBinarySensor(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet device RDM support status."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo):
        """Initialize the binary sensor."""
        super().__init__(art_poll_reply, f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} RDM Support", "rdm_support", device_info)
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self.art_poll_reply.supports_rdm

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        return {
            "supports_rdm_through_artnet": self.art_poll_reply.supports_rdm_through_artnet,
        }

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetDHCPBinarySensor(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet device DHCP status."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo):
        """Initialize the binary sensor."""
        super().__init__(art_poll_reply, f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} DHCP", "dhcp", device_info)
        self._attr_icon = "mdi:network"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self.art_poll_reply.dhcp_configured

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        return {
            "dhcp_capable": self.art_poll_reply.dhcp_capable,
        }

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetPortInputBinarySensor(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet port input status."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo, port_index):
        """Initialize the binary sensor."""
        self.port_index = port_index
        self.port = art_poll_reply.ports[port_index]
        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port {port_index + 1} Input Active",
            f"port_{port_index}_input_active",
            device_info
        )
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_icon = "mdi:arrow-down-bold"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        port = self.art_poll_reply.ports[self.port_index]
        return port.good_input.data_received

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        port = self.art_poll_reply.ports[self.port_index]
        return port.input and not port.good_input.input_disabled

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        port = self.art_poll_reply.ports[self.port_index]
        return {
            "includes_dmx512_test_packets": port.good_input.includes_dmx512_test_packets,
            "includes_dmx512_sips": port.good_input.includes_dmx512_sips,
            "includes_dmx512_text_packets": port.good_input.includes_dmx512_text_packets,
            "receive_errors_detected": port.good_input.receive_errors_detected,
            "last_input_seen": port.last_input_seen.isoformat(),
            "port_type": port.type.name,
        }

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetPortOutputBinarySensor(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet port output status."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo, port_index):
        """Initialize the binary sensor."""
        self.port_index = port_index
        self.port = art_poll_reply.ports[port_index]
        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port {port_index + 1} Output Active",
            f"port_{port_index}_output_active",
            device_info
        )
        self._attr_icon = "mdi:arrow-up-bold"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        port = self.art_poll_reply.ports[self.port_index]
        return port.good_output_a.data_being_transmitted

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        port = self.art_poll_reply.ports[self.port_index]
        return port.output

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        port = self.art_poll_reply.ports[self.port_index]
        return {
            "includes_dmx512_test_packets": port.good_output_a.includes_dmx512_test_packets,
            "includes_dmx512_sips": port.good_output_a.includes_dmx512_sips,
            "includes_dmx512_text_packets": port.good_output_a.includes_dmx512_text_packets,
            "merging_enabled": port.good_output_a.merging_enabled,
            "short_detected": port.good_output_a.short_detected,
            "port_type": port.type.name,
        }

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetPortMergeModeSelect(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet port merge mode."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo, port_index):
        """Initialize the sensor."""
        self.port_index = port_index
        self.port = art_poll_reply.ports[port_index]
        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port {port_index + 1} Merge Mode",
            f"port_{port_index}_merge_mode",
            device_info
        )
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        """Return the state of the sensor indicating if merging is enabled."""
        port = self.art_poll_reply.ports[self.port_index]
        return port.good_output_a.merging_enabled

    @property
    def extra_state_attributes(self) -> dict:
        """Return merge mode as extra state attributes."""
        port = self.art_poll_reply.ports[self.port_index]
        return {
            "merge_mode": "LTP" if port.good_output_a.merge_is_ltp else "HTP"
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        port = self.art_poll_reply.ports[self.port_index]
        return port.output

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetPortSACNBinarySensor(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet port sACN mode status."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo, port_index):
        """Initialize the binary sensor."""
        self.port_index = port_index
        self.port = art_poll_reply.ports[port_index]
        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port {port_index + 1} sACN Mode",
            f"port_{port_index}_sacn_mode",
            device_info
        )
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        port = self.art_poll_reply.ports[self.port_index]
        return port.good_output_a.use_sacn

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
                self.art_poll_reply.ports[self.port_index].output and
                self.art_poll_reply.supports_switching_to_sacn
        )

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetPortRDMBinarySensor(ArtNetEntity, BinarySensorEntity):
    """Representation of an ArtNet port RDM enabled status."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo, port_index):
        """Initialize the binary sensor."""
        self.port_index = port_index
        self.port = art_poll_reply.ports[port_index]
        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port {port_index + 1} RDM",
            f"port_{port_index}_rdm",
            device_info
        )
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        port = self.art_poll_reply.ports[self.port_index]
        return port.rdm_enabled

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
                self.art_poll_reply.ports[self.port_index].output and
                self.art_poll_reply.supports_rdm
        )

    @property
    def platform_type(self) -> str:
        return "binary_sensor"


class ArtNetPortOutputModeSensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet port output mode."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo, port_index):
        """Initialize the sensor."""
        self.port_index = port_index
        self.port = art_poll_reply.ports[port_index]
        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port {port_index + 1} Output Mode",
            f"port_{port_index}_output_mode",
            device_info
        )
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["Continuous", "Non-continuous"]
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str:
        """Return the native value of the sensor."""
        port = self.art_poll_reply.ports[self.port_index]
        return "Continuous" if port.output_continuous else "Non-continuous"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.art_poll_reply.ports[self.port_index].output

    @property
    def platform_type(self) -> str:
        return "sensor"


class ArtNetPortUniverseSensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet port universe number."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo, port_index, is_input=True):
        """Initialize the sensor."""
        self.port_index = port_index
        self.port = art_poll_reply.ports[port_index]
        self.is_input = is_input
        direction = "Input" if is_input else "Output"
        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port {port_index + 1} {direction} Universe",
            f"port_{port_index}_{direction.lower()}_universe",
            device_info
        )

    @property
    def native_value(self) -> str:
        """Return the value reported by the sensor."""
        port = self.art_poll_reply.ports[self.port_index]
        return f"{self.art_poll_reply.net_switch}/{self.art_poll_reply.sub_switch}/{port.sw_in if self.is_input else port.sw_out}"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        port = self.art_poll_reply.ports[self.port_index]
        return port.input if self.is_input else port.output

    @property
    def platform_type(self) -> str:
        return "sensor"


class ArtNetFailsafeStateSensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet failsafe state."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Failsafe State",
            "failsafe_state",
            device_info
        )
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = [member.name for member in FailsafeState]
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str:
        """Return the native value of the sensor."""
        return self.art_poll_reply.failsafe_state.name

    @property
    def platform_type(self) -> str:
        return "sensor"


class ArtNetACNPrioritySensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet ACN priority number."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} ACN Priority",
            "acn_priority",
            device_info
        )
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int:
        """Return the value reported by the sensor."""
        return self.art_poll_reply.acn_priority

    @property
    def platform_type(self) -> str:
        return "sensor"


class ArtNetNodeReportSensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet node report text."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Node Report",
            "node_report",
            device_info
        )
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str:
        """Return the value reported by the sensor."""
        return self.art_poll_reply.node_report

    @property
    def platform_type(self) -> str:
        return "sensor"


class ArtNetPortAddressProgrammingAuthoritySensor(ArtNetEntity, SensorEntity):
    """Representation of an ArtNet port address programming authority."""

    def __init__(self, art_poll_reply, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(
            art_poll_reply,
            f"{art_poll_reply.short_name}{bind_index_str(art_poll_reply)} Port Programming Authority",
            "port_programming_authority",
            device_info
        )
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = [member.name for member in PortAddressProgrammingAuthority]
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str:
        """Return the native value of the sensor."""
        return self.art_poll_reply.port_address_programming_authority.name

    @property
    def platform_type(self) -> str:
        return "sensor"
