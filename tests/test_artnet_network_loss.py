"""The Art-Net server has to get through a network outage on its own, without needing a restart."""

import asyncio
import datetime
from unittest.mock import MagicMock, patch

import pytest

from custom_components.dmx.server import ArtDmx, PortAddress
from custom_components.dmx.server.artnet_server import ArtNetServer, ManualNode, Node
from tests.dmx_test_framework import MockHomeAssistant

MODULE = "custom_components.dmx.server.artnet_server"
ADDRESS = PortAddress(0, 0, 7)
BROADCAST = "255.255.255.255"
NODE_IP = "192.168.1.15"
MANUAL_NODE_IP = "192.168.1.16"
LAN_IP = "192.168.1.98"


class Network:
    """Stands in for the socket module, where sending to an unreachable target fails like it does on Linux."""

    def __init__(self):
        self.unreachable = set()
        self.delivered = []

    def __call__(self, *_):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def setsockopt(self, *_):
        pass

    def setblocking(self, *_):
        pass

    def sendto(self, packet, target):
        if target[0] in self.unreachable:
            raise OSError(101, "Network unreachable")
        self.delivered.append(target[0])


@pytest.fixture
def network():
    network = Network()
    with patch(f"{MODULE}.socket", network), patch(f"{MODULE}.random.uniform", return_value=0):
        yield network


def create_server(own_ip=LAN_IP, **kwargs):
    hass = MockHomeAssistant()
    stale_checks = []

    def create_background_task(coro, name):
        coro.close()
        stale_checks.append(name)

    hass.async_create_background_task = create_background_task
    with patch(f"{MODULE}.get_private_ip", return_value=own_ip):
        server = ArtNetServer(hass, **kwargs)
    server.add_port(ADDRESS)
    server.stale_checks = stale_checks
    return server


@pytest.fixture
def server(network):
    return create_server(retransmit_time_ms=1)


async def run_for_a_while(coroutine):
    task = asyncio.ensure_future(coroutine)
    await asyncio.sleep(0.05)
    assert not task.done(), task
    task.cancel()


def dmx_loop(server):
    own_port = server.own_port_addresses[ADDRESS]
    return server.start_artdmx_loop(ADDRESS, bytearray(16), own_port, ADDRESS in server.manual_nodes_by_port_address)


def add_discovered_node(server):
    node = Node("node", bytes(map(int, NODE_IP.split("."))), 1, bytes(6), MagicMock())
    server.add_node_by_port_address(ADDRESS, node)


class TestPollLoop:
    @pytest.mark.asyncio
    async def test_polling_resumes_when_the_network_returns(self, server, network):
        network.unreachable.add(BROADCAST)
        await run_for_a_while(server.start_poll_loop())
        assert BROADCAST not in network.delivered

        network.unreachable.clear()
        await run_for_a_while(server.start_poll_loop())
        assert BROADCAST in network.delivered

    @pytest.mark.asyncio
    async def test_undelivered_polls_do_not_make_nodes_stale(self, server, network):
        network.unreachable.add(BROADCAST)
        await run_for_a_while(server.start_poll_loop())
        assert server.stale_checks == []

        network.unreachable.clear()
        await run_for_a_while(server.start_poll_loop())
        assert server.stale_checks

    @pytest.mark.asyncio
    async def test_failure_is_logged_once(self, server, network):
        network.unreachable.add(BROADCAST)
        with patch(f"{MODULE}.log") as log:
            await run_for_a_while(server.start_poll_loop())
        assert log.warning.call_count == 1


class TestOwnAddress:
    def test_starts_without_a_default_route(self, network):
        assert create_server("127.0.0.1")._own_ip == bytes([127, 0, 0, 1])

    @pytest.mark.asyncio
    async def test_learned_once_the_route_is_back(self, network):
        """Otherwise, we'd no longer recognize our own broadcasts, and start answering ourselves."""
        server = create_server("127.0.0.1")

        with patch(f"{MODULE}.get_private_ip", return_value=LAN_IP):
            await run_for_a_while(server.start_poll_loop())
        assert server._own_ip == bytes([192, 168, 1, 98])

    @pytest.mark.asyncio
    async def test_kept_when_the_route_is_lost(self, server):
        with patch(f"{MODULE}.get_private_ip", return_value="127.0.0.1"):
            await run_for_a_while(server.start_poll_loop())
        assert server._own_ip == bytes([192, 168, 1, 98])


class TestDmxLoop:
    @pytest.mark.asyncio
    async def test_refreshes_resume_when_the_network_returns(self, server, network):
        add_discovered_node(server)
        network.unreachable.add(NODE_IP)

        task = asyncio.ensure_future(dmx_loop(server))
        await asyncio.sleep(0.02)
        assert not task.done()
        assert NODE_IP not in network.delivered

        network.unreachable.clear()
        await asyncio.sleep(0.02)
        task.cancel()
        assert NODE_IP in network.delivered

    @pytest.mark.asyncio
    async def test_unreachable_manual_node_does_not_hold_back_others(self, server, network):
        add_discovered_node(server)
        server.add_manual_node(ManualNode(ADDRESS, MANUAL_NODE_IP, 6454))
        network.unreachable.add(MANUAL_NODE_IP)

        await run_for_a_while(dmx_loop(server))
        assert NODE_IP in network.delivered

    @pytest.mark.asyncio
    async def test_unreachable_node_does_not_hold_back_manual_node(self, server, network):
        add_discovered_node(server)
        server.add_manual_node(ManualNode(ADDRESS, MANUAL_NODE_IP, 6454))
        network.unreachable.add(NODE_IP)

        await run_for_a_while(dmx_loop(server))
        assert MANUAL_NODE_IP in network.delivered


class TestCommandsWithoutNodes:
    """A command that comes in while there are no nodes has to reach them when they return."""

    @pytest.fixture
    def running_server(self, server):
        server.startup_time = datetime.datetime.now() - datetime.timedelta(seconds=60)
        server.send_dmx = MagicMock(wraps=server.send_dmx)
        return server

    def test_latest_data_goes_to_the_first_node_found(self, running_server):
        latest = bytearray([1, 2, 3])
        running_server.send_dmx(ADDRESS, latest)
        running_server.send_dmx.reset_mock()

        add_discovered_node(running_server)

        running_server.send_dmx.assert_called_once_with(ADDRESS, latest)

    def test_nothing_is_sent_to_a_node_without_data(self, running_server):
        add_discovered_node(running_server)
        running_server.send_dmx.assert_not_called()

    def test_node_found_during_startup_does_not_trigger_a_send(self, server):
        server.own_port_addresses[ADDRESS].data = bytearray(3)
        server.send_dmx = MagicMock()
        add_discovered_node(server)
        server.send_dmx.assert_not_called()


def test_failing_diagnostics_and_replies_do_not_reach_the_caller(server, network):
    """These get sent from within send_dmx, and shouldn't make a light command fail."""
    network.unreachable.add(BROADCAST)
    server.send_diagnostics()
    ArtNetServer.send_artnet(ArtDmx(port_address=ADDRESS, data=bytearray(16)), BROADCAST)
