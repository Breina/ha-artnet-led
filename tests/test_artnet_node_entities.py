"""Discovered Art-Net nodes get entities, that have to follow what the node reports for as long as it's around."""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.dmx import async_setup_entry
from custom_components.dmx.const import CONF_NODE_ENTITIES, DOMAIN
from custom_components.dmx.entity.node import (
    ArtNetNodeReportSensor,
    ArtNetOnlineBinarySensor,
    ArtNetPortInputBinarySensor,
)
from custom_components.dmx.entity.node_handler import DynamicNodeHandler
from custom_components.dmx.server import ArtPollReply, Port
from custom_components.dmx.server.artnet_server import ArtNetServer, Node
from custom_components.dmx.setup.server_manager import ServerManager
from tests.dmx_test_framework import MockHomeAssistant

MAC = bytes.fromhex("0050c20830bc")
OTHER_MAC = bytes.fromhex("0050c20830bd")
NODE_IP = bytes([192, 168, 1, 15])


def reply(report="#0001 first", mac=MAC, source_ip=NODE_IP, bind_index=1, ports=None):
    """A reply like the ones we get off the wire."""
    packet = ArtPollReply(
        source_ip=bytearray(source_ip), mac_address=bytearray(mac), bind_index=bind_index, ports=ports or []
    )
    packet.node_report = report
    parsed = ArtPollReply()
    parsed.deserialize(bytes(packet.serialize()))
    return parsed


def added(entity):
    entity.hass = MagicMock()
    entity.async_schedule_update_ha_state = MagicMock()
    return entity


def handler_with(*entities):
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry": {CONF_NODE_ENTITIES: list(entities)}}}
    handler = DynamicNodeHandler(hass, SimpleNamespace(entry_id="entry"), MagicMock())
    known = reply()
    handler.discovered_nodes[f"{known.mac_address!r}{known.bind_index}"] = known
    return handler


class TestUpdates:
    @pytest.mark.asyncio
    async def test_entities_follow_the_replies(self):
        sensor = added(ArtNetNodeReportSensor(reply(), {}))
        await handler_with(sensor).update_node(reply("#0001 changed"))

        assert sensor.native_value == "#0001 changed"
        sensor.async_schedule_update_ha_state.assert_called_once_with()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("other", [{"mac": OTHER_MAC}, {"bind_index": 2}])
    async def test_entities_ignore_other_nodes(self, other):
        sensor = added(ArtNetNodeReportSensor(reply(), {}))
        handler = handler_with(sensor)
        other_reply = reply("#0001 other node", **other)
        handler.discovered_nodes[f"{other_reply.mac_address!r}{other_reply.bind_index}"] = other_reply

        await handler.update_node(other_reply)

        assert sensor.native_value == "#0001 first"
        sensor.async_schedule_update_ha_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_node_can_change_its_ip_address(self):
        sensor = added(ArtNetNodeReportSensor(reply(), {}))
        await handler_with(sensor).update_node(reply("#0001 moved", source_ip=bytes([192, 168, 1, 16])))
        assert sensor.native_value == "#0001 moved"

    @pytest.mark.asyncio
    async def test_entity_disabled_in_the_registry_is_left_alone(self):
        sensor = ArtNetNodeReportSensor(reply(), {})
        sensor.async_schedule_update_ha_state = MagicMock()
        await handler_with(sensor).update_node(reply("#0001 changed"))
        sensor.async_schedule_update_ha_state.assert_not_called()

    def test_repeated_replies_report_the_same_state(self):
        """Otherwise, each poll of every node writes a new state for its input sensors."""
        port = Port(input=True)
        first = ArtNetPortInputBinarySensor(reply(ports=[port]), {}, 0)
        second = ArtNetPortInputBinarySensor(reply(ports=[port]), {}, 0)
        assert first.extra_state_attributes == second.extra_state_attributes


class TestLostNodes:
    def node(self):
        return Node("node", NODE_IP, 1, MAC, MagicMock())

    @pytest.mark.asyncio
    async def test_entities_go_unavailable_except_for_online(self):
        online = added(ArtNetOnlineBinarySensor(reply(), {}))
        report = added(ArtNetNodeReportSensor(reply(), {}))

        await handler_with(online, report).handle_lost_node(self.node())

        assert online.available
        assert not online.is_on
        assert not report.available
        online.async_schedule_update_ha_state.assert_called_once_with()
        report.async_schedule_update_ha_state.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_other_nodes_are_not_affected(self):
        other = added(ArtNetNodeReportSensor(reply(mac=OTHER_MAC), {}))
        other_bind_index = added(ArtNetNodeReportSensor(reply(bind_index=2), {}))

        await handler_with(other, other_bind_index).handle_lost_node(self.node())

        assert other.available
        assert other_bind_index.available

    @pytest.mark.asyncio
    async def test_entities_recover_when_the_node_is_back(self):
        online = added(ArtNetOnlineBinarySensor(reply(), {}))
        report = added(ArtNetNodeReportSensor(reply(), {}))
        handler = handler_with(online, report)
        await handler.handle_lost_node(self.node())

        await handler.handle_new_node(reply("#0001 back"))

        assert online.is_on
        assert report.available
        assert report.native_value == "#0001 back"

    @pytest.mark.asyncio
    async def test_port_that_is_not_an_input_stays_unavailable_when_the_node_is_back(self):
        output_port = Port(output=True)
        sensor = added(ArtNetPortInputBinarySensor(reply(ports=[output_port]), {}, 0))
        handler = handler_with(sensor)
        assert not sensor.available

        await handler.handle_new_node(reply(ports=[output_port]))

        assert not sensor.available

    @pytest.mark.asyncio
    @pytest.mark.parametrize("subscribed", [False, True], ids=["node never polled us", "node polled us"])
    async def test_server_reports_stale_nodes(self, subscribed):
        """Nodes aren't controllers, so usually they don't poll us."""
        with patch("custom_components.dmx.server.artnet_server.get_private_ip", return_value="192.168.1.98"):
            server = ArtNetServer(MockHomeAssistant())
        lost = []
        server.node_lost_callback = lost.append
        node = Node("node", NODE_IP, 1, MAC, datetime.datetime.now() - datetime.timedelta(minutes=5))
        server.add_node_by_ip(node, NODE_IP, 1)
        if subscribed:
            server.node_change_subscribers.add("192.168.1.15")

        with patch("custom_components.dmx.server.artnet_server.STALE_NODE_CUTOFF_TIME", 0):
            await server.remove_stale_nodes()

        assert lost == [node]
        assert not server.nodes_by_ip
        assert not server.node_change_subscribers


class TestStartup:
    @pytest.mark.asyncio
    async def test_setting_up_the_protocol_does_not_start_discovery(self):
        protocol = MagicMock(setup=AsyncMock())
        with patch("custom_components.dmx.setup.server_manager.ArtNetProtocol", return_value=protocol):
            await ServerManager(MagicMock(), MagicMock()).setup_protocols({"artnet": {}})
        protocol.start_server.assert_not_called()

    @pytest.mark.asyncio
    async def test_discovery_starts_once_the_platforms_are_set_up(self):
        """Replies that come in before that lose the entities of platforms that aren't ready, until a restart."""
        order = MagicMock()
        protocol = order.protocol
        manager = MagicMock(setup_protocols=AsyncMock(), get_universes=MagicMock(return_value={}))
        manager.get_protocol_server.return_value = protocol
        hass = MagicMock(data={})
        hass.config_entries.async_forward_entry_setups = AsyncMock(side_effect=lambda *_: order.platforms_ready())
        entry = SimpleNamespace(entry_id="entry", data={DOMAIN: {"artnet": {"universes": []}}})

        with (
            patch("custom_components.dmx.ServerManager", return_value=manager),
            patch("custom_components.dmx.EntityFactory"),
            patch("custom_components.dmx.process_fixtures", AsyncMock(return_value={})),
            patch("custom_components.dmx.cleanup_obsolete_entities", AsyncMock()),
            patch("custom_components.dmx.store_fixture_fingerprints", AsyncMock()),
        ):
            await async_setup_entry(hass, entry)

        calls = [call[0] for call in order.mock_calls]
        assert calls.index("platforms_ready") < calls.index("protocol.start_server")


class TestStringsFromPackets:
    """Strings in Art-Net packets are NUL terminated."""

    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            (b"#0001 [0000] ok".ljust(64, b"\0"), "#0001 [0000] ok"),
            (bytes(64), ""),
            (b"\0left over".ljust(64, b"\0"), ""),
            (b"a\0left over".ljust(64, b"\0"), "a"),
        ],
    )
    def test_ends_at_the_first_nul(self, field, expected):
        assert ArtPollReply._consume_str(bytearray(field), 0, 64) == (expected, 64)
