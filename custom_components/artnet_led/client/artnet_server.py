import asyncio
import datetime
import logging
import random
import uuid
from asyncio import transports, Task
from dataclasses import dataclass, field
from socket import socket
from typing import Any, Union

from _socket import SO_BROADCAST, AF_INET, SOCK_DGRAM, SOL_SOCKET, IPPROTO_UDP, inet_aton, inet_ntoa
from homeassistant.core import HomeAssistant
from netifaces import AF_INET

from custom_components.artnet_led.client import OpCode, ArtBase, ArtPoll, ArtPollReply, PortAddress, IndicatorState, \
    PortAddressProgrammingAuthority, BootProcess, NodeReport, Port, PortType, StyleCode, FailsafeState, \
    DiagnosticsMode, DiagnosticsPriority, ArtIpProgReply, ArtDiagData, ArtTimeCode, ArtCommand, ArtTrigger, ArtDmx
from custom_components.artnet_led.client.net_utils import get_private_ip, get_default_gateway

STALE_NODE_CUTOFF_TIME = 10

ARTNET_PORT = 0x1936

RDM_SUPPORT = False  # TODO
SWITCH_TO_SACN_SUPPORT = False  # TODO
ART_ADDRESS_SUPPORT = False  # TODO

HA_PHYSICAL_PORT = 0x00

log = logging.getLogger(__name__)


@dataclass
class Node:
    addr: bytes = [0x00] * 4,
    bind_index: int = 0,

    last_seen: datetime.datetime = datetime.datetime.now(),
    net_switch: int = 0,
    sub_switch: int = 0
    ports: list[Port] = None

    def get_addresses(self) -> set[PortAddress]:
        if not self.ports:
            return set()

        input_ports = set(map(lambda port: PortAddress(self.net_switch, self.sub_switch, port.sw_in),
                              filter(lambda port: port.input, self.ports)
                              ))
        output_ports = set(map(lambda port: PortAddress(self.net_switch, self.sub_switch, port.sw_out),
                               filter(lambda port: port.output, self.ports)
                               ))

        return input_ports.union(output_ports)

    def __repr__(self) -> str:
        return str(self)

    def __str__(self):
        return f"{self.net_switch}:{self.sub_switch}:*@{inet_ntoa(self.addr)}#{self.bind_index}"

    def __eq__(self, other):
        return self.addr == other.addr and self.bind_index == other.bind_index

    def __hash__(self) -> int:
        return hash((self.addr, self.bind_index))


@dataclass
class OwnPort:
    port: Port = field(default_factory=Port)
    data: bytearray | None = None
    update_task: Task[None] = None


class ArtNetServer(asyncio.DatagramProtocol):
    def __init__(self, hass: HomeAssistant, state_update_callback=None, new_node_callback=None,
                 firmware_version: int = 0,
                 oem: int = 0, esta=0,
                 short_name: str = "PyArtNet", long_name: str = "Python ArtNet Server",
                 is_server_dhcp_configured: bool = True, polling: bool = True, sequencing: bool = True,
                 retransmit_time_ms: int = 900):
        super().__init__()

        self.__hass = hass
        self.__state_update_callback = state_update_callback
        self.__new_node_callback = new_node_callback
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

        self._own_ip = inet_aton(get_private_ip())
        self._default_gateway = inet_aton(get_default_gateway())

        self.indicator_state = IndicatorState.LOCATE_IDENTIFY
        self.node_report = NodeReport.RC_POWER_OK
        self.status_message = "Starting ArtNet server..."
        self.art_poll_reply_counter = 0
        self.swout_text = "Output"
        self.swin_text = "Input"

        self.startup_time = None

        self.mac = uuid.getnode().to_bytes(6, "big")

    def uptime(self) -> int:
        return (datetime.datetime.now() - self.startup_time).seconds if self.startup_time else 0

    def add_port(self, port_address: PortAddress):
        port = Port(input=True, output=True, type=PortType.ART_NET,
                    sw_in=port_address.universe, sw_out=port_address.universe)

        self.own_port_addresses[port_address] = OwnPort(port)
        self.update_subscribers()

    def remove_port(self, port_address: PortAddress):
        del self.own_port_addresses[port_address]
        self.update_subscribers()

    def get_port_bounds(self) -> Union[tuple[PortAddress, PortAddress], None]:
        port_addresses = self.own_port_addresses.keys()
        if not port_addresses:
            return None
        return min(port_addresses), max(port_addresses)

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
                        log.info(f"Since we have data on that node already, let's send an update immediately to it!")
                        self.send_dmx(port_address, own_port.data)

        else:
            self.nodes_by_port_address[port_address] = {node}

    def remove_node_by_ip(self, addr: bytes, bind_index: int = 1):
        del self.nodes_by_ip[addr, bind_index]

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

    def update_subscribers(self):
        for subscriber in self.node_change_subscribers:
            self.send_reply(subscriber)

    def get_grouped_ports(self) -> [(int, int, [[Port]])]:
        # Sort the ports by their net and subnet
        net_sub = set(map(lambda p: (p.net, p.sub_net), self.own_port_addresses))
        grouped_list = [
            [
                ns[0],
                ns[1],
                [p.universe for p in self.own_port_addresses if (p.net, p.sub_net) == ns]
            ]
            for ns in net_sub
        ]

        for gli in grouped_list:
            # Chunk the universes into lists of at most 4
            chunked_universes = [gli[2][i:i + 4] for i in range(0, len(gli[2]), 4)]

            # Put the Port as value, instead of just universe number
            gli[2] = [
                list(map(lambda u: self.own_port_addresses[PortAddress(gli[0], gli[1], u)].port, chunked_universe))
                for chunked_universe in chunked_universes
            ]

        return grouped_list

    def start_server(self):
        loop = self.__hass.loop
        server_event = loop.create_datagram_endpoint(lambda: self, local_addr=('0.0.0.0', ARTNET_PORT))

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

                self.__hass.async_create_background_task(self.remove_stale_nodes(), "Art-Net remove stale nodes")

                log.debug("Sleeping a few seconds before polling again...")
            await asyncio.sleep(random.uniform(2.5, 3))

    async def remove_stale_nodes(self):
        await asyncio.sleep(STALE_NODE_CUTOFF_TIME)

        now = datetime.datetime.now()
        cutoff_time: datetime.datetime = now - datetime.timedelta(seconds=STALE_NODE_CUTOFF_TIME)

        nodes_by_ip_to_delete = []

        for (ip, bind_index), node in self.nodes_by_ip.items():
            if node.last_seen > cutoff_time:
                continue

            time_delta: datetime.timedelta = now - node.last_seen

            log.warning(f"Haven't seen node {inet_ntoa(ip)}#{bind_index} for {time_delta.seconds} seconds;"
                        f" removing it.")
            nodes_by_ip_to_delete += [(ip, bind_index)]
            for node_address in node.get_addresses():
                self.remove_node_by_port_address(node_address, node)

        for (ip, bind_index) in nodes_by_ip_to_delete:
            del self.nodes_by_ip[(ip, bind_index)]

    @staticmethod
    def send_artnet(art_packet: ArtBase, ip: str):
        with socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP) as sock:
            sock.setblocking(False)
            sock.sendto(art_packet.serialize(), (ip, ARTNET_PORT))

    def send_diagnostics(self, addr: str = None, diagnostics_priority=DiagnosticsPriority.DP_MED,
                         diagnostics_mode=DiagnosticsMode.BROADCAST):
        diag_data = ArtDiagData(diag_priority=diagnostics_priority, logical_port=0, text=self.status_message)
        address = addr if diagnostics_mode == DiagnosticsMode.UNICAST else bytes("255.255.255.255")
        self.send_artnet(diag_data, address)

    def send_reply(self, addr):
        bind_index = None
        for (net, sub_net, ports_chunk) in self.get_grouped_ports():
            if bind_index is None:
                bind_index = 0 if len(ports_chunk) == 1 else 1

            for ports in ports_chunk:
                node_report = self.node_report.report(self.art_poll_reply_counter, self.status_message)

                poll_reply = ArtPollReply(
                    source_ip=self._own_ip, firmware_version=self.firmware_version, net_switch=net,
                    sub_switch=sub_net, oem=self.oem, indicator_state=IndicatorState.LOCATE_IDENTIFY,
                    port_address_programming_authority=PortAddressProgrammingAuthority.PROGRAMMATIC,
                    boot_process=BootProcess.FLASH, supports_rdm=RDM_SUPPORT, esta=0,
                    short_name=self.short_name, long_name=self.long_name, node_report=node_report,
                    ports=ports, style=StyleCode.ST_CONTROLLER, mac_address=self.mac,
                    supports_web_browser_configuration=True, dhcp_configured=self.dhcp_configured,
                    dhcp_capable=True, supports_15_bit_port_address=True,
                    supports_switching_to_sacn=SWITCH_TO_SACN_SUPPORT, squawking=RDM_SUPPORT,
                    supports_switching_of_output_style=ART_ADDRESS_SUPPORT, bind_index=bind_index,
                    supports_rdm_through_artnet=RDM_SUPPORT, failsafe_state=FailsafeState.HOLD_LAST_STATE
                )

                log.debug(f"Sending ArtPollReply from bind_index {bind_index} for {net}/{sub_net}/"
                          f"[{','.join([str(p.sw_out) for p in ports])}]"
                          )
                self.send_artnet(poll_reply, addr)

                self.art_poll_reply_counter += 1
                if bind_index != 0:
                    bind_index += 1

    def send_dmx(self, address: PortAddress, data: bytearray) -> Task[None] | None:
        if not self.get_node_by_port_address(address):
            if self.uptime() < 3:
                log.debug("Can't currently send DMX as nodes haven't had the chance to be discovered.")
                return

            if len(self.nodes_by_port_address) == 0:
                log.error("The server hasn't received replies from any node at all. We don't know where we can "
                          "send the DMX data to. If this message persists, consider using direct mode instead of "
                          "the ArtNet server.")
            else:
                log.error(f"No nodes found that listen to port address {address}. Current nodes: "
                          f"{self.nodes_by_port_address.keys()}")
            return

        own_port = self.own_port_addresses[address]
        if own_port.update_task:
            own_port.update_task.cancel()

        is_already_outputting = own_port.port.good_output_a.data_being_transmitted
        if not is_already_outputting:
            own_port.port.good_output_a.data_being_transmitted = True
            self.update_subscribers()

        task = self.__hass.async_create_task(self.start_artdmx_loop(address, data, own_port))
        own_port.update_task = task
        return task

    async def start_artdmx_loop(self, address, data, own_port):
        own_port.data = data
        art_dmx = ArtDmx(sequence_number=self.sequence_number, physical=HA_PHYSICAL_PORT, port_address=address,
                         data=data)
        packet = art_dmx.serialize()

        while True:
            nodes = self.get_node_by_port_address(address)
            if not nodes:
                log.warning(f"No nodes found that listen to port address {address}. "
                            f"Stopping sending ArtDmx refreshes...")
                own_port.port.good_output_a.data_being_transmitted = False
                self.update_subscribers()
            else:
                with socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP) as sock:
                    sock.setblocking(False)
                    for node in nodes:
                        ip_str = inet_ntoa(node.addr)
                        log.debug(f"Sending ArtDmx to {ip_str}")
                        sock.sendto(packet, (ip_str, ARTNET_PORT))

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
        log.debug("Server connection made")
        super().connection_made(transport)

    def connection_lost(self, exc: Exception | None) -> None:
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

            log.debug(f"Received IP prog reply from {addr[0]}:\n"
                      f"  IP      : {ip_prog_reply.prog_ip}\n"
                      f"  Subnet  : {ip_prog_reply.prog_subnet}\n"
                      f"  Gateway : {ip_prog_reply.prog_gateway}\n"
                      f"  DHCP    : {ip_prog_reply.dhcp_enabled}")
            #                 TODO set port.good_input.data_received

        elif opcode == OpCode.OP_ADDRESS:
            log.debug(f"Received Adress request from {addr[0]}, not doing anything with it...")

        elif opcode == OpCode.OP_DIAG_DATA:
            diag_data = ArtDiagData()
            diag_data.deserialize(data)

            log.debug(f"Received Diag Data from {addr[0]}:\n"
                      f"  Priority     : {diag_data.diag_priority}\n"
                      f"  Logical port : {diag_data.logical_port}\n"
                      f"  Text         : {diag_data.text}")

        elif opcode == OpCode.OP_TIME_CODE:
            timecode = ArtTimeCode()
            timecode.deserialize(data)

            log.debug(f"Received Time Code from {addr[0]}:\n"
                      f"  Current time/frame : {timecode.hours}:{timecode.minutes}:{timecode.seconds}.{timecode.frames}\n"
                      f"  Type               : {timecode.type}")

        elif opcode == OpCode.OP_COMMAND:
            command = ArtCommand()
            command.deserialize(data)

            log.debug(f"Received command from {addr[0]}\n"
                      f"  ESTA    : {command.esta}\n"
                      f"  Command : {command.command}")
            self.handle_command(command)

        elif opcode == OpCode.OP_TRIGGER:
            trigger = ArtTrigger()
            trigger.deserialize(data)

            log.debug(f"Received trigger from {addr[0]}\n"
                      f"  OEM    : {trigger.oem}\n"
                      f"  Key    : {trigger.key}\n"
                      f"  Subkey : {trigger.sub_key}")
            self.handle_trigger(trigger)

        elif opcode == OpCode.OP_OUTPUT_DMX:
            dmx = ArtDmx()
            dmx.deserialize(data)

            log.debug(f"Received DMX data from {addr[0]}\n"
                      f"  Address: {dmx.port_address}")
            self.handle_dmx(dmx)

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

        current_time = datetime.datetime.now()
        if not node:
            node = Node(source_ip, bind_index, current_time)
            self.add_node_by_ip(node, source_ip, bind_index)
            log.info(f"Discovered new node at {inet_ntoa(source_ip)}@{bind_index} with "
                     f"{reply.net_switch}:{reply.sub_switch}:[{','.join([str(p.sw_out) for p in reply.ports if p.output])}]"
                     )

            if self.__new_node_callback:
                self.__new_node_callback(reply)

        else:
            node.last_seen = current_time
            log.debug(f"Existing node checking in {inet_ntoa(source_ip)}@{bind_index} with "
                      f"{reply.net_switch}:{reply.sub_switch}:[{','.join([str(p.sw_out) for p in reply.ports])}]"
                      )

        old_addresses = node.get_addresses()
        node.net_switch = reply.net_switch
        node.sub_switch = reply.sub_switch
        node.ports = reply.ports

        new_addresses = node.get_addresses()
        log.debug(f"Addresses of the node at {inet_ntoa(source_ip)}@{bind_index}: {new_addresses}")
        addresses_to_remove = old_addresses - new_addresses

        for address_to_remove in addresses_to_remove:
            self.remove_node_by_port_address(address_to_remove, node)

        for new_address in new_addresses:
            self.add_node_by_port_address(new_address, node)

            if source_ip != self._own_ip:
                self.status_message = "Discovered some ArtNet nodes!"

                if self.indicator_state == IndicatorState.LOCATE_IDENTIFY:
                    self.indicator_state = IndicatorState.MUTE_MODE

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
            self.send_diagnostics(addr=addr[0], diagnostics_mode=DiagnosticsMode.UNICAST,
                                  diagnostics_priority=poll.diagnostics_priority)

    def handle_command(self, command: ArtCommand):
        if command.esta == 0xFFFF:
            commands = command.command.split("&")
            for c in commands:
                c = c.strip(' ')
                if c:
                    key, value = c.split('=')
                    key = key.lower()
                    if key == 'SwoutText'.lower():
                        self.swout_text = value
                        log.debug(f"Set Sw out text to: {value}")
                    elif key == 'SwinText'.lower():
                        self.swin_text = value
                        log.debug(f"Set Sw in text to: {value}")
        # TODO check if it would be cool to add HA specific commands?

    def handle_trigger(self, trigger):
        # TODO possible integrations here
        #  0: ASCII inputs into HA?
        #  1: Define and activate Macro's
        #  2: Key press inputs into HA?
        #  3: Scenes!
        pass

    def handle_dmx(self, dmx: ArtDmx):
        own_port = self.own_port_addresses.get(dmx.port_address)
        if not own_port:
            log.debug(f"Received ArtDmx for port address that we don't care about: {dmx.port_address}")
            return

        if own_port.port.good_input.data_received:
            own_port.port.good_input.data_received = True
            self.update_subscribers()

        own_port.port.last_input_seen = datetime.datetime.now()
        self.__hass.async_create_task(self.disable_input_flag(own_port))
        if self.__state_update_callback:
            self.__state_update_callback(dmx.port_address, dmx.data)

    async def disable_input_flag(self, own_port: OwnPort):
        await asyncio.sleep(4)

        cutoff_time = datetime.datetime.now() - datetime.timedelta(seconds=4)

        if own_port.port.last_input_seen < cutoff_time:
            own_port.port.good_input.data_received = False
            self.update_subscribers()

# server = ArtNetServer(firmware_version=1, short_name="Test python", long_name="Hello I am testing ArtNet server",
#                       polling=True)
# server.add_port(PortAddress(0, 0, 0))
# server.add_port(PortAddress(0, 0, 1))
#
# loopy = server.start_server()
#
# server.send_artnet(ArtCommand(command="SwoutText=Playback& SwinText=Record&"), "192.168.1.35")
# server.send_artnet(ArtTrigger(key=1, sub_key=ord('F')), "192.168.1.35")
#
# # loop.create_task(server.send_dmx(PortAddress(0, 0, 0), [0xFF] * 12))
#
# loopy.run_forever()
