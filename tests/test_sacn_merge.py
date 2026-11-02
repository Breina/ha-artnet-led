"""Tests for how sACN sources share a universe (issue #133, #113)."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from custom_components.dmx.entity.light.light_entity import DmxLightEntity
from custom_components.dmx.entity.number import DmxNumberEntity
from custom_components.dmx.fixture import delegator, parser
from custom_components.dmx.io.dmx_io import DmxUniverse
from custom_components.dmx.protocols.sacn import protocol as protocol_module
from custom_components.dmx.protocols.sacn.protocol import SacnProtocol
from custom_components.dmx.server import PortAddress
from custom_components.dmx.server.sacn_merge import ReceivedSlot, SacnMerger
from custom_components.dmx.server.sacn_packet import SacnOptions, SacnPacket
from custom_components.dmx.server.sacn_server import SacnReceiver, SacnServer, SacnServerConfig
from tests.dmx_test_framework import MockHomeAssistant

CONSOLE = uuid.uuid4().bytes
WALL_PANEL = uuid.uuid4().bytes


def levels(slots: dict[int, int], cid: bytes = CONSOLE, priority: int = 100, name: str = "Console", **options):
    data = bytearray(513)
    for slot, value in slots.items():
        data[slot] = value
    return SacnPacket(source_name=name, priority=priority, cid=cid, options=SacnOptions(**options), dmx_data=data)


def priorities(slots: dict[int, int], cid: bytes = CONSOLE, length: int = 512, name: str = "Console"):
    data = bytearray(length + 1)
    data[0] = 0xDD
    for slot, value in slots.items():
        data[slot] = value
    return SacnPacket(source_name=name, cid=cid, dmx_data=data)


def merger_with(*packets: SacnPacket) -> SacnMerger:
    """A merger which already waited for the per-address priorities of these sources."""
    merger = SacnMerger()
    for packet in packets:
        merger.handle_packet(packet, 0.0)
    merger.expire(1.5)
    return merger


class TestMerge:
    def test_highest_universe_priority_takes_every_slot(self):
        merged = merger_with(
            levels({1: 200, 2: 200}, WALL_PANEL, priority=100, name="Wall panel"),
            levels({1: 10}, CONSOLE, priority=120),
        ).merge()

        assert merged[1] == ReceivedSlot(10, 120, "Console")
        assert merged[2] == ReceivedSlot(0, 120, "Console")

    def test_equal_priority_is_highest_level(self):
        merged = merger_with(
            levels({1: 200, 2: 10}, WALL_PANEL, name="Wall panel"),
            levels({1: 10, 2: 200}, CONSOLE),
        ).merge()

        assert merged[1].source == "Wall panel"
        assert merged[2].source == "Console"

    def test_per_address_priority_beats_universe_priority(self):
        merged = merger_with(
            levels({1: 200}, WALL_PANEL, priority=150, name="Wall panel"),
            levels({1: 10}, CONSOLE, priority=100),
            priorities({1: 180}, CONSOLE),
        ).merge()

        assert merged[1] == ReceivedSlot(10, 180, "Console")

    def test_per_address_priority_zero_is_not_sourced(self):
        merged = merger_with(levels({1: 200, 2: 200}), priorities({2: 100})).merge()

        assert 1 not in merged
        assert merged[2].level == 200

    def test_slots_past_short_priorities_are_not_sourced(self):
        merged = merger_with(levels({1: 200, 3: 200}), priorities({1: 100}, length=2)).merge()

        assert 1 in merged
        assert 3 not in merged

    def test_slots_past_short_levels_are_claimed_at_zero(self):
        packet = SacnPacket(source_name="Console", cid=CONSOLE, dmx_data=bytearray([0, 200]))

        merged = merger_with(packet).merge()

        assert merged[1].level == 200
        assert merged[512].level == 0

    def test_universe_priority_zero_still_sources(self):
        merged = merger_with(levels({1: 200}, priority=0)).merge()

        assert merged[1] == ReceivedSlot(200, 1, "Console")


class TestSourceLifecycle:
    def test_levels_wait_for_per_address_priorities(self):
        merger = SacnMerger()
        merger.handle_packet(levels({1: 200}), 0.0)

        assert not merger.expire(1.4)
        assert merger.merge() == {}

        assert merger.expire(1.5)
        assert merger.merge()[1].level == 200

    def test_per_address_priorities_end_the_wait(self):
        merger = SacnMerger()
        merger.handle_packet(levels({1: 200}), 0.0)
        merger.handle_packet(priorities({1: 100}), 0.1)

        assert merger.merge()[1].level == 200

    def test_source_loss_falls_back_to_the_next_source(self):
        merger = merger_with(levels({1: 10}, CONSOLE, priority=120), levels({1: 200}, WALL_PANEL, name="Wall panel"))
        merger.handle_packet(levels({1: 200}, WALL_PANEL, name="Wall panel"), 2.0)

        assert merger.expire(2.5)

        assert merger.merge()[1] == ReceivedSlot(200, 100, "Wall panel")

    def test_stream_terminated_removes_at_once(self):
        merger = merger_with(levels({1: 10}))

        assert merger.handle_packet(levels({1: 10}, stream_terminated=True), 0.1)

        assert merger.merge() == {}

    def test_per_address_priorities_alone_dont_keep_a_source_alive(self):
        merger = merger_with(levels({1: 10}), priorities({1: 100}))
        merger.handle_packet(priorities({1: 100}), 2.4)

        merger.expire(2.5)

        assert merger.merge() == {}

    def test_lost_per_address_priorities_fall_back_to_universe_priority(self):
        merger = merger_with(levels({1: 10, 2: 10}), priorities({1: 150}))
        merger.handle_packet(levels({1: 10, 2: 10}), 2.0)

        merger.expire(2.5)

        merged = merger.merge()
        assert merged[1].priority == 100
        assert merged[2].priority == 100

    def test_repeating_a_frame_isnt_a_change(self):
        merger = merger_with(levels({1: 10}), priorities({1: 100}))

        assert not merger.handle_packet(levels({1: 10}), 0.1)
        assert not merger.handle_packet(priorities({1: 100}), 0.1)
        assert merger.handle_packet(levels({1: 11}), 0.1)
        assert merger.handle_packet(priorities({1: 101}), 0.1)


def sacn_universe(priority: int = 100) -> tuple[DmxUniverse, MagicMock]:
    server = MagicMock()
    server.config.priority = priority
    return DmxUniverse(PortAddress(0, 0, 1), None, True, server, 1), server


def received(*slots: tuple[int, int, int, str]) -> dict[int, ReceivedSlot]:
    return {slot: ReceivedSlot(level, slot_priority, name) for slot, level, slot_priority, name in slots}


class TestSharedSacnUniverse:
    @pytest.mark.asyncio
    async def test_received_levels_are_never_transmitted(self):
        universe, server = sacn_universe()

        await universe.set_received(received((1, 200, 100, "Console"), (505, 90, 100, "Console")))
        await universe.update_multiple_values({505: 64})

        sent = server.send_dmx_data.call_args[0][1]
        assert sent[1] == 0
        assert sent[505] == 64

    @pytest.mark.asyncio
    async def test_only_slots_we_set_are_claimed(self):
        universe, server = sacn_universe(priority=110)

        await universe.update_multiple_values({5: 64})

        address_priorities = server.send_dmx_data.call_args[0][2]
        assert address_priorities[4] == 110
        assert not any(address_priorities[:4])

    @pytest.mark.asyncio
    async def test_zero_priority_config_still_claims_our_slots(self):
        universe, server = sacn_universe(priority=0)

        await universe.update_multiple_values({1: 64})

        assert server.send_dmx_data.call_args[0][2][0] == 1

    @pytest.mark.asyncio
    async def test_lower_priority_source_doesnt_affect_our_channel(self):
        universe, _ = sacn_universe(priority=110)
        heard = []
        universe.register_channel_listener(1, heard.append)
        await universe.update_multiple_values({1: 64})
        heard.clear()

        await universe.set_received(received((1, 0, 100, "Console")))

        assert universe.get_channel_value(1) == 64
        assert universe.get_channel_source(1) is None
        assert heard == []

    @pytest.mark.asyncio
    async def test_higher_priority_source_wins_and_falls_back(self):
        universe, server = sacn_universe(priority=110)
        heard = []
        universe.register_channel_listener(1, heard.append)
        await universe.update_multiple_values({1: 64})
        heard.clear()

        await universe.set_received(received((1, 0, 120, "Console")))
        assert universe.get_channel_value(1) == 0
        assert heard == ["Console"]
        assert server.send_dmx_data.call_args[0][1][1] == 64

        await universe.set_received({})
        assert universe.get_channel_value(1) == 64
        assert heard == ["Console", None]

    @pytest.mark.asyncio
    async def test_local_change_hears_about_the_source_that_still_wins(self):
        universe, _ = sacn_universe(priority=100)
        await universe.set_received(received((1, 200, 120, "Console")))
        heard = []
        universe.register_channel_listener(1, heard.append)

        await universe.update_multiple_values({1: 64})
        await universe.update_multiple_values({1: 64})

        assert heard == ["Console", "Console"]
        assert universe.get_channel_value(1) == 200

    @pytest.mark.asyncio
    async def test_equal_priority_is_highest_level_against_us_too(self):
        universe, _ = sacn_universe(priority=100)
        await universe.update_multiple_values({1: 64})

        await universe.set_received(received((1, 200, 100, "Console")))
        assert universe.get_channel_value(1) == 200
        assert universe.get_channel_source(1) == "Console"

        await universe.set_received(received((1, 10, 100, "Console")))
        assert universe.get_channel_value(1) == 64
        assert universe.get_channel_source(1) is None

    @pytest.mark.asyncio
    async def test_received_slots_arent_set_by_us(self):
        universe, _ = sacn_universe()

        await universe.set_received(received((1, 200, 100, "Console")))

        assert universe.get_channel_value(1) == 200
        assert not universe.is_channel_set(1)


class TestEntitiesOnSharedUniverse:
    def entities(self) -> tuple[DmxLightEntity, DmxNumberEntity, DmxUniverse]:
        fixture = parser._parse_fixture_data(
            {
                "name": "T",
                "categories": ["Dimmer"],
                "availableChannels": {"Intensity": {"capability": {"type": "Intensity"}}},
                "modes": [{"name": "m", "channels": ["Intensity"]}],
            }
        )
        universe, _ = sacn_universe(priority=110)
        entities = delegator.create_entities("X", 1, fixture.select_mode("m"), None, universe)

        light = next(e for e in entities if isinstance(e, DmxLightEntity))
        number = next(e for e in entities if isinstance(e, DmxNumberEntity))
        for entity in (light, number):
            entity.hass = MagicMock()
            entity.async_write_ha_state = MagicMock()
            entity.async_schedule_update_ha_state = MagicMock()
        return light, number, universe

    @pytest.mark.asyncio
    async def test_lower_priority_source_doesnt_turn_our_light_off(self):
        light, _, universe = self.entities()
        await light.async_turn_on(brightness=64)

        await universe.set_received(received((1, 0, 100, "Console")))

        assert light.is_on
        assert light.brightness == 64
        assert light.attribution is None

    @pytest.mark.asyncio
    async def test_light_shows_the_winning_source_and_falls_back(self):
        light, _, universe = self.entities()
        await light.async_turn_on(brightness=64)

        await universe.set_received(received((1, 10, 120, "Console")))
        assert light.brightness == 10
        assert light.attribution == "Console"

        await light.async_turn_on(brightness=40)
        assert light.brightness == 10
        assert light.attribution == "Console"

        await universe.set_received({})
        assert light.brightness == 40
        assert light.attribution is None

    @pytest.mark.asyncio
    async def test_number_shows_the_winning_source_and_falls_back(self):
        _, number, universe = self.entities()
        await universe.set_received(received((1, 255, 120, "Console")))

        await number.async_set_native_value(50)
        assert number.native_value == 100
        assert number.attribution == "Console"

        await universe.set_received({})
        assert number.native_value == pytest.approx(50, abs=0.5)
        assert number.attribution is None


class TestArtNetUniverse:
    def universe(self) -> tuple[DmxUniverse, MagicMock]:
        controller = MagicMock()
        return DmxUniverse(PortAddress(0, 0, 1), controller), controller

    @pytest.mark.asyncio
    async def test_received_levels_are_never_transmitted(self):
        universe, controller = self.universe()

        await universe.receive_values({1: 200, 2: 90}, "Console")
        await universe.update_multiple_values({2: 64})

        sent = controller.send_dmx.call_args[0][1]
        assert sent[0] == 0
        assert sent[1] == 64

    @pytest.mark.asyncio
    async def test_latest_writer_wins(self):
        universe, _ = self.universe()
        await universe.update_multiple_values({1: 64})

        await universe.receive_values({1: 0}, "Console")
        assert universe.get_channel_value(1) == 0
        assert universe.get_channel_source(1) == "Console"

        # The same level we had before, which only counts because it replaces what was received.
        heard = []
        universe.register_channel_listener(1, heard.append)
        await universe.update_multiple_values({1: 64})
        assert universe.get_channel_value(1) == 64
        assert universe.get_channel_source(1) is None
        assert heard == [None]


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[SacnPacket] = []

    def sendto(self, data: bytes, address: tuple[str, int]) -> None:
        self.sent.append(SacnPacket.deserialize(data))

    def close(self) -> None:
        pass


class TestSendingPriorities:
    @pytest.fixture
    def hass(self):
        return MockHomeAssistant()

    @pytest.fixture
    def server(self, hass):
        hass.async_create_background_task = lambda coro, name=None: hass.async_create_task(coro)
        server = SacnServer(hass, SacnServerConfig(priority=110))
        server.running = True
        server.socket = FakeSocket()
        server.add_universe(1)
        yield server
        server.running = False
        server.universes[1].stream_task.cancel()

    @pytest.mark.asyncio
    async def test_change_is_sent_first_and_repeated(self, server):
        server.send_dmx_data(1, bytearray([0, 64]), bytes([110]))
        await asyncio.sleep(0.15)

        assert [packet.start_code for packet in server.socket.sent] == [0xDD, 0x00, 0xDD, 0xDD, 0xDD]
        priority_frame = server.socket.sent[0]
        assert priority_frame.channel_data[0] == 110
        assert not any(priority_frame.channel_data[1:])

    @pytest.mark.asyncio
    async def test_unchanged_priorities_arent_repeated_with_levels(self, server):
        server.send_dmx_data(1, bytearray([0, 64]), bytes([110]))
        await asyncio.sleep(0.15)
        server.socket.sent.clear()

        server.send_dmx_data(1, bytearray([0, 65]), bytes([110]))
        await asyncio.sleep(0.05)

        assert [packet.start_code for packet in server.socket.sent] == [0x00]

    @pytest.mark.asyncio
    async def test_keep_alive_keeps_both_going(self, server):
        with patch("custom_components.dmx.server.sacn_server.PRIORITY_INTERVAL", 0.05):
            server.config.retransmit_interval = 0.05
            server.send_dmx_data(1, bytearray([0, 64]), bytes([110]))
            await asyncio.sleep(0.3)

        start_codes = [packet.start_code for packet in server.socket.sent[5:]]
        assert 0x00 in start_codes
        assert 0xDD in start_codes

    @pytest.mark.asyncio
    async def test_sequence_numbers_are_unique_across_start_codes(self, server):
        server.send_dmx_data(1, bytearray([0, 64]), bytes([110]))
        server.send_dmx_data(1, bytearray([0, 65]), bytes([110, 110]))
        await asyncio.sleep(0.15)

        sequence_numbers = [packet.sequence_number for packet in server.socket.sent]
        assert len(set(sequence_numbers)) == len(sequence_numbers)

    @pytest.mark.asyncio
    async def test_output_coming_back_resumes_the_keep_alive(self, server):
        server.config.retransmit_interval = 0.05
        server.send_dmx_data(1, bytearray([0, 64]), bytes([110]))
        await asyncio.sleep(0.15)

        server.terminate_universe(1)
        await asyncio.sleep(0)
        server.send_dmx_data(1, bytearray([0, 64]), bytes([110]))
        server.socket.sent.clear()
        await asyncio.sleep(0.3)

        start_codes = [packet.start_code for packet in server.socket.sent]
        assert start_codes[:2] == [0xDD, 0x00]
        assert start_codes.count(0x00) > 1


class TestProtocolEndToEnd:
    """From packet bytes on the receiving end, to packets on the sending end."""

    @pytest.fixture
    async def protocol(self):
        hass = MockHomeAssistant()
        hass.loop = asyncio.get_running_loop()
        hass.async_create_background_task = lambda coro, name=None: hass.async_create_task(coro)

        async def create_receiver(hass_, callback, own_cid, interface_ip):
            return SacnReceiver(hass_, callback, own_cid, interface_ip)

        with (
            patch.object(protocol_module, "create_sacn_receiver", create_receiver),
            patch("custom_components.dmx.server.sacn_server.socket.socket"),
        ):
            protocol = SacnProtocol(hass, SimpleNamespace(data={}))
            await protocol.setup(
                {"source_name": "HA", "priority": 110, "rate_limit": 0.01, "universes": [{1: {}}]}
            )

        protocol.sacn_server.socket = FakeSocket()
        yield protocol
        protocol.stop_server()
        protocol.sacn_server.running = False
        for task in list(hass._tasks):
            task.cancel()

    def send(self, protocol: SacnProtocol, packet: SacnPacket, universe: int = 1) -> None:
        packet.universe = universe
        protocol.sacn_receiver.datagram_received(packet.serialize(), ("10.0.0.9", 5568))

    @pytest.mark.asyncio
    async def test_reported_scenario(self, protocol):
        """External sources sharing the universe at a lower priority, while we control channel 505."""
        universe = protocol.universes[PortAddress(0, 0, 1)]
        heard = []
        universe.register_channel_listener(505, heard.append)

        console = dict.fromkeys(range(1, 21), 200)
        self.send(protocol, priorities(dict.fromkeys(range(1, 513), 100)))
        self.send(protocol, levels(console))
        await asyncio.sleep(0.05)

        await universe.update_multiple_values({505: 64})
        await asyncio.sleep(0.05)

        # The console's zero doesn't bring our channel back to off.
        self.send(protocol, levels(console))
        await asyncio.sleep(0.05)
        assert universe.get_channel_value(505) == 64
        assert heard == [None]

        # Nothing of the console in what we send.
        sent_levels = [p for p in protocol.sacn_server.socket.sent if p.start_code == 0x00]
        assert sent_levels
        assert {slot: value for slot, value in enumerate(sent_levels[-1].channel_data, 1) if value} == {505: 64}
        assert sent_levels[-1].source_name == "HA"
        assert sent_levels[-1].priority == 110

        # While channel 1 is what the console is making it.
        assert universe.get_channel_value(1) == 200
        assert universe.get_channel_source(1) == "Console"

        sent_priorities = next(p for p in protocol.sacn_server.socket.sent if p.start_code == 0xDD)
        assert {slot: value for slot, value in enumerate(sent_priorities.channel_data, 1) if value} == {505: 110}

    @pytest.mark.asyncio
    async def test_termination_is_applied(self, protocol):
        universe = protocol.universes[PortAddress(0, 0, 1)]
        self.send(protocol, priorities({1: 100}))
        self.send(protocol, levels({1: 200}))
        await asyncio.sleep(0.05)
        assert universe.get_channel_value(1) == 200

        self.send(protocol, levels({1: 200}, stream_terminated=True))
        await asyncio.sleep(0.1)
        assert universe.get_channel_value(1) == 0

    @pytest.mark.asyncio
    async def test_source_loss_is_noticed_without_more_packets(self, protocol):
        universe = protocol.universes[PortAddress(0, 0, 1)]
        self.send(protocol, priorities({1: 100}))
        self.send(protocol, levels({1: 200}))
        await asyncio.sleep(0.05)
        assert universe.get_channel_value(1) == 200

        with (
            patch.object(protocol_module, "SOURCE_CHECK_INTERVAL", 0.01),
            patch("custom_components.dmx.server.sacn_merge.SOURCE_LOSS_TIMEOUT", 0.0),
        ):
            protocol.stop_server()
            protocol._source_watcher = protocol.hass.async_create_background_task(protocol._watch_sources())
            await asyncio.sleep(0.1)

        assert universe.get_channel_value(1) == 0

    @pytest.mark.asyncio
    async def test_high_universe_receives_packets(self, protocol):
        universe = protocol.add_universe({513: {}})
        protocol.sacn_receiver.subscribe_universe(513)
        self.send(protocol, priorities({1: 100}), universe=513)
        self.send(protocol, levels({1: 200}), universe=513)
        await asyncio.sleep(0.05)

        assert universe.get_channel_value(1) == 200
