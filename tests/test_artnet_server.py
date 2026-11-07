from _socket import inet_aton
from unittest.mock import MagicMock, patch

import pytest

from custom_components.dmx.server import PortAddress
from custom_components.dmx.server.artnet_server import ARTNET_PORT, ArtNetServer, ManualNode, Node

ADDRESS = PortAddress(0, 0, 0)
NODE_IP = "192.0.2.3"
OTHER_IP = "192.0.2.4"


def make_server() -> ArtNetServer:
    hass = MagicMock()
    # Background tasks don't run in these tests, so close their coroutines to avoid "never awaited" warnings.
    hass.async_create_background_task.side_effect = lambda coro, _name: coro.close()
    with patch("custom_components.dmx.server.artnet_server.get_private_ip", return_value="192.0.2.2"):
        server = ArtNetServer(hass, retransmit_time_ms=0)
    server.add_port(ADDRESS)
    return server


@pytest.fixture
def mock_sock():
    with patch("custom_components.dmx.server.artnet_server.socket") as socket_class:
        yield socket_class.return_value.__enter__.return_value


class TestArtDmxTargets:
    @staticmethod
    def add_discovered(server: ArtNetServer, ip: str) -> None:
        addr = inet_aton(ip)
        server.nodes_by_port_address.setdefault(ADDRESS, set()).add(Node(addr=addr))

    @staticmethod
    async def send_one_frame(server: ArtNetServer) -> None:
        await server.start_artdmx_loop(
            ADDRESS,
            bytearray(62),
            server.own_port_addresses[ADDRESS],
            ADDRESS in server.manual_nodes_by_port_address,
        )

    @staticmethod
    def sent_to(mock_sock: MagicMock) -> list[tuple[str, int]]:
        return [call.args[1] for call in mock_sock.sendto.call_args_list]

    async def test_manual_node_that_is_also_discovered_gets_one_frame(self, mock_sock):
        server = make_server()
        server.add_manual_node(ManualNode(ADDRESS, NODE_IP, ARTNET_PORT))
        self.add_discovered(server, NODE_IP)

        await self.send_one_frame(server)

        assert self.sent_to(mock_sock) == [(NODE_IP, ARTNET_PORT)]

    async def test_manual_node_on_another_port_is_a_separate_target(self, mock_sock):
        server = make_server()
        server.add_manual_node(ManualNode(ADDRESS, NODE_IP, 6455))
        self.add_discovered(server, NODE_IP)

        await self.send_one_frame(server)

        assert sorted(self.sent_to(mock_sock)) == [(NODE_IP, ARTNET_PORT), (NODE_IP, 6455)]

    async def test_manual_and_different_discovered_node_both_get_a_frame(self, mock_sock):
        server = make_server()
        server.add_manual_node(ManualNode(ADDRESS, NODE_IP, ARTNET_PORT))
        self.add_discovered(server, OTHER_IP)

        await self.send_one_frame(server)

        assert sorted(self.sent_to(mock_sock)) == [(NODE_IP, ARTNET_PORT), (OTHER_IP, ARTNET_PORT)]

    async def test_manual_node_without_discovery_gets_a_frame(self, mock_sock):
        server = make_server()
        server.add_manual_node(ManualNode(ADDRESS, NODE_IP, ARTNET_PORT))

        await self.send_one_frame(server)

        assert self.sent_to(mock_sock) == [(NODE_IP, ARTNET_PORT)]

    async def test_discovered_node_without_manual_gets_a_frame(self, mock_sock):
        server = make_server()
        self.add_discovered(server, NODE_IP)

        await self.send_one_frame(server)

        assert self.sent_to(mock_sock) == [(NODE_IP, ARTNET_PORT)]
