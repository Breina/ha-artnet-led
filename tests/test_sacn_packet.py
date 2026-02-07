import struct
import uuid

import pytest

from custom_components.dmx.server.sacn_packet import SacnOptions, SacnPacket, SacnSyncPacket


class TestSacnPacket:
    def test_packet_creation_defaults(self):
        packet = SacnPacket()

        assert packet.source_name == "HA sACN Controller"
        assert packet.priority == 100
        assert packet.universe == 1
        assert packet.sequence_number == 0
        assert len(packet.cid) == 16
        assert len(packet.dmx_data) == 513
        assert packet.dmx_data[0] == 0x00

    def test_packet_creation_custom(self):
        cid = uuid.uuid4().bytes
        dmx_data = bytearray([0] + [255] * 10 + [0] * 502)

        packet = SacnPacket(
            source_name="Test Controller", priority=150, universe=42, sequence_number=123, cid=cid, dmx_data=dmx_data
        )

        assert packet.source_name == "Test Controller"
        assert packet.priority == 150
        assert packet.universe == 42
        assert packet.sequence_number == 123
        assert packet.cid == cid
        assert packet.dmx_data == dmx_data

    def test_packet_validation(self):
        with pytest.raises(AssertionError):
            SacnPacket(source_name="")

        with pytest.raises(AssertionError):
            SacnPacket(source_name="x" * 64)

        with pytest.raises(AssertionError):
            SacnPacket(priority=-1)

        with pytest.raises(AssertionError):
            SacnPacket(priority=201)

        with pytest.raises(AssertionError):
            SacnPacket(universe=0)

        with pytest.raises(AssertionError):
            SacnPacket(universe=64000)

        with pytest.raises(AssertionError):
            SacnPacket(sequence_number=-1)

        with pytest.raises(AssertionError):
            SacnPacket(sequence_number=256)

        with pytest.raises(AssertionError):
            SacnPacket(cid=b"short")

        with pytest.raises(AssertionError):
            SacnPacket(dmx_data=bytearray(514))

    def test_dmx_channel_operations(self):
        packet = SacnPacket()

        packet.set_dmx_channel(1, 255)
        packet.set_dmx_channel(10, 128)
        packet.set_dmx_channel(512, 64)

        assert packet.dmx_data[1] == 255
        assert packet.dmx_data[10] == 128
        assert packet.dmx_data[512] == 64

        with pytest.raises(AssertionError):
            packet.set_dmx_channel(0, 255)

        with pytest.raises(AssertionError):
            packet.set_dmx_channel(513, 255)

        with pytest.raises(AssertionError):
            packet.set_dmx_channel(1, -1)

        with pytest.raises(AssertionError):
            packet.set_dmx_channel(1, 256)

    def test_set_dmx_data(self):
        packet = SacnPacket()

        test_data = bytearray([0] + [i % 256 for i in range(1, 513)])
        packet.set_dmx_data(test_data)

        assert packet.dmx_data == test_data
        assert packet.start_code == 0x00
        assert packet.channel_data == test_data[1:]

        non_zero_start_code_data = bytearray([0xDD] + [i % 256 for i in range(1, 513)])
        packet.set_dmx_data(non_zero_start_code_data)

        assert packet.dmx_data == non_zero_start_code_data
        assert packet.start_code == 0xDD
        assert packet.channel_data == non_zero_start_code_data[1:]

    def test_serialize_forces_start_code_zero(self):
        """Test that serialize() always outputs start code 0x00 regardless of internal value."""
        packet = SacnPacket()

        non_zero_start_code_data = bytearray([0xDD] + [100] * 512)
        packet.set_dmx_data(non_zero_start_code_data)

        assert packet.start_code == 0xDD

        serialized = packet.serialize()
        assert serialized[125] == 0x00

    def test_multicast_address_calculation(self):
        test_cases = [
            (1, "239.255.0.1"),
            (256, "239.255.1.0"),
            (257, "239.255.1.1"),
            (63999, "239.255.249.255"),
        ]

        for universe, expected_addr in test_cases:
            packet = SacnPacket(universe=universe)
            assert packet.get_multicast_address() == expected_addr

    def test_packet_serialization_basic(self):
        cid = uuid.UUID("12345678-1234-5678-1234-567812345678").bytes
        dmx_data = bytearray([0] + [255, 128, 64] + [0] * 509)

        packet = SacnPacket(
            source_name="Test", priority=120, universe=1, sequence_number=42, cid=cid, dmx_data=dmx_data
        )

        serialized = packet.serialize()

        assert len(serialized) >= 126
        assert serialized[4:16] == b"\x41\x53\x43\x2d\x45\x31\x2e\x31\x37\x00\x00\x00"

        universe_bytes = struct.pack(">H", 1)
        assert universe_bytes in serialized

    def test_packet_round_trip(self):
        cid = uuid.UUID("12345678-1234-5678-1234-567812345678").bytes
        dmx_data = bytearray([0] + [i % 256 for i in range(1, 100)] + [0] * 413)

        original = SacnPacket(
            source_name="Round Trip Test", priority=150, universe=42, sequence_number=99, cid=cid, dmx_data=dmx_data
        )

        serialized = original.serialize()
        deserialized = SacnPacket.deserialize(serialized)

        assert deserialized.source_name == original.source_name
        assert deserialized.priority == original.priority
        assert deserialized.universe == original.universe
        assert deserialized.sequence_number == original.sequence_number
        assert deserialized.cid == original.cid
        assert deserialized.dmx_data == original.dmx_data

    def test_options_serialization(self):
        options = SacnOptions(preview_data=True, stream_terminated=True, force_synchronization=True)

        packet = SacnPacket(options=options)
        serialized = packet.serialize()
        deserialized = SacnPacket.deserialize(serialized)

        assert deserialized.options.preview_data
        assert deserialized.options.stream_terminated
        assert deserialized.options.force_synchronization


class TestSacnSyncPacket:
    def test_sync_packet_creation(self):
        cid = uuid.uuid4().bytes
        packet = SacnSyncPacket(sequence_number=42, sync_address=100, cid=cid)

        assert packet.sequence_number == 42
        assert packet.sync_address == 100
        assert packet.cid == cid

    def test_sync_packet_validation(self):
        with pytest.raises(AssertionError):
            SacnSyncPacket(sequence_number=-1)

        with pytest.raises(AssertionError):
            SacnSyncPacket(sequence_number=256)

        with pytest.raises(AssertionError):
            SacnSyncPacket(sync_address=-1)

        with pytest.raises(AssertionError):
            SacnSyncPacket(sync_address=64000)

        with pytest.raises(AssertionError):
            SacnSyncPacket(cid=b"short")

    def test_sync_packet_serialization(self):
        cid = uuid.UUID("12345678-1234-5678-1234-567812345678").bytes
        packet = SacnSyncPacket(sequence_number=123, sync_address=456, cid=cid)

        serialized = packet.serialize()

        assert len(serialized) >= 125
        assert serialized[4:16] == b"\x41\x53\x43\x2d\x45\x31\x2e\x31\x37\x00\x00\x00"


class TestSacnOptions:
    def test_options_defaults(self):
        options = SacnOptions()

        assert not options.preview_data
        assert not options.stream_terminated
        assert not options.force_synchronization

    def test_options_custom(self):
        options = SacnOptions(preview_data=True, stream_terminated=True, force_synchronization=True)

        assert options.preview_data
        assert options.stream_terminated
        assert options.force_synchronization
