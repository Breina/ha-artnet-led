import struct
import uuid
from dataclasses import dataclass, field

SACN_PORT = 5568
ACN_PACKET_IDENTIFIER = b"\x41\x53\x43\x2d\x45\x31\x2e\x31\x37\x00\x00\x00"
ROOT_VECTOR = 0x00000004
FRAMING_VECTOR = 0x00000002
DMP_VECTOR = 0x02
DMP_ADDRESS_TYPE_DATA_TYPE = 0xA1
DMP_FIRST_PROPERTY_ADDRESS = 0x0000
DMP_ADDRESS_INCREMENT = 0x0001


@dataclass
class SacnOptions:
    preview_data: bool = False
    stream_terminated: bool = False
    force_synchronization: bool = False


@dataclass
class SacnPacket:
    """
    sACN (E1.31) packet implementation following ANSI E1.31-2016 specification.

    This class implements the complete E1.31 packet structure with:
    - ACN Root Layer (38 bytes)
    - Framing Layer (77 bytes)
    - Device Management Protocol (DMP) Layer (variable length)
    """

    source_name: str = "HA sACN Controller"
    priority: int = 100  # 0-200, default 100
    universe: int = 1
    sequence_number: int = 0
    options: SacnOptions = field(default_factory=SacnOptions)
    cid: bytes = field(default_factory=lambda: uuid.uuid4().bytes)
    dmx_data: bytearray = field(default_factory=lambda: bytearray(513))  # Start code + 512 channels

    def __post_init__(self):
        assert 1 <= len(self.source_name) <= 63, "Source name must be 1-63 characters"
        assert 0 <= self.priority <= 200, "Priority must be 0-200"
        assert 1 <= self.universe <= 63999, "Universe must be 1-63999"
        assert 0 <= self.sequence_number <= 255, "Sequence number must be 0-255"
        assert len(self.cid) == 16, "CID must be 16 bytes (UUID)"
        assert len(self.dmx_data) <= 513, "DMX data must be <= 513 bytes"

        if len(self.dmx_data) == 0:
            self.dmx_data = bytearray(513)
        if self.dmx_data[0] != 0x00:
            self.dmx_data[0] = 0x00

    def set_dmx_channel(self, channel: int, value: int):
        assert 1 <= channel <= 512, "Channel must be 1-512"
        assert 0 <= value <= 255, "Value must be 0-255"

        if len(self.dmx_data) < channel + 1:
            self.dmx_data.extend([0] * (channel + 1 - len(self.dmx_data)))

        self.dmx_data[channel] = value

    def set_dmx_data(self, data: bytearray):
        assert len(data) <= 513, "DMX data must be <= 513 bytes"
        self.dmx_data = data
        if len(self.dmx_data) > 0 and self.dmx_data[0] != 0x00:
            self.dmx_data[0] = 0x00

    def get_multicast_address(self) -> str:
        return f"239.255.{self.universe >> 8}.{self.universe & 0xFF}"

    def serialize(self) -> bytes:
        # Calculate lengths
        dmp_layer_length = 11 + len(self.dmx_data)  # DMP header (11) + property values
        framing_layer_length = 77 + dmp_layer_length  # Framing header (77) + DMP layer
        root_layer_length = 38 + framing_layer_length  # Root header (38) + Framing layer

        packet = bytearray()

        packet.extend(struct.pack(">H", 0x0010))
        packet.extend(struct.pack(">H", 0x0000))
        packet.extend(ACN_PACKET_IDENTIFIER)
        packet.extend(struct.pack(">H", 0x7000 | root_layer_length))
        packet.extend(struct.pack(">I", ROOT_VECTOR))
        packet.extend(self.cid)

        packet.extend(struct.pack(">H", 0x7000 | framing_layer_length))
        packet.extend(struct.pack(">I", FRAMING_VECTOR))

        source_name_bytes = self.source_name.encode("utf-8")[:63]
        source_name_padded = source_name_bytes + b"\x00" * (64 - len(source_name_bytes))
        packet.extend(source_name_padded)

        packet.extend(struct.pack(">B", self.priority))
        packet.extend(struct.pack(">H", 0x0000))
        packet.extend(struct.pack(">B", self.sequence_number))

        options_byte = 0
        if self.options.preview_data:
            options_byte |= 0x80
        if self.options.stream_terminated:
            options_byte |= 0x40
        if self.options.force_synchronization:
            options_byte |= 0x20
        packet.extend(struct.pack(">B", options_byte))

        packet.extend(struct.pack(">H", self.universe))

        packet.extend(struct.pack(">H", 0x7000 | dmp_layer_length))
        packet.extend(struct.pack(">B", DMP_VECTOR))
        packet.extend(struct.pack(">B", DMP_ADDRESS_TYPE_DATA_TYPE))
        packet.extend(struct.pack(">H", DMP_FIRST_PROPERTY_ADDRESS))
        packet.extend(struct.pack(">H", DMP_ADDRESS_INCREMENT))
        packet.extend(struct.pack(">H", len(self.dmx_data)))

        packet.extend(self.dmx_data)

        return bytes(packet)

    @classmethod
    def deserialize(cls, packet: bytes) -> "SacnPacket":
        if len(packet) < 126:
            raise ValueError("Packet too small to be valid sACN")

        offset = 0

        _preamble_size = struct.unpack(">H", packet[offset : offset + 2])[0]
        offset += 2

        _postamble_size = struct.unpack(">H", packet[offset : offset + 2])[0]
        offset += 2

        acn_pid = packet[offset : offset + 12]
        if acn_pid != ACN_PACKET_IDENTIFIER:
            raise ValueError("Invalid ACN Packet Identifier")
        offset += 12

        root_flength = struct.unpack(">H", packet[offset : offset + 2])[0]
        _root_length = root_flength & 0x0FFF
        offset += 2

        root_vector = struct.unpack(">I", packet[offset : offset + 4])[0]
        if root_vector != ROOT_VECTOR:
            raise ValueError(f"Invalid root vector: {root_vector}")
        offset += 4

        cid = packet[offset : offset + 16]
        offset += 16

        framing_flength = struct.unpack(">H", packet[offset : offset + 2])[0]
        _framing_length = framing_flength & 0x0FFF
        offset += 2

        framing_vector = struct.unpack(">I", packet[offset : offset + 4])[0]
        if framing_vector != FRAMING_VECTOR:
            raise ValueError(f"Invalid framing vector: {framing_vector}")
        offset += 4

        source_name_bytes = packet[offset : offset + 64]
        source_name = source_name_bytes.rstrip(b"\x00").decode("utf-8")
        offset += 64

        priority = struct.unpack(">B", packet[offset : offset + 1])[0]
        offset += 1

        _reserved = struct.unpack(">H", packet[offset : offset + 2])[0]
        offset += 2

        sequence_number = struct.unpack(">B", packet[offset : offset + 1])[0]
        offset += 1

        options_byte = struct.unpack(">B", packet[offset : offset + 1])[0]
        options = SacnOptions(
            preview_data=(options_byte & 0x80) != 0,
            stream_terminated=(options_byte & 0x40) != 0,
            force_synchronization=(options_byte & 0x20) != 0,
        )
        offset += 1

        universe = struct.unpack(">H", packet[offset : offset + 2])[0]
        offset += 2

        dmp_flength = struct.unpack(">H", packet[offset : offset + 2])[0]
        _dmp_length = dmp_flength & 0x0FFF
        offset += 2

        dmp_vector = struct.unpack(">B", packet[offset : offset + 1])[0]
        if dmp_vector != DMP_VECTOR:
            raise ValueError(f"Invalid DMP vector: {dmp_vector}")
        offset += 1

        _address_type_data_type = struct.unpack(">B", packet[offset : offset + 1])[0]
        offset += 1

        _first_property_address = struct.unpack(">H", packet[offset : offset + 2])[0]
        offset += 2

        _address_increment = struct.unpack(">H", packet[offset : offset + 2])[0]
        offset += 2

        property_value_count = struct.unpack(">H", packet[offset : offset + 2])[0]
        offset += 2

        dmx_data = bytearray(packet[offset : offset + property_value_count])

        return cls(
            source_name=source_name,
            priority=priority,
            universe=universe,
            sequence_number=sequence_number,
            options=options,
            cid=cid,
            dmx_data=dmx_data,
        )


@dataclass
class SacnSyncPacket:
    """
    sACN Synchronization packet (E1.31) for universe synchronization.
    Used to synchronize multiple universes for frame-accurate output.
    """

    sequence_number: int = 0
    sync_address: int = 0  # 0 = all universes, 1-63999 = specific sync address
    cid: bytes = field(default_factory=lambda: uuid.uuid4().bytes)

    def __post_init__(self):
        assert 0 <= self.sequence_number <= 255, "Sequence number must be 0-255"
        assert 0 <= self.sync_address <= 63999, "Sync address must be 0-63999"
        assert len(self.cid) == 16, "CID must be 16 bytes (UUID)"

    def serialize(self) -> bytes:
        dmp_layer_length = 11
        framing_layer_length = 77 + dmp_layer_length
        root_layer_length = 38 + framing_layer_length

        packet = bytearray()

        packet.extend(struct.pack(">H", 0x0010))
        packet.extend(struct.pack(">H", 0x0000))
        packet.extend(ACN_PACKET_IDENTIFIER)
        packet.extend(struct.pack(">H", 0x7000 | root_layer_length))
        packet.extend(struct.pack(">I", ROOT_VECTOR))
        packet.extend(self.cid)

        packet.extend(struct.pack(">H", 0x7000 | framing_layer_length))
        packet.extend(struct.pack(">I", 0x00000001))

        packet.extend(b"\x00" * 64)

        packet.extend(struct.pack(">B", 0))
        packet.extend(struct.pack(">H", 0x0000))
        packet.extend(struct.pack(">B", self.sequence_number))
        packet.extend(struct.pack(">B", 0x00))
        packet.extend(struct.pack(">H", self.sync_address))

        packet.extend(struct.pack(">H", 0x7000 | dmp_layer_length))
        packet.extend(struct.pack(">B", DMP_VECTOR))
        packet.extend(struct.pack(">B", DMP_ADDRESS_TYPE_DATA_TYPE))
        packet.extend(struct.pack(">H", DMP_FIRST_PROPERTY_ADDRESS))
        packet.extend(struct.pack(">H", DMP_ADDRESS_INCREMENT))
        packet.extend(struct.pack(">H", 0x0000))

        return bytes(packet)


class SacnPacketError(Exception):
    pass
