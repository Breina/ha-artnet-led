import asyncio
import logging
import socket
import struct
from dataclasses import dataclass
from typing import Callable, Optional

from homeassistant.core import HomeAssistant

log = logging.getLogger(__name__)

ACN_PACKET_IDENTIFIER = b'ASC-E1.31\x00\x00\x00'
VECTOR_ROOT_E131_DATA = b'\x00\x00\x00\x04'
VECTOR_E131_DATA_PACKET = b'\x00\x00\x00\x02'
VECTOR_DMP_SET_PROPERTY = 0x02
SACN_PORT = 5568


@dataclass
class SacnPacket:
    cid: bytes
    source_name: str
    priority: int
    sync_universe: int
    sequence_number: int
    preview_data: bool
    stream_terminated: bool
    universe: int
    start_code: int
    dmx_data: bytearray

    @classmethod
    def deserialize(cls, data: bytes) -> Optional["SacnPacket"]:
        """Parse an incoming sACN (ANSI E1.31) Data Packet."""
        if len(data) < 126:
            return None

        if data[4:16] != ACN_PACKET_IDENTIFIER:
            return None

        root_vector = data[18:22]
        if root_vector != VECTOR_ROOT_E131_DATA:
            return None

        cid = data[22:38]

        framing_vector = data[40:44]
        if framing_vector != VECTOR_E131_DATA_PACKET:
            return None

        source_name = data[44:108].decode('utf-8', errors='ignore').rstrip('\x00')
        priority = data[108]
        sync_universe = int.from_bytes(data[109:111], 'big')
        sequence_number = data[111]
        options = data[112]
        preview_data = bool(options & 0x40)
        stream_terminated = bool(options & 0x80)
        universe = int.from_bytes(data[113:115], 'big')

        dmp_vector = data[117]
        if dmp_vector != VECTOR_DMP_SET_PROPERTY:
            return None

        addr_type = data[118]
        if addr_type != 0xA1:
            return None

        prop_count = int.from_bytes(data[123:125], 'big')
        if prop_count < 1 or len(data) < 125 + prop_count:
            return None

        start_code = data[125]
        dmx_data = bytearray(data[126:125 + prop_count])

        return cls(
            cid=cid,
            source_name=source_name,
            priority=priority,
            sync_universe=sync_universe,
            sequence_number=sequence_number,
            preview_data=preview_data,
            stream_terminated=stream_terminated,
            universe=universe,
            start_code=start_code,
            dmx_data=dmx_data,
        )


class SacnServer(asyncio.DatagramProtocol):
    def __init__(
        self,
        hass: HomeAssistant,
        state_update_callback: Optional[Callable[[int, bytearray], None]] = None,
        bind_address: str = '0.0.0.0',
        port: int = SACN_PORT,
    ):
        super().__init__()
        self.__hass = hass
        self.__state_update_callback = state_update_callback
        self.bind_address = bind_address
        self.port = port

        self._transport: Optional[asyncio.DatagramTransport] = None
        self._socket: Optional[socket.socket] = None
        self._joined_multicast_groups: set[tuple[str, str]] = set()

    @staticmethod
    def get_multicast_ip(universe: int) -> str:
        hi = (universe >> 8) & 0xFF
        lo = universe & 0xFF
        return f"239.255.{hi}.{lo}"

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport  # type: ignore[assignment]
        if hasattr(transport, 'get_extra_info'):
            self._socket = transport.get_extra_info('socket')
        log.info(f"sACN server listening on {self.bind_address}:{self.port}")

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        log.info(f"Raw UDP datagram ({len(data)} bytes) received on port {self.port} from {addr[0]}:{addr[1]}")

        packet = SacnPacket.deserialize(data)
        if not packet:
            log.warning(f"Could not deserialize sACN packet ({len(data)} bytes) from {addr[0]}:{addr[1]}")
            return

        if packet.source_name == "ha-artnet-led":
            return

        log.info(f"Parsed sACN frame for universe {packet.universe} from {addr[0]} (source: {packet.source_name})")

        try:
            self.__hass.add_job(
                self.__hass.components.persistent_notification.create,
                f"sACN packet received for universe {packet.universe} from {addr[0]} (source: {packet.source_name}, DMX slots: {len(packet.dmx_data)})",
                "sACN Inbound Notification"
            )
        except Exception:
            pass

        if self.__state_update_callback:
            self.__state_update_callback(packet.universe, packet.dmx_data)

    def join_multicast_group(self, universe: int, interface_ip: str = '0.0.0.0'):
        if not self._socket:
            log.warning(f"Cannot join multicast group for universe {universe} yet: socket not initialized")
            return

        mcast_ip = self.get_multicast_ip(universe)

        if interface_ip in ("127.0.0.1", "", None):
            interface_ip = "0.0.0.0"

        group_key = (mcast_ip, interface_ip)
        if group_key in self._joined_multicast_groups:
            return

        try:
            mreq = struct.pack('4s4s', socket.inet_aton(mcast_ip), socket.inet_aton(interface_ip))
            self._socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self._joined_multicast_groups.add(group_key)
            log.info(f"Joined sACN multicast group {mcast_ip} for universe {universe} on interface {interface_ip}")
            self._send_igmp_report(mcast_ip)
        except OSError as err:
            if err.errno == 98:  # EADDRINUSE - socket already joined this group/interface
                self._joined_multicast_groups.add(group_key)
                self._send_igmp_report(mcast_ip)
            else:
                log.error(f"Failed to join sACN multicast group {mcast_ip} on interface {interface_ip}: {err}")
        except Exception as err:
            log.error(f"Failed to join sACN multicast group {mcast_ip} on interface {interface_ip}: {err}")


    def _send_igmp_report(self, mcast_ip: str):
        try:
            group_bytes = socket.inet_aton(mcast_ip)
            igmp_type = 0x16  # IGMPv2 Membership Report
            code = 0x00
            msg = bytes([igmp_type, code, 0, 0]) + group_bytes
            s = 0
            for i in range(0, len(msg), 2):
                w = (msg[i] << 8) + msg[i+1]
                s += w
            s = (s >> 16) + (s & 0xffff)
            s += (s >> 16)
            checksum = ~s & 0xffff
            igmp_pkt = bytes([igmp_type, code, checksum >> 8, checksum & 0xff]) + group_bytes

            with socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IGMP) as raw_sock:
                raw_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
                raw_sock.sendto(igmp_pkt, (mcast_ip, 0))
                log.info(f"Sent raw IGMPv2 Join for {mcast_ip}")
        except Exception:
            pass



    async def start_server(self):
        loop = self.__hass.loop

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, 'SO_REUSEPORT'):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except Exception:
                pass
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        except Exception:
            pass

        sock.setblocking(False)
        sock.bind((self.bind_address, self.port))

        self._socket = sock

        transport, _ = await loop.create_datagram_endpoint(lambda: self, sock=sock)
        self._transport = transport
        log.info(f"sACN server listening on port {self.port}")

        async def refresh_igmp_loop():
            while True:
                await asyncio.sleep(90)
                try:
                    for (mcast_ip, _) in list(self._joined_multicast_groups):
                        self._send_igmp_report(mcast_ip)
                except Exception as err:
                    log.debug(f"IGMP refresh error: {err}")

        self.__hass.async_create_background_task(refresh_igmp_loop(), "sACN IGMP Refresh Task")
        return transport

