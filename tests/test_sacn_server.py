import uuid
from unittest.mock import MagicMock, patch

import pytest

from custom_components.dmx.server import PortAddress
from custom_components.dmx.server.sacn_server import SacnReceiver, SacnServer, SacnServerConfig
from tests.dmx_test_framework import MockHomeAssistant


class TestSacnServerConfig:
    def test_config_defaults(self):
        config = SacnServerConfig()

        assert config.source_name == "HA sACN Controller"
        assert config.priority == 100
        assert config.sync_address == 0
        assert config.interface_ip is None
        assert not config.enable_per_universe_sync
        assert config.multicast_ttl == 64
        assert not config.enable_preview_data
        assert len(config.cid) == 16

    def test_config_custom(self):
        cid = uuid.uuid4().bytes
        config = SacnServerConfig(
            source_name="Custom Controller",
            priority=150,
            cid=cid,
            sync_address=100,
            interface_ip="192.168.1.100",
            enable_per_universe_sync=True,
            multicast_ttl=32,
            enable_preview_data=True,
        )

        assert config.source_name == "Custom Controller"
        assert config.priority == 150
        assert config.cid == cid
        assert config.sync_address == 100
        assert config.interface_ip == "192.168.1.100"
        assert config.enable_per_universe_sync
        assert config.multicast_ttl == 32
        assert config.enable_preview_data


class TestSacnServer:
    @pytest.fixture
    def mock_hass(self):
        return MockHomeAssistant()

    @pytest.fixture
    def sacn_server(self, mock_hass):
        return SacnServer(mock_hass)

    def test_server_initialization(self, sacn_server):
        assert not sacn_server.running
        assert len(sacn_server.universes) == 0
        assert sacn_server.socket is None
        assert sacn_server.config.source_name == "HA sACN Controller"

    @patch("socket.socket")
    def test_server_start_stop(self, mock_socket_class, sacn_server):
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket

        sacn_server.start_server()
        assert sacn_server.running
        assert sacn_server.socket == mock_socket

        mock_socket.setsockopt.assert_called()
        mock_socket.bind.assert_called_with(("", 0))

        sacn_server.stop_server()
        assert not sacn_server.running
        mock_socket.close.assert_called()

    def test_universe_management(self, sacn_server):
        assert sacn_server.add_universe(1)
        assert 1 in sacn_server.universes

        assert sacn_server.add_universe(1)
        assert len(sacn_server.universes) == 1

        assert not sacn_server.add_universe(0)
        assert not sacn_server.add_universe(64000)

        sacn_server.remove_universe(1)
        assert 1 not in sacn_server.universes

    def test_universe_callbacks(self, sacn_server):
        added_universes = []
        removed_universes = []

        sacn_server.universe_added_callback = lambda u: added_universes.append(u)
        sacn_server.universe_removed_callback = lambda u: removed_universes.append(u)

        sacn_server.add_universe(42)
        assert added_universes == [42]

        sacn_server.remove_universe(42)
        assert removed_universes == [42]

    def test_universe_info(self, sacn_server):
        sacn_server.add_universe(5)

        info = sacn_server.get_universe_info(5)
        assert info is not None
        assert info["universe_id"] == 5
        assert info["sequence_number"] == 0
        assert info["multicast_address"] == "239.255.0.5"
        assert not info["has_data"]
        assert not info["termination_sent"]

        assert sacn_server.get_universe_info(999) is None

    def test_get_all_universes(self, sacn_server):
        sacn_server.add_universe(1)
        sacn_server.add_universe(10)

        all_universes = sacn_server.get_all_universes()
        assert len(all_universes) == 2
        assert 1 in all_universes
        assert 10 in all_universes

    @patch("socket.socket")
    @pytest.mark.asyncio
    async def test_send_dmx_data(self, mock_socket_class, sacn_server, mock_hass):
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket

        sacn_server.start_server()
        sacn_server.add_universe(1)

        dmx_data = bytearray([0] + [255, 128, 64] + [0] * 509)

        result = sacn_server.send_dmx_data(1, dmx_data)
        assert result

        await mock_hass.wait_for_all_tasks()

        mock_socket.sendto.assert_called()

        result = sacn_server.send_dmx_data(999, dmx_data)
        assert not result

    @patch("socket.socket")
    def test_termination_packet(self, mock_socket_class, sacn_server):
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket

        sacn_server.start_server()
        sacn_server.add_universe(1)

        universe_state = sacn_server.universes[1]
        universe_state.last_data = bytearray([0] + [255] * 10 + [0] * 502)

        sacn_server.terminate_universe(1)

        assert mock_socket.sendto.call_count == 3
        assert universe_state.termination_sent

    @patch("socket.socket")
    def test_sync_packet(self, mock_socket_class, sacn_server):
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket

        sacn_server.start_server()

        sacn_server.send_sync_packet(100)

        mock_socket.sendto.assert_called()
        call_args = mock_socket.sendto.call_args[0]
        assert call_args[1] == ("239.255.0.0", 5568)


class TestSacnReceiver:
    @pytest.fixture
    def mock_hass(self):
        return MockHomeAssistant()

    @pytest.fixture
    def data_callback(self):
        return MagicMock()

    @pytest.fixture
    def sacn_receiver(self, mock_hass, data_callback):
        return SacnReceiver(mock_hass, data_callback)

    def test_receiver_initialization(self, sacn_receiver, data_callback):
        assert sacn_receiver.data_callback == data_callback
        assert sacn_receiver.transport is None
        assert len(sacn_receiver.subscribed_universes) == 0

    def test_universe_subscription(self, sacn_receiver):
        sacn_receiver.subscribe_universe(1)
        assert 1 in sacn_receiver.subscribed_universes

        sacn_receiver.subscribe_universe(42)
        assert 42 in sacn_receiver.subscribed_universes

        sacn_receiver.unsubscribe_universe(1)
        assert 1 not in sacn_receiver.subscribed_universes
        assert 42 in sacn_receiver.subscribed_universes

        sacn_receiver.subscribe_universe(0)
        sacn_receiver.subscribe_universe(64000)

    def test_packet_processing(self, sacn_receiver, data_callback):
        sacn_receiver.subscribe_universe(1)

        from custom_components.dmx.server.sacn_packet import SacnPacket

        test_packet = SacnPacket(universe=1, dmx_data=bytearray([0] + [255, 128, 64] + [0] * 509))

        serialized_packet = test_packet.serialize()

        sacn_receiver.datagram_received(serialized_packet, ("192.168.1.100", 5568))

        data_callback.assert_called_once()
        call_args = data_callback.call_args[0]

        port_address = call_args[0]
        assert isinstance(port_address, PortAddress)
        assert port_address.universe == 1

        dmx_data = call_args[1]
        assert dmx_data == test_packet.dmx_data[1:]

        source_name = call_args[2]
        assert source_name == test_packet.source_name

    def test_packet_processing_unsubscribed(self, sacn_receiver, data_callback):
        sacn_receiver.subscribe_universe(1)

        from custom_components.dmx.server.sacn_packet import SacnPacket

        test_packet = SacnPacket(universe=2)
        serialized_packet = test_packet.serialize()

        sacn_receiver.datagram_received(serialized_packet, ("192.168.1.100", 5568))

        data_callback.assert_not_called()

    def test_packet_processing_non_dmx_start_code_ignored(self, sacn_receiver, data_callback):
        """Test that packets with non-DMX start codes (e.g., 0xDD per-address priority) are ignored."""
        sacn_receiver.subscribe_universe(1)

        from custom_components.dmx.server.sacn_packet import SacnPacket

        test_packet = SacnPacket(universe=1, dmx_data=bytearray([0] + [100] * 512))
        serialized_packet = bytearray(test_packet.serialize())

        serialized_packet[125] = 0xDD  # Per-address priority start code

        sacn_receiver.datagram_received(bytes(serialized_packet), ("192.168.1.100", 5568))

        data_callback.assert_not_called()

    def test_connection_lifecycle(self, sacn_receiver):
        mock_transport = MagicMock()

        sacn_receiver.connection_made(mock_transport)
        assert sacn_receiver.transport == mock_transport

        sacn_receiver.connection_lost(None)
        assert sacn_receiver.transport is None


@pytest.mark.asyncio
class TestSacnIntegration:
    async def test_basic_data_flow(self):
        mock_hass = MockHomeAssistant()

        server = SacnServer(mock_hass)
        received_data = []

        def data_callback(port_address, dmx_data, source_name):
            received_data.append((port_address.universe, dmx_data, source_name))

        receiver = SacnReceiver(mock_hass, data_callback)

        server.add_universe(1)
        receiver.subscribe_universe(1)

        with patch("socket.socket") as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket_class.return_value = mock_socket

            server.start_server()

            test_data = bytearray([0] + [255, 128, 64] + [0] * 509)
            server.send_dmx_data(1, test_data)

            await mock_hass.wait_for_all_tasks()

            mock_socket.sendto.assert_called()
            call_args = mock_socket.sendto.call_args[0]

            assert call_args[1] == ("239.255.0.1", 5568)

            server.stop_server()
