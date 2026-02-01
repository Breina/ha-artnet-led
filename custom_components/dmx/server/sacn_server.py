import asyncio
import logging
import socket
import struct
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant

from custom_components.dmx.server import PortAddress
from custom_components.dmx.server.sacn_packet import SACN_PORT, SacnOptions, SacnPacket, SacnSyncPacket

log = logging.getLogger(__name__)


@dataclass
class SacnServerConfig:
    source_name: str = "HA sACN Controller"
    priority: int = 100
    cid: bytes | None = None
    sync_address: int = 0
    interface_ip: str | None = None  # defaults to None, which means the *default* interface
    """Which interface (by IP) the sACN server should bind to for sending and receiving data."""
    enable_per_universe_sync: bool = False
    multicast_ttl: int = 64
    enable_preview_data: bool = False
    retransmit_interval: float = 0.8
    """Interval in seconds to retransmit last frame when no new data arrives."""

    def __post_init__(self) -> None:
        if self.cid is None:
            self.cid = uuid.uuid4().bytes


@dataclass
class UniverseState:
    sequence_number: int = 0
    last_data: bytearray | None = None
    stream_task: asyncio.Task[None] | None = None
    termination_sent: bool = False
    unicast_addresses: list[dict[str, Any]] = field(default_factory=list)
    pending_data: bytearray | None = None
    last_update_time: float = field(default_factory=lambda: 0.0)
    last_send_time: float = field(default_factory=lambda: 0.0)

    def increment_sequence(self) -> None:
        self.sequence_number = (self.sequence_number + 1) % 256


class SacnServer:
    """
    sACN (E1.31) server implementation for streaming DMX universe data.

    Supports:
    - Multicast transmission to standard sACN multicast addresses
    - Universe synchronization
    - Configurable priorities and options
    - Integration with existing DMX universe system
    - Continuous streaming at sACN standard frame rate (44 fps)
    """

    def __init__(self, hass: HomeAssistant, config: SacnServerConfig | None = None) -> None:
        import uuid

        self.hass = hass
        self.config = config or SacnServerConfig()

        # Ensure we have a valid CID
        if self.config.cid is None:
            self.config.cid = uuid.uuid4().bytes

        self.universes: dict[int, UniverseState] = {}
        self.socket: socket.socket | None = None
        self.running = False

        # Callbacks
        self.universe_added_callback: Callable[[int], None] | None = None
        self.universe_removed_callback: Callable[[int], None] | None = None

        log.info(f"sACN Server initialized with source name: {self.config.source_name}")

    def start_server(self) -> None:
        if self.running:
            log.warning("sACN server already running")
            return

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, self.config.multicast_ttl)
            self.socket.bind((self.config.interface_ip or "", 0))

            if self.config.interface_ip:
                packed_interface = socket.inet_aton(self.config.interface_ip)
                self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, packed_interface)
                log.info(f"sACN server started on {self.config.interface_ip}:{SACN_PORT}")
            else:
                log.info(f"sACN server started on {SACN_PORT}")

            self.running = True

        except Exception as e:
            log.error(f"Failed to start sACN server: {e}")
            raise

    def stop_server(self) -> None:
        if not self.running:
            return

        for universe_id in list(self.universes.keys()):
            self.terminate_universe(universe_id)

        if self.socket:
            self.socket.close()
            self.socket = None

        self.running = False
        log.info("sACN server stopped")

    def add_universe(self, universe_id: int, unicast_addresses: list[str] | None = None) -> bool:
        if not (1 <= universe_id <= 63999):
            log.error(f"Invalid universe ID: {universe_id}. Must be 1-63999")
            return False

        if universe_id in self.universes:
            log.debug(f"Universe {universe_id} already exists")
            return True

        universe_state = UniverseState()
        if unicast_addresses:
            # Convert string addresses to dict format
            universe_state.unicast_addresses = []
            for addr in unicast_addresses:
                if ":" in addr:
                    host, port_str = addr.split(":", 1)
                    universe_state.unicast_addresses.append({"host": host, "port": int(port_str)})
                else:
                    # Default to standard sACN port if no port specified
                    universe_state.unicast_addresses.append({"host": addr, "port": 5568})

        self.universes[universe_id] = universe_state
        log.info(f"Added sACN universe {universe_id}")

        if self.universe_added_callback:
            self.universe_added_callback(universe_id)

        return True

    def remove_universe(self, universe_id: int) -> None:
        if universe_id not in self.universes:
            log.warning(f"Universe {universe_id} not found")
            return

        self.terminate_universe(universe_id)
        del self.universes[universe_id]
        log.info(f"Removed sACN universe {universe_id}")

        if self.universe_removed_callback:
            self.universe_removed_callback(universe_id)

    def send_dmx_data(self, universe_id: int, dmx_data: bytearray) -> bool:
        if not self.running:
            log.error("sACN server not running")
            return False

        if universe_id not in self.universes:
            log.error(f"Universe {universe_id} not configured")
            return False

        universe_state = self.universes[universe_id]

        universe_state.pending_data = dmx_data.copy()
        universe_state.last_update_time = time.time()
        log.debug(f"Universe {universe_id}: received new DMX data")

        # Start streaming task if not already running
        if universe_state.stream_task is None or universe_state.stream_task.done():
            log.debug(f"Universe {universe_id}: creating new streaming task")
            universe_state.stream_task = self.hass.async_create_task(self._stream_universe_data(universe_id))

        self.hass.async_create_task(self._send_pending_frame(universe_id))

        return True

    async def _stream_universe_data(self, universe_id: int) -> None:
        """Continuously retransmit last frame on keep-alive timeout.

        New frames are sent immediately via _send_pending_frame when they arrive.
        This loop only handles retransmission if no new data for retransmit_interval seconds.
        """

        try:
            universe_state = self.universes[universe_id]
            log.debug(f"Started streaming task for universe {universe_id}")

            while self.running and universe_id in self.universes and not universe_state.termination_sent:
                time_since_send = time.time() - universe_state.last_send_time

                if universe_state.last_data is not None and time_since_send >= self.config.retransmit_interval:
                    log.debug(f"Universe {universe_id}: retransmitting frame (seq: {universe_state.sequence_number})")
                    await self._send_packet(universe_id, universe_state.last_data)
                    universe_state.increment_sequence()
                    universe_state.last_send_time = time.time()
                else:
                    sleep_duration = self.config.retransmit_interval - time_since_send
                    await asyncio.sleep(sleep_duration)

        except asyncio.CancelledError:
            log.debug(f"Streaming task for universe {universe_id} cancelled")
        except Exception as e:
            log.error(f"Error in streaming loop for universe {universe_id}: {e}")
        finally:
            log.debug(f"Stopped streaming for universe {universe_id}")

    async def _send_pending_frame(self, universe_id: int) -> None:
        """Hot path: send pending frame immediately (called from send_dmx_data)."""
        import time

        try:
            universe_state = self.universes[universe_id]

            if universe_state.pending_data is not None:
                log.debug(f"Universe {universe_id}: sending immediate frame (seq: {universe_state.sequence_number})")
                await self._send_packet(universe_id, universe_state.pending_data)
                universe_state.increment_sequence()
                universe_state.last_data = universe_state.pending_data.copy()
                universe_state.pending_data = None
                universe_state.last_send_time = time.time()
                universe_state.last_update_time = universe_state.last_send_time
                universe_state.termination_sent = False

        except Exception as e:
            log.error(f"Error sending pending frame for universe {universe_id}: {e}")

    async def _send_packet(self, universe_id: int, dmx_data: bytearray) -> None:
        """Send a single sACN packet."""
        try:
            universe_state = self.universes[universe_id]

            processed_data = bytearray(max(25, len(dmx_data)))
            processed_data[0] = 0x00
            processed_data[1 : len(dmx_data)] = dmx_data[1:] if len(dmx_data) > 1 else []

            options = SacnOptions(
                preview_data=self.config.enable_preview_data,
                stream_terminated=False,
                force_synchronization=self.config.enable_per_universe_sync,
            )

            assert self.config.cid is not None  # Guaranteed by __init__
            packet = SacnPacket(
                source_name=self.config.source_name,
                priority=self.config.priority,
                universe=universe_id,
                sequence_number=universe_state.sequence_number,
                options=options,
                cid=self.config.cid,
                dmx_data=processed_data,
            )

            multicast_addr = packet.get_multicast_address()
            packet_bytes = packet.serialize()

            if self.socket is not None:
                log.debug(
                    f"Sending sACN data to universe {universe_id} (multicast {multicast_addr},"
                    f" seq: {universe_state.sequence_number})"
                )
                await self.hass.async_add_executor_job(self.socket.sendto, packet_bytes, (multicast_addr, SACN_PORT))

            for unicast_addr in universe_state.unicast_addresses:
                if self.socket is not None:
                    log.debug(
                        f"Sending sACN data to universe {universe_id} (unicast {unicast_addr['host']}:"
                        f"{unicast_addr['port']}, seq: {universe_state.sequence_number})"
                    )
                    await self.hass.async_add_executor_job(
                        self.socket.sendto,
                        packet_bytes,
                        (unicast_addr["host"], unicast_addr["port"]),
                    )

        except Exception as e:
            log.error(f"Error sending sACN packet for universe {universe_id}: {e}")

    def terminate_universe(self, universe_id: int) -> None:
        if universe_id not in self.universes:
            return

        universe_state = self.universes[universe_id]
        if universe_state.termination_sent:
            return

        if universe_state.stream_task and not universe_state.stream_task.done():
            universe_state.stream_task.cancel()

        try:
            options = SacnOptions(preview_data=False, stream_terminated=True, force_synchronization=False)

            last_data = universe_state.last_data or bytearray(513)

            assert self.config.cid is not None  # Guaranteed by __init__
            packet = SacnPacket(
                source_name=self.config.source_name,
                priority=self.config.priority,
                universe=universe_id,
                sequence_number=universe_state.sequence_number,
                options=options,
                cid=self.config.cid,
                dmx_data=last_data,
            )

            multicast_addr = packet.get_multicast_address()
            packet_bytes = packet.serialize()

            if self.socket is not None:
                for _ in range(3):
                    self.socket.sendto(packet_bytes, (multicast_addr, SACN_PORT))

                    for unicast_addr in universe_state.unicast_addresses:
                        self.socket.sendto(packet_bytes, (unicast_addr["host"], unicast_addr["port"]))

            universe_state.termination_sent = True
            log.info(f"Sent termination packet for sACN universe {universe_id}")

        except Exception as e:
            log.error(f"Error sending termination packet for universe {universe_id}: {e}")

    def send_sync_packet(self, sync_address: int = 0) -> None:
        if not self.running:
            log.error("sACN server not running")
            return

        try:
            assert self.config.cid is not None  # Guaranteed by __init__
            sync_packet = SacnSyncPacket(sequence_number=0, sync_address=sync_address, cid=self.config.cid)

            packet_bytes = sync_packet.serialize()

            if self.socket is not None:
                self.socket.sendto(packet_bytes, ("239.255.0.0", SACN_PORT))
            log.debug(f"Sent sACN sync packet for sync address {sync_address}")

        except Exception as e:
            log.error(f"Error sending sACN sync packet: {e}")

    def get_universe_info(self, universe_id: int) -> dict[str, Any] | None:
        if universe_id not in self.universes:
            return None

        state = self.universes[universe_id]
        return {
            "universe_id": universe_id,
            "sequence_number": state.sequence_number,
            "multicast_address": f"239.255.{universe_id >> 8}.{universe_id & 0xFF}",
            "has_data": state.last_data is not None,
            "termination_sent": state.termination_sent,
        }

    def get_all_universes(self) -> dict[int, dict[str, Any]]:
        return {uid: info for uid in self.universes if (info := self.get_universe_info(uid)) is not None}


class SacnReceiver(asyncio.DatagramProtocol):
    def __init__(
        self,
        hass: HomeAssistant,
        data_callback: Callable[[PortAddress, bytearray, str], None] | None = None,
        own_source_name: str | None = None,
        interface_ip: str | None = None,
    ) -> None:
        self.hass = hass
        self.data_callback = data_callback
        self.transport: asyncio.DatagramTransport | None = None
        self.subscribed_universes: set[int] = set()
        self.own_source_name = own_source_name
        self.interface_ip = interface_ip

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        log.info("sACN receiver connection established")

        for universe_id in self.subscribed_universes:
            self._join_multicast_group(universe_id)

    def connection_lost(self, exc: Exception | None) -> None:
        log.info("sACN receiver connection lost")
        self.transport = None

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            packet = SacnPacket.deserialize(data)

            if packet.universe in self.subscribed_universes:
                log.debug(
                    f"Received sACN data for universe {packet.universe} from {addr[0]} "
                    f"(source: '{packet.source_name}', seq: {packet.sequence_number}, "
                    f"priority: {packet.priority}, channels: {len(packet.dmx_data)})"
                )

                # Ignore packets from our own sACN server to prevent feedback loops
                if self.own_source_name and packet.source_name == self.own_source_name:
                    return

                if self.data_callback:
                    port_address = PortAddress(0, 0, packet.universe)
                    self.data_callback(port_address, packet.dmx_data, packet.source_name)
                else:
                    log.warning("No data callback configured for sACN receiver")
            else:
                log.debug(
                    f"Ignoring sACN data for universe {packet.universe} from {addr[0]} "
                    f"(not subscribed, subscribed universes: {self.subscribed_universes})"
                )

        except Exception as e:
            log.warning(f"Error processing sACN packet from {addr[0]}:{addr[1]} ({len(data)} bytes): {e}")
            log.debug(f"Raw packet data: {data[:50].hex()}{'...' if len(data) > 50 else ''}")

    def subscribe_universe(self, universe_id: int) -> None:
        if not (1 <= universe_id <= 63999):
            log.error(f"Invalid universe ID: {universe_id}")
            return

        self.subscribed_universes.add(universe_id)

        if self.transport:
            self._join_multicast_group(universe_id)

        log.info(f"Subscribed to sACN universe {universe_id}")

    def unsubscribe_universe(self, universe_id: int) -> None:
        if universe_id in self.subscribed_universes:
            self.subscribed_universes.remove(universe_id)

            if self.transport:
                self._leave_multicast_group(universe_id)

            log.info(f"Unsubscribed from sACN universe {universe_id}")

    def _manage_multicast_group(self, universe_id: int, join: bool) -> None:
        """Join or leave multicast group for a universe"""
        multicast_addr = f"239.255.{universe_id >> 8}.{universe_id & 0xFF}"
        try:

            sock = self.transport.get_extra_info("socket") if self.transport else None
            if sock:
                operation = socket.IP_ADD_MEMBERSHIP if join else socket.IP_DROP_MEMBERSHIP
                action = "Joined" if join else "Left"
                if self.interface_ip:
                    mreq = struct.pack("4s4s", socket.inet_aton(multicast_addr), socket.inet_aton(self.interface_ip))
                else:
                    mreq = struct.pack("4sl", socket.inet_aton(multicast_addr), socket.INADDR_ANY)
                sock.setsockopt(socket.IPPROTO_IP, operation, mreq)
                log.debug(f"{action} multicast group {multicast_addr} for universe {universe_id}")
            else:
                log.error(
                    f"No socket available to {'join' if join else 'leave'} multicast group for universe {universe_id}"
                )

        except Exception as e:
            action = "join" if join else "leave"
            log.error(f"Failed to {action} multicast group {multicast_addr} for universe {universe_id}: {e}")

    def _join_multicast_group(self, universe_id: int) -> None:
        self._manage_multicast_group(universe_id, True)

    def _leave_multicast_group(self, universe_id: int) -> None:
        self._manage_multicast_group(universe_id, False)


async def create_sacn_receiver(
    hass: HomeAssistant,
    data_callback: Callable[[PortAddress, bytearray, str], None] | None = None,
    own_source_name: str | None = None,
    interface_ip: str | None = None,
) -> SacnReceiver:
    receiver = SacnReceiver(hass, data_callback, own_source_name, interface_ip)

    loop = hass.loop
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: receiver,
            local_addr=("0.0.0.0", SACN_PORT),  # noqa: S104
        )

        # Set socket options for multicast reception
        sock = transport.get_extra_info("socket")
        if sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            log.debug("Set socket reuse option for sACN receiver")

        log.info("sACN receiver started successfully")
        return receiver

    except Exception as e:
        log.error(f"Failed to create sACN receiver: {e}")
        raise
