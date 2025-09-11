import asyncio
import datetime
import logging
import random
import uuid
from _socket import AF_INET, IPPROTO_UDP, SO_BROADCAST, SOCK_DGRAM, SOL_SOCKET, inet_aton, inet_ntoa
from asyncio import Task, transports
from dataclasses import dataclass, field
from socket import socket
from typing import Any

from homeassistant.core import HomeAssistant
from netifaces import AF_INET

from custom_components.dmx.const import HA_OEM
from custom_components.dmx.server import (
    ArtBase,
    ArtCommand,
    ArtDiagData,
    ArtDmx,
    ArtIpProgReply,
    ArtPoll,
    ArtPollReply,
    ArtTimeCode,
    ArtTrigger,
    BootProcess,
    DiagnosticsMode,
    DiagnosticsPriority,
    FailsafeState,
    IndicatorState,
    NodeReport,
    OpCode,
    Port,
    PortAddress,
    PortAddressProgrammingAuthority,
    PortType,
    StyleCode,
)
from custom_components.dmx.server.net_utils import get_default_gateway, get_private_ip

STALE_NODE_CUTOFF_TIME = 10

ARTNET_PORT = 0x1936

RDM_SUPPORT = False  # TODO
SWITCH_TO_SACN_SUPPORT = False  # TODO
ART_ADDRESS_SUPPORT = False  # TODO

HA_PHYSICAL_PORT = 0x00

log = logging.getLogger(__name__)


@dataclass
class Node:
    name: str = "Unknown node"
    addr: bytes = ([0x00] * 4,)
    bind_index: int = (0,)
    mac_address: bytes = ([0x00] * 6,)

    last_seen: datetime.datetime = (datetime.datetime.now(),)
    net_switch: int = (0,)
    sub_switch: int = 0
    ports: list[Port] = None

    def get_addresses(self) -> set[PortAddress]:
        if not self.ports:
            return set()

        addresses = set()

        for port in self.ports:
            if hasattr(port, "input") and port.input:
                addresses.add(PortAddress(self.net_switch, self.sub_switch, port.sw_in))
            if hasattr(port, "output") and port.output:
                addresses.add(PortAddress(self.net_switch, self.sub_switch, port.sw_out))

        return addresses

    def __repr__(self) -> str:
        return str(self)

    def __str__(self):
        return f"{self.net_switch}/{self.sub_switch}/*@{inet_ntoa(self.addr)}#{self.bind_index}"

    def __eq__(self, other):
        return self.addr == other.addr and self.bind_index == other.bind_index

    def __hash__(self) -> int:
        return hash((self.addr, self.bind_index))


@dataclass
class ManualNode:
    port_address: PortAddress = None
    addr: str = ("",)
    port: int = (6454,)


@dataclass
class OwnPort:
    port: Port = field(default_factory=Port)
    data: bytearray | None = None
    update_task: Task[None] = None


class ArtNetServer(asyncio.DatagramProtocol):
    def __init__(
        self,
        hass: HomeAssistant,
        state_update_callback=None,
        firmware_version: int = 0,
        oem: int = HA_OEM,
        esta=0,
        short_name: str = "HA ArtNet",
        long_name: str = "HomeAssistant ArtNet controller",
        is_server_dhcp_configured: bool = True,
        polling: bool = True,
        sequencing: bool = True,
        retransmit_time_ms: int = 900,
    ):
        super().__init__()

        self.__hass = hass
        self.__state_update_callback = state_update_callback

        self.node_new_callback = None
        self.node_update_callback = None
        self.node_lost_callback = None

        self.firmware_version = firmware_version
        self.oem = oem
        self.esta = esta
        self.short_name = short_name
        self.long_name = long_name
        self.dhcp_configured = is_server_dhcp_configured
        self._polling = polling
        self._sequencing = sequencing
        self.sequence_number = 1 if sequencing else 0
        self.retransmit_time_ms = retransmit_time_ms

        self.own_port_addresses = {}
        self.node_change_subscribers = set()

        self.nodes_by_ip = {}
        self.nodes_by_port_address = {}
        self.manual_nodes_by_port_address = {}

        self._own_ip = inet_aton(get_private_ip())
        self._default_gateway = inet_aton(get_default_gateway())

        self.indicator_state = IndicatorState.LOCATE_IDENTIFY
        self.node_report = NodeReport.RC_POWER_OK
        self.status_message = "Initializing ArtNet server..."
        self.art_poll_reply_counter = 0
        self.swout_text = "Output"
        self.swin_text = "Input"

        self.startup_time = None

        self.mac = uuid.getnode().to_bytes(6, "big")

    def uptime(self) -> int:
        return (datetime.datetime.now() - self.startup_time).seconds if self.startup_time else 0

    def _update_status_message(self):
        """Update status message based on current server state"""
        node_count = len(self.nodes_by_ip)
        port_count = len(self.own_port_addresses)
        active_outputs = sum(
            1 for own_port in self.own_port_addresses.values() if own_port.port.good_output_a.data_being_transmitted
        )
        active_inputs = sum(
            1 for own_port in self.own_port_addresses.values() if own_port.port.good_input.data_received
        )
        manual_nodes = len(self.manual_nodes_by_port_address)

        if node_count == 0 and port_count == 0:
            self.status_message = "Ready - No ports configured"
            self.indicator_state = IndicatorState.LOCATE_IDENTIFY
        elif node_count == 0 and port_count > 0:
            if manual_nodes > 0:
                self.status_message = f"Active - {port_count} ports, {manual_nodes} manual nodes"
            else:
                self.status_message = f"Scanning - {port_count} ports, no nodes found"
            self.indicator_state = IndicatorState.NORMAL_MODE
        else:
            parts = [f"{node_count} nodes", f"{port_count} ports"]
            if active_outputs > 0:
                parts.append(f"{active_outputs} transmitting")
            if active_inputs > 0:
                parts.append(f"{active_inputs} receiving")
            if manual_nodes > 0:
                parts.append(f"{manual_nodes} manual")
            self.status_message = f"Active - {', '.join(parts)}"
            self.indicator_state = IndicatorState.NORMAL_MODE

    def add_port(self, port_address: PortAddress):
        port = Port(
            input=True, output=True, type=PortType.ART_NET, sw_in=port_address.universe, sw_out=port_address.universe
        )

        self.own_port_addresses[port_address] = OwnPort(port)
        self._update_status_message()
        self.update_subscribers()

    def remove_port(self, port_address: PortAddress):
        del self.own_port_addresses[port_address]
        self._update_status_message()
        self.update_subscribers()

    def get_port_bounds(self) -> tuple[PortAddress, PortAddress] | None:
        port_addresses = self.own_port_addresses.keys()
        if not port_addresses:
            return None
        return min(port_addresses), max(port_addresses)

    def add_manual_node(self, manual_node: ManualNode):
        self.manual_nodes_by_port_address[manual_node.port_address] = manual_node
        self._update_status_message()

    def get_node_by_ip(self, addr: bytes, bind_index: int = 1) -> Node | None:
        return self.nodes_by_ip.get((addr, bind_index), None)

    def add_node_by_ip(self, node: Node, addr: bytes, bind_index: int = 1):
        self.nodes_by_ip[(addr, bind_index)] = node

    def get_node_by_port_address(self, port_address: PortAddress) -> set[Node] | None:
        return self.nodes_by_port_address.get(port_address, None)

    def add_node_by_port_address(self, port_address: PortAddress, node: Node):
        nodes = self.nodes_by_port_address.get(port_address)
        if nodes:
            if node not in nodes:
                nodes.add(node)

                if self.uptime() > 3:
                    own_port: OwnPort = self.own_port_addresses.get(port_address, None)
                    if own_port and own_port.data:
                        log.info("Since we have data on that node already, let's send an update immediately to it!")
                        self.send_dmx(port_address, own_port.data)

        else:
            self.nodes_by_port_address[port_address] = {node}

    def remove_node_by_port_address(self, port_address: PortAddress, node: Node):
        nodes = self.nodes_by_port_address[port_address]
        if not nodes:
            return
        if node in nodes:
            nodes.remove(node)
        if not nodes:
            del self.nodes_by_port_address[port_address]

        if node not in self.nodes_by_ip.values():
            ip_str = inet_ntoa(node.addr)
            if ip_str in self.node_change_subscribers:
                self.node_change_subscribers.remove(ip_str)
                self.node_lost_callback(node)

    def update_subscribers(self):
        for subscriber in self.node_change_subscribers:
            self.send_reply(subscriber)

    def get_grouped_ports(self) -> [(int, int, [[Port]])]:
        # Sort the ports by their net and subnet
        net_sub = set(map(lambda p: (p.net, p.sub_net), self.own_port_addresses))
        grouped_list = [
            [ns[0], ns[1], [p.universe for p in self.own_port_addresses if (p.net, p.sub_net) == ns]] for ns in net_sub
        ]

        for gli in grouped_list:
            # Chunk the universes into lists of at most 4
            chunked_universes = [gli[2][i : i + 4] for i in range(0, len(gli[2]), 4)]

            # Put the Port as value, instead of just universe number
            gli[2] = [
                list(map(lambda u: self.own_port_addresses[PortAddress(gli[0], gli[1], u)].port, chunked_universe))
                for chunked_universe in chunked_universes
            ]

        return grouped_list

    def start_server(self):
        loop = self.__hass.loop
        server_event = loop.create_datagram_endpoint(lambda: self, local_addr=("0.0.0.0", ARTNET_PORT))

        self.status_message = "Starting server on port 6454..."

        if self._polling:
            self.__hass.async_create_background_task(self.start_poll_loop(), "Art-Net polling loop")
        log.info("ArtNet server started")

        return self.__hass.async_create_task(server_event)

    async def start_poll_loop(self):
        while True:
            poll = ArtPoll()
            port_bounds = self.get_port_bounds()
            if port_bounds:
                poll.target_port_bounds = port_bounds
                poll.notify_on_change = True
                poll.enable_diagnostics(DiagnosticsMode.UNICAST, DiagnosticsPriority.DP_HIGH)

                log.debug("Sending ArtPoll")
                with socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP) as sock:
                    sock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
                    sock.setblocking(False)
                    sock.sendto(poll.serialize(), ("255.255.255.255", 0x1936))

                if len(self.nodes_by_ip) == 0:
                    self.status_message = f"Polling network - {len(self.own_port_addresses)} ports configured"

                self.__hass.async_create_background_task(self.remove_stale_nodes(), "Art-Net remove stale nodes")

                log.debug("Sleeping a few seconds before polling again...")
            else:
                self.status_message = "Idle - No ports configured"

            await asyncio.sleep(random.uniform(2.5, 3))

    async def remove_stale_nodes(self):
        await asyncio.sleep(STALE_NODE_CUTOFF_TIME)

        now = datetime.datetime.now()
        cutoff_time: datetime.datetime = now - datetime.timedelta(seconds=STALE_NODE_CUTOFF_TIME)

        nodes_by_ip_to_delete = []
        stale_count = 0

        for (ip, bind_index), node in self.nodes_by_ip.items():
            if node.last_seen > cutoff_time:
                continue

            time_delta: datetime.timedelta = now - node.last_seen
            stale_count += 1

            log.warning(
                f"Haven't seen node {inet_ntoa(ip)}#{bind_index} for {time_delta.seconds} seconds;" f" removing it."
            )
            nodes_by_ip_to_delete += [(ip, bind_index)]
            for node_address in node.get_addresses():
                self.remove_node_by_port_address(node_address, node)

        for ip, bind_index in nodes_by_ip_to_delete:
            del self.nodes_by_ip[(ip, bind_index)]

        if stale_count > 0:
            self.status_message = f"Cleaned up {stale_count} stale nodes"
            self._update_status_message()

    @staticmethod
    def send_artnet(art_packet: ArtBase, ip: str):
        with socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP) as sock:
            sock.setblocking(False)
            sock.sendto(art_packet.serialize(), (ip, ARTNET_PORT))

    def send_diagnostics(
        self,
        addr: str = None,
        diagnostics_priority=DiagnosticsPriority.DP_MED,
        diagnostics_mode=DiagnosticsMode.BROADCAST,
    ):
        diag_data = ArtDiagData(diag_priority=diagnostics_priority, logical_port=0, text=self.status_message)
        address = addr if diagnostics_mode == DiagnosticsMode.UNICAST else bytes("255.255.255.255")
        self.send_artnet(diag_data, address)

    def send_reply(self, addr):
        grouped_ports = self.get_grouped_ports()
        bind_index = 1 if len(grouped_ports) > 1 else 0

        log.debug("Sending ArtPollReply!")
        for net, sub_net, ports_chunk in grouped_ports:
            log.debug(f"ArtPollReply's bind index = {bind_index}")

            for ports in ports_chunk:
                node_report = self.node_report.report(self.art_poll_reply_counter, self.status_message)

                poll_reply = ArtPollReply(
                    source_ip=self._own_ip,
                    firmware_version=self.firmware_version,
                    net_switch=net,
                    sub_switch=sub_net,
                    oem=self.oem,
                    indicator_state=self.indicator_state,
                    port_address_programming_authority=PortAddressProgrammingAuthority.PROGRAMMATIC,
                    boot_process=BootProcess.FLASH,
                    supports_rdm=RDM_SUPPORT,
                    esta=0,
                    short_name=self.short_name,
                    long_name=self.long_name,
                    node_report=node_report,
                    ports=ports,
                    style=StyleCode.ST_CONTROLLER,
                    mac_address=self.mac,
                    supports_web_browser_configuration=True,
                    dhcp_configured=self.dhcp_configured,
                    dhcp_capable=True,
                    supports_15_bit_port_address=True,
                    supports_switching_to_sacn=SWITCH_TO_SACN_SUPPORT,
                    squawking=RDM_SUPPORT,
                    supports_switching_of_output_style=ART_ADDRESS_SUPPORT,
                    bind_index=bind_index,
                    supports_rdm_through_artnet=RDM_SUPPORT,
                    failsafe_state=FailsafeState.HOLD_LAST_STATE,
                )

                log.debug(
                    f"Sending ArtPollReply from bind_index {bind_index} for {net}/{sub_net}/"
                    f"[{','.join([str(p.sw_out) for p in ports])}]"
                )
                self.send_artnet(poll_reply, addr)

                self.art_poll_reply_counter += 1
                if bind_index != 0:
                    bind_index += 1

    def send_dmx(self, address: PortAddress, data: bytearray) -> Task[None] | None:
        has_manual_node = address in self.manual_nodes_by_port_address

        if not has_manual_node and not self.get_node_by_port_address(address):
            if self.uptime() < 3:
                log.debug("Can't currently send DMX as nodes haven't had the chance to be discovered.")
                return None

            if len(self.nodes_by_port_address) == 0:
                self.status_message = "Error - No nodes found for DMX output"
                log.error(
                    "The server hasn't received replies from any node at all. We don't know where we can "
                    "send the DMX data to. If this message persists, consider configuring manual_nodes "
                    "under the compatibility section."
                )
            else:
                self.status_message = f"Warning - No nodes for universe {address.universe}"
                log.error(
                    f"No nodes found that listen to port address {address}. Current nodes: "
                    f"{self.nodes_by_port_address.keys()}"
                )
            return None

        own_port = self.own_port_addresses[address]
        if own_port.update_task:
            own_port.update_task.cancel()

        is_already_outputting = own_port.port.good_output_a.data_being_transmitted
        if not is_already_outputting:
            own_port.port.good_output_a.data_being_transmitted = True
            self._update_status_message()
            self.update_subscribers()

        task = self.__hass.async_create_background_task(
            self.start_artdmx_loop(address, data, own_port, has_manual_node), f"Art-Net DMX loop {address}"
        )
        own_port.update_task = task
        return task

    async def start_artdmx_loop(self, address, data, own_port, has_manual_node: bool = False):
        own_port.data = data
        art_dmx = ArtDmx(
            sequence_number=self.sequence_number, physical=HA_PHYSICAL_PORT, port_address=address, data=data
        )
        packet = art_dmx.serialize()

        while True:
            nodes = self.get_node_by_port_address(address)
            if not has_manual_node and not nodes:
                log.warning(
                    f"No nodes found that listen to port address {address}. " f"Stopping sending ArtDmx refreshes..."
                )
                own_port.port.good_output_a.data_being_transmitted = False
                self._update_status_message()
                self.update_subscribers()
            elif nodes:
                with socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP) as sock:
                    sock.setblocking(False)
                    for node in nodes:
                        ip_str = inet_ntoa(node.addr)
                        log.debug(f"Sending ArtDmx to {ip_str}")
                        sock.sendto(packet, (ip_str, ARTNET_PORT))

            if has_manual_node:
                manual_node = self.manual_nodes_by_port_address[address]
                with socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP) as sock:
                    sock.setblocking(False)
                    log.debug(f"Sending manually ArtDmx to {manual_node.addr}")
                    sock.sendto(packet, (manual_node.addr, manual_node.port))

            if self._sequencing:
                self.sequence_number += 0x01
                if self.sequence_number > 0xFF:
                    self.sequence_number = 0x01
                art_dmx.sequence_number = self.sequence_number
                packet = art_dmx.serialize()

            if self.retransmit_time_ms == 0:
                return

            await asyncio.sleep(self.retransmit_time_ms / 1000.0)

    def connection_made(self, transport: transports.DatagramTransport) -> None:
        self.startup_time = datetime.datetime.now()
        self.status_message = "Server started successfully"
        log.debug("Server connection made")
        super().connection_made(transport)

    def connection_lost(self, exc: Exception | None) -> None:
        self.status_message = "Server connection lost"
        super().connection_lost(exc)

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        self.handle_datagram(addr, data)

    def handle_datagram(self, addr, data):
        data = bytearray(data)
        opcode = ArtBase.peek_opcode(data)
        if opcode == OpCode.OP_POLL:
            poll = ArtPoll()
            poll.deserialize(data)

            log.debug(f"Received ArtPoll from {addr[0]}")
            self.handle_poll(addr, poll)

        elif opcode == OpCode.OP_POLL_REPLY:
            reply = ArtPollReply()
            reply.deserialize(data)

            log.debug(f"Received ArtPollReply from {reply.long_name}")
            self.handle_poll_reply(addr, reply)

        elif opcode == OpCode.OP_IP_PROG:
            log.debug(f"Received IP prog request from {addr[0]}, ignoring...")

        elif opcode == OpCode.OP_IP_PROG_REPLY:
            ip_prog_reply = ArtIpProgReply()
            ip_prog_reply.deserialize(data)

            log.debug(
                f"Received IP prog reply from {addr[0]}:\n"
                f"  IP      : {ip_prog_reply.prog_ip}\n"
                f"  Subnet  : {ip_prog_reply.prog_subnet}\n"
                f"  Gateway : {ip_prog_reply.prog_gateway}\n"
                f"  DHCP    : {ip_prog_reply.dhcp_enabled}"
            )
            #                 TODO set port.good_input.data_received

        elif opcode == OpCode.OP_ADDRESS:
            log.debug(f"Received Adress request from {addr[0]}, not doing anything with it...")

        elif opcode == OpCode.OP_DIAG_DATA:
            diag_data = ArtDiagData()
            diag_data.deserialize(data)

            log.debug(
                f"Received Diag Data from {addr[0]}:\n"
                f"  Priority     : {diag_data.diag_priority}\n"
                f"  Logical port : {diag_data.logical_port}\n"
                f"  Text         : {diag_data.text}"
            )

        elif opcode == OpCode.OP_TIME_CODE:
            timecode = ArtTimeCode()
            timecode.deserialize(data)

            log.debug(
                f"Received Time Code from {addr[0]}:\n"
                f"  Current time/frame : {timecode.hours}:{timecode.minutes}:{timecode.seconds}.{timecode.frames}\n"
                f"  Type               : {timecode.type}"
            )

        elif opcode == OpCode.OP_COMMAND:
            command = ArtCommand()
            command.deserialize(data)

            log.debug(
                f"Received command from {addr[0]}\n" f"  ESTA    : {command.esta}\n" f"  Command : {command.command}"
            )
            self.handle_command(command)

        elif opcode == OpCode.OP_TRIGGER:
            trigger = ArtTrigger()
            trigger.deserialize(data)

            log.debug(
                f"Received trigger from {addr[0]}\n"
                f"  OEM    : {trigger.oem}\n"
                f"  Key    : {trigger.key}\n"
                f"  Subkey : {trigger.sub_key}"
            )
            self.handle_trigger(trigger)

        elif opcode == OpCode.OP_OUTPUT_DMX:
            dmx = ArtDmx()
            dmx.deserialize(data)

            log.debug(f"Received DMX data from {addr[0]}\n" f"  Address: {dmx.port_address}")
            self.handle_dmx(dmx, addr)

        elif opcode == OpCode.OP_SYNC:
            # No action
            pass

        else:
            log.warning(f"Received Opcode {opcode}, which isn't supported yet!")

    def should_handle_ports(self, lower_port: PortAddress, upper_port: PortAddress) -> bool:
        if not self.own_port_addresses:
            return False

        port_bounds = self.get_port_bounds()
        if not port_bounds:
            return False

        return not (lower_port > port_bounds[1] or upper_port < port_bounds[0])

    def handle_poll_reply(self, addr, reply):
        if reply.source_ip is not bytes([0x00] * 4):
            source_ip = inet_aton(inet_ntoa(reply.source_ip))
        else:
            source_ip = inet_aton(addr[0])

        if addr == self._own_ip:
            log.debug("Ignoring ArtPollReply as it came ourselves own address.")
            return

        # The device should wait for a random delay of up to 1s before sending the reply. This mechanism is intended
        # to reduce packet bunching when scaling up to very large systems.
        # TODO somehow this causes the `reply` to become fucked up?
        # await asyncio.sleep(random.uniform(0, 1))

        if reply.node_report:
            log.debug(f"  {reply.node_report}")

        # Maintain data structures
        bind_index = reply.bind_index
        node = self.get_node_by_ip(source_ip, bind_index)
        mac_address = reply.mac_address

        current_time = datetime.datetime.now()
        if not node:
            node = Node(reply.short_name, source_ip, bind_index, mac_address, current_time)
            self.add_node_by_ip(node, source_ip, bind_index)
            log.info(
                f"Discovered new node at {inet_ntoa(source_ip)}@{bind_index} with "
                f"{reply.net_switch}/{reply.sub_switch}/[{','.join([str(p.sw_out) for p in reply.ports if p.output])}]"
            )

            if self.node_new_callback:
                self.node_new_callback(reply)

        else:
            node.last_seen = current_time
            log.debug(
                f"Existing node checking in {inet_ntoa(source_ip)}@{bind_index} with "
                f"{reply.net_switch}/{reply.sub_switch}/[{','.join([str(p.sw_out) for p in reply.ports])}]"
            )
            if self.node_update_callback:
                self.node_update_callback(reply)

        old_addresses = node.get_addresses()
        node.net_switch = reply.net_switch
        node.sub_switch = reply.sub_switch
        node.ports = reply.ports

        new_addresses = node.get_addresses()
        log.debug(
            f"Addresses of the node at {inet_ntoa(source_ip)}@{bind_index}: {new_addresses}, old addresses were: {old_addresses}"
        )
        addresses_to_remove = old_addresses - new_addresses

        for address_to_remove in addresses_to_remove:
            self.remove_node_by_port_address(address_to_remove, node)

        for new_address in new_addresses:
            self.add_node_by_port_address(new_address, node)

            if source_ip != self._own_ip:
                self.indicator_state = IndicatorState.MUTE_MODE

        # Update status after processing node changes
        self._update_status_message()

    def handle_poll(self, addr: tuple[str | Any, int], poll: ArtPoll):
        if inet_aton(addr[0]) == self._own_ip:
            log.debug("Ignoring ArtPoll as it came from ourselves")
            return

        if poll.targeted_mode_enabled and not self.should_handle_ports(*poll.target_port_bounds):
            log.debug("Received ArtPoll, but ignoring it since none of its universes overlap with our universes.")
            return

        if poll.notify_on_change:
            self.node_change_subscribers.add(addr[0])

        self.send_reply(addr[0])

        if poll.is_diagnostics_enabled:
            self.send_diagnostics(
                addr=addr[0], diagnostics_mode=DiagnosticsMode.UNICAST, diagnostics_priority=poll.diagnostics_priority
            )

    def handle_command(self, command: ArtCommand):
        if command.esta == 0xFFFF:
            commands = command.command.split("&")
            for c in commands:
                c = c.strip(" ")
                if c:
                    key, value = c.split("=")
                    key = key.lower()
                    if key == "SwoutText".lower():
                        self.swout_text = value
                        log.debug(f"Set Sw out text to: {value}")
                    elif key == "SwinText".lower():
                        self.swin_text = value
                        log.debug(f"Set Sw in text to: {value}")
        # TODO check if it would be cool to add HA specific commands?

    def handle_trigger(self, trigger: ArtTrigger):
        null_index = trigger.payload.find(b"\x00")
        payload_bytes = trigger.payload[:null_index] if null_index != -1 else trigger.payload[:null_index]

        payload_str = ""

        try:
            # Primary: Try UTF-8 decoding
            payload_str = payload_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                # Fallback 1: Try UTF-8 with error replacement
                payload_str = payload_bytes.decode("utf-8", errors="replace")
            except Exception:
                try:
                    # Fallback 2: Try latin-1 (can decode any byte sequence)
                    payload_str = payload_bytes.decode("latin-1")
                except Exception:
                    # Fallback 3: Convert to hex representation as last resort
                    payload_str = payload_bytes.hex()

        self.__hass.bus.fire(
            "artnet_trigger",
            {"oem": trigger.oem, "key": trigger.key, "sub_key": trigger.sub_key, "payload": payload_str},
        )

    def handle_dmx(self, dmx: ArtDmx, sender_addr: tuple[str, int] = None):
        own_port = self.own_port_addresses.get(dmx.port_address)
        if not own_port:
            log.debug(f"Received ArtDmx for port address that we don't care about: {dmx.port_address}")
            return

        if not own_port.port.good_input.data_received:
            own_port.port.good_input.data_received = True
            self.update_subscribers()

        own_port.port.last_input_seen = datetime.datetime.now()
        self.__hass.async_create_task(self.disable_input_flag(own_port))

        # Find the sender node information
        sender_node_name = "Unknown controller"

        if sender_addr:
            sender_ip = sender_addr[0]
            sender_ip_bytes = inet_aton(sender_ip)

            for (ip_bytes, bind_index), node in self.nodes_by_ip.items():
                if ip_bytes == sender_ip_bytes:
                    sender_node_name = node.name
                    break

        if self.__state_update_callback:
            self.__state_update_callback(dmx.port_address, dmx.data, sender_node_name)

    async def disable_input_flag(self, own_port: OwnPort):
        await asyncio.sleep(4)

        cutoff_time = datetime.datetime.now() - datetime.timedelta(seconds=4)

        if own_port.port.last_input_seen < cutoff_time:
            own_port.port.good_input.data_received = False
            self.update_subscribers()

