import datetime
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

CLIENT_VERSION = 1

PROTOCOL_VERSION = 0x000E
PORT = 0x1936
HOME_ASSISTANT_ESTA = ord('H') << 8 + ord('A')

log = logging.getLogger(__name__)


class OpCode(Enum):
    # @formatter:off
    OP_POLL                 = 0x2000
    OP_POLL_REPLY           = 0x2100
    OP_DIAG_DATA            = 0x2300
    OP_COMMAND              = 0x2400
    OP_OUTPUT_DMX           = 0x5000
    OP_NZS                  = 0x5100
    OP_SYNC                 = 0x5200
    OP_ADDRESS              = 0x6000
    OP_INPUT                = 0x7000
    OP_TOD_REQUEST          = 0x8000
    OP_TOD_DATA             = 0x8100
    OP_TOD_CONTROL          = 0x8200
    OP_RDM                  = 0x8300
    OP_RDM_SUB              = 0x8400
    OP_VIDEO_SETUP          = 0xA010
    OP_VIDEO_PALETTE        = 0xA020
    OP_VIDEO_DATA           = 0xA040
    OP_MAC_MASTER           = 0xF000
    OP_MAC_SLAVE            = 0xF100
    OP_FIRMWARE_MASTER      = 0xF200
    OP_FIRMWARE_REPLY       = 0xF300
    OP_FILE_TN_MASTER       = 0xF400
    OP_FILE_FN_MASTER       = 0xF500
    OP_FILE_FN_REPLY        = 0xF600
    OP_IP_PROG              = 0xF800
    OP_IP_PROG_REPLY        = 0xF900
    OP_MEDIA                = 0x9000
    OP_MEDIA_PATCH          = 0x9100
    OP_MEDIA_CONTROL        = 0x9200
    OP_MEDIA_CONTROL_REPLY  = 0x9300
    OP_TIME_CODE            = 0x9700
    OP_TIME_SYNC            = 0x9800
    OP_TRIGGER              = 0x9900
    OP_DIRECTORY            = 0x9A00
    OP_DIRECTORY_REPLY      = 0x9B00
    # @formatter:on


class DiagnosticsMode(Enum):
    UNICAST = False
    BROADCAST = True


class DiagnosticsPriority(Enum):
    # @formatter:off
    DP_UNKNOWN  = 0x00
    DP_LOW      = 0x10
    DP_MED      = 0x40
    DP_HIGH     = 0x80
    DP_CRITICAL = 0xE0
    DP_VOLATILE = 0xF0
    # @formatter:on


class NodeReport(Enum):
    # @formatter:off
    RC_DEBUG            = 0x0000  # Booted in debug mode (Only used in development)
    RC_POWER_OK         = 0x0001  # Power On Tests successful
    RC_POWER_FAIL       = 0x0002  # Hardware tests failed at Power On
    RC_SOCKET_WR1       = 0x0003  # Last UDP from Node failed due to truncated length, Most likely caused by a collision.
    RC_PARSE_FAIL       = 0x0004  # Unable to identify last UDP transmission. Check OpCode and packet length.
    RC_UDP_FAIL         = 0x0005  # Unable to open Udp Socket in last transmission attempt
    RC_SH_NAME_OK       = 0x0006  # Confirms that Short Name programming via ArtAddress, was successful.
    RC_LO_NAME_OK       = 0x0007  # Confirms that Long Name programming via ArtAddress, was successful.
    RC_DMX_ERROR        = 0x0008  # DMX512 receive errors detected.
    RC_DMX_UDP_FULL     = 0x0009  # Ran out of internal DMX transmit buffers.
    RC_DMX_RX_FULL      = 0x000A  # Ran out of internal DMX Rx buffers.
    RC_SWITCH_ERR       = 0x000B  # Rx Universe switches conflict.
    RC_CONFIG_ERR       = 0x000C  # Product configuration does not match firmware.
    RC_DMX_SHORT        = 0x000D  # DMX output short detected. See GoodOutput field.
    RC_FIRMWARE_FAIL    = 0x000E  # Last attempt to upload new firmware failed.
    RC_USER_FAIL        = 0x000F  # User changed switch settings when address locked by remote programming. User changes ignored.
    RC_FACTORY_RES      = 0x0010  # Factory reset has occurred.
    # @formatter:on

    def report(self, reply_count: int, status_message: str):
        # The spec is very unclear regarding the 'ArtPollResponse' count, this is my best-guess.
        return f"#{hex(self.value)[2:]} [{str(reply_count).zfill(4)}] {status_message}"


class StyleCode(Enum):
    # @formatter:off
    ST_NODE         = (0x00, "A DMX to / from Art-Net device")
    ST_CONTROLLER   = (0x01, "A lighting console.")
    ST_MEDIA        = (0x02, "A Media Server.")
    ST_ROUTE        = (0x03, "A network routing device.")
    ST_BACKUP       = (0x04, "A backup device.")
    ST_CONFIG       = (0x05, "A configuration or diagnostic tool.")
    ST_VISUAL       = (0x06, "A visualiser.")
    # @formatter:on


@dataclass(order=True)
class PortAddress:
    net: int = 0
    sub_net: int = 0
    universe: int = 0

    def __init__(self, net: int, sub_net: int, universe: int = 0) -> None:
        super().__init__()
        assert (0 <= net <= 0xF)
        assert (0 <= sub_net <= 0xF)
        assert (0 <= universe <= 0x1FF)
        self.net = net
        self.sub_net = sub_net
        self.universe = universe

    @property
    def port_address(self):
        return (self.net << 13) | (self.sub_net << 9) | self.universe

    @port_address.setter
    def port_address(self, port_address):
        self.net = port_address >> 13 & 0xF
        self.sub_net = port_address >> 9 & 0xF
        self.universe = port_address & 0x1FF

    @staticmethod
    def parse(port_address: int):
        return PortAddress(port_address >> 13 & 0xF, port_address >> 9 & 0xF, port_address & 0x1FF)

    def __str__(self):
        return f"{self.net}:{self.sub_net}:{self.universe}"

    def __hash__(self):
        return self.port_address



class IndicatorState(Enum):
    # @formatter:off
    UNKNOWN         = 0
    LOCATE_IDENTIFY = 1
    MUTE_MODE       = 2
    NORMAL_MODE     = 3
    # @formatter:on


class PortAddressProgrammingAuthority(Enum):
    # @formatter:off
    UNKNOWN         = 0
    FRONT_PANEL     = 1
    PROGRAMMATIC    = 2
    # @formatter:on


class BootProcess(Enum):
    FLASH = False
    ROM = True


class PortType(Enum):
    DMX512 = 0
    MIDI = 1
    AVAB = 2
    COLORTRAN_CMX = 3
    ADB_65_2 = 4
    ART_NET = 5
    DALI = 6


@dataclass
class GoodInput:
    data_received: bool = False
    includes_dmx512_test_packets: bool = False
    includes_dmx512_sips: bool = False
    includes_dmx512_text_packets: bool = False
    input_disabled: bool = False
    receive_errors_detected: bool = False

    @property
    def flags(self):
        return (self.data_received << 7) \
            + (self.includes_dmx512_test_packets << 6) \
            + (self.includes_dmx512_sips << 5) \
            + (self.includes_dmx512_text_packets << 4) \
            + (self.input_disabled << 3) \
            + (self.receive_errors_detected << 2)

    @flags.setter
    def flags(self, flags):
        self.data_received = bool(flags >> 7 & 1)
        self.includes_dmx512_test_packets = bool(flags >> 6 & 1)
        self.includes_dmx512_sips = bool(flags >> 5 & 1)
        self.includes_dmx512_text_packets = bool(flags >> 4 & 1)
        self.input_disabled = bool(flags >> 3 & 1)
        self.receive_errors_detected = bool(flags >> 2 & 1)


@dataclass
class GoodOutputA:
    data_being_transmitted: bool = False
    includes_dmx512_test_packets: bool = False
    includes_dmx512_sips: bool = False
    includes_dmx512_text_packets: bool = False
    merging_enabled: bool = False
    short_detected: bool = False
    merge_is_ltp: bool = False
    use_sacn: bool = False

    @property
    def flags(self):
        return (self.data_being_transmitted << 7) \
            + (self.includes_dmx512_test_packets << 6) \
            + (self.includes_dmx512_sips << 5) \
            + (self.includes_dmx512_text_packets << 4) \
            + (self.merging_enabled << 3) \
            + (self.short_detected << 2) \
            + (self.merge_is_ltp << 1) \
            + self.use_sacn

    @flags.setter
    def flags(self, flags):
        self.data_being_transmitted = bool(flags >> 7 & 1)
        self.includes_dmx512_test_packets = bool(flags >> 6 & 1)
        self.includes_dmx512_sips = bool(flags >> 5 & 1)
        self.includes_dmx512_text_packets = bool(flags >> 4 & 1)
        self.merging_enabled = bool(flags >> 3 & 1)
        self.short_detected = bool(flags >> 2 & 1)
        self.merge_is_ltp = bool(flags >> 1 & 1)
        self.use_sacn = bool(flags & 1)


@dataclass
class Port:
    input: bool = False
    output: bool = False
    type: PortType = PortType.DMX512
    good_input: GoodInput = field(default_factory=GoodInput)
    good_output_a: GoodOutputA = field(default_factory=GoodOutputA)
    sw_in: int = 0
    sw_out: int = 0
    rdm_enabled: bool = False
    output_continuous: bool = True

    last_input_seen: datetime = datetime.datetime.now()

    @property
    def port_types_flags(self) -> int:
        return (self.output << 7) \
            + (self.input << 6) \
            + self.type.value

    @port_types_flags.setter
    def port_types_flags(self, flags):
        self.output = bool(flags >> 7 & 1)
        self.input = bool(flags >> 6 & 1)
        self.type = PortType(flags & 0b11_1111)

    @property
    def good_output_b(self) -> int:
        return (self.rdm_enabled << 7) \
            + (self.output_continuous << 6)

    @good_output_b.setter
    def good_output_b(self, flags):
        self.rdm_enabled = bool(flags >> 7 & 1)
        self.output_continuous = bool(flags >> 6 & 1)


class FailsafeState(Enum):
    HOLD_LAST_STATE = 0
    ALL_OUTPUTS_0 = 1
    ALL_OUTPUTS_FULL = 2
    PLAYBACK_FAIL_SAFE_SCENE = 3


@dataclass
class ArtIpProgCommand:
    enable_programming: bool = False
    enable_dhcp: bool = False
    program_default_gateway: bool = False
    set_parameters_to_default: bool = False
    program_ip_address: bool = False
    program_subnet_mask: bool = False
    program_port: bool = False

    @property
    def flags(self):
        return (self.enable_programming << 7) \
            + (self.enable_dhcp << 6) \
            + (self.program_default_gateway << 4) \
            + (self.set_parameters_to_default << 3) \
            + (self.program_ip_address << 2) \
            + (self.program_subnet_mask << 1) \
            + self.program_port

    @flags.setter
    def flags(self, flags):
        self.enable_programming = bool(flags >> 7 & 1)
        self.enable_dhcp = bool(flags >> 6 & 1)
        self.program_default_gateway = bool(flags >> 4 & 1)
        self.set_parameters_to_default = bool(flags >> 3 & 1)
        self.program_ip_address = bool(flags >> 2 & 1)
        self.program_subnet_mask = bool(flags >> 1 & 1)
        self.program_port = bool(flags & 1)


class ArtAddressCommand(Enum):
    # @formatter:off
    AC_NONE             = 0x00  # No action
    AC_CANCEL_MERGE     = 0x01  # If Node is currently in merge mode, cancel merge mode upon receipt of next ArtDmx packet. See discussion of merge mode operation.
    AC_LED_NORMAL       = 0x02  # The front panel indicators of the Node operate normally.
    AC_LED_MUTE         = 0x03  # The front panel indicators of the Node are disabled and switched off.
    AC_LED_LOCATE       = 0x04  # Rapid flashing of the Node’s front panel indicators. It is intended as an outlet identifier for large installations.
    AC_RESET_RX_FLAGS   = 0x05  # Resets the Node’s Sip, Text, Test and data error flags. If an output short is being flagged, forces the test to re-run.
    AC_ANALYSIS_ON      = 0x06  # Enable analysis and debugging mode.
    AC_ANALYSIS_OFF     = 0x07  # Disable analysis and debugging mode.

    # Failsafe configuration commands: These settings should be retained by the node during power cycling.
    AC_FAIL_HOLD        = 0x08  # Set the node to hold last state in the event of loss of network data.
    AC_FAIL_ZERO        = 0x09  # Set the node’s outputs to zero in the event of loss of network data.
    AC_FAIL_FULL        = 0x0A  # Set the node’s outputs to full in the event of loss of network data.
    AC_FAIL_SCENE       = 0x0B  # Set the node’s outputs to play the failsafescene in the event of loss of network data.
    AC_FAIL_RECORD      = 0x0C  # Record the current output state as the failsafescene.

    # Node configuration commands: Note that Ltp / Htp settings should be retained by the node during power cycling.
    # Implementation node: Using the same enum for all 4 ports, use the lower 4 bits to determine port number
    AC_MERGE_LTP        = 0x10  # Set DMX Port # to Merge in LTP mode.
    AC_DIRECTION_TX     = 0x20  # Set Port# direction to Output.
    AC_DIRECTION_RX     = 0x30  # Set Port# direction to Input.
    AC_MERGE_HTP        = 0x50  # Set DMX Port # to Merge in HTP (default) mode.
    AC_ART_NET_SEL      = 0x60  # Set DMX Port # to output both DMX512 and RDM packets from the Art-Net protocol (default).
    AC_ACN_SEL          = 0x70  # Set DMX Port # to output DMX512 data from the sACN protocol and RDM data from the Art-Net protocol
    AC_CLEAR_OP         = 0x90  # Clear DMX Output buffer for Port #
    AC_STYLE_DELTA      = 0xA0  # Set output style to delta mode (DMX frame triggered by ArtDmx) for Port #
    AC_STYLE_CONST      = 0xB0  # Set output style to constant mode (DMX output is continuous) for Port #
    AC_RDM_ENABLE       = 0xC0  # Enable RDM for Port #
    AC_RDM_DISABLE      = 0XD0  # Disable RDM for Port #
    # @formatter:on

    def apply_port_index(self, port_index: int) -> int:
        assert 0 <= port_index <= 3
        return self.value if self.value >= 0x10 else self.value + port_index

    @staticmethod
    def decode_with_port_index(value: int) -> (Enum, int):
        if value >= 0x10:
            port_index = value & 0x0F
            value -= port_index
        else:
            port_index = 0
        return ArtAddressCommand(value), port_index


class ValueAction(Enum):
    RESET = 0
    IGNORE = 1
    WRITE = 2


class TimeCodeType(Enum):
    FILM = 0
    EBU = 1
    DF = 2
    SMPTE = 3


class ArtBase:
    __ENCODINGS__ = ['iso-8859-1', 'utf8']

    def __init__(self, opcode: OpCode) -> None:
        super().__init__()
        self.__opcode = opcode

    def serialize(self) -> bytearray:
        packet = bytearray()
        packet.extend(map(ord, "Art-Net\0"))
        self._append_int_lsb(packet, self.__opcode.value)
        return packet

    def deserialize(self, packet: bytearray) -> int:
        packet_header, index = self._consume_str(packet, 0, 8)
        if packet_header != "Art-Net":
            raise SerializationException(f"Not a valid packet, expected \"Art-Net\", but is \"{packet_header}\"")

        opcode, index = self._consume_int_lsb(packet, index)
        if opcode != self.__opcode.value:
            raise SerializationException(f"Expected this packet to have opcode {self.__opcode}, but was {opcode}")

        return index

    @staticmethod
    def _pop(packet: bytearray, index: int) -> (int, int):
        return packet[index], index + 1

    @staticmethod
    def _take(packet: bytearray, n: int, index: int) -> (int, int):
        return packet[index:index + n], index + n

    @staticmethod
    def _append_int_lsb(packet: bytearray, number: int):
        packet.append(number & 0xFF)
        packet.append(number >> 8 & 0xFF)

    @staticmethod
    def _append_int_msb(packet: bytearray, number: int):
        packet.append(number >> 8 & 0xFF)
        packet.append(number & 0xFF)

    @staticmethod
    def _consume_int_lsb(packet: bytearray, index: int) -> (int, int):
        if len(packet) < (index + 2):
            raise SerializationException(f"Not enough bytes in packet: {bytes(packet).hex()}")
        [lsb, msb] = packet[index:index + 2]
        return (msb << 8) | lsb, index + 2

    @staticmethod
    def _consume_int_msb(packet: bytearray, index: int) -> (int, int):
        if len(packet) < (index + 2):
            raise SerializationException(f"Not enough bytes in packet: {bytes(packet).hex()}")
        [msb, lsb] = packet[index:index + 2]
        return (msb << 8) | lsb, index + 2

    @staticmethod
    def _consume_hex_number_lsb(packet: bytearray, index: int) -> (int, int):
        if len(packet) < (index + 2):
            raise SerializationException(f"Not enough bytes in packet: {bytes(packet).hex()}")
        lower = hex(packet[index])[2:].zfill(2)
        upper = hex(packet[index + 1])[2:].zfill(2)
        return int(upper + lower, 16), index + 2

    @staticmethod
    def _consume_hex_number_msb(packet: bytearray, index: int) -> (int, int):
        if len(packet) < (index + 2):
            raise SerializationException(f"Not enough bytes in packet: {bytes(packet).hex()}")
        upper = hex(packet[index])[2:].zfill(2)
        lower = hex(packet[index + 1])[2:].zfill(2)
        return int(upper + lower, 16), index + 2

    @staticmethod
    def _append_str(packet: bytearray, text: str, length: int):
        cut_text: str = text[:length - 1]
        padded_text = cut_text.ljust(length, '\0')
        packet.extend(map(ord, padded_text))

    @staticmethod
    def _consume_str(packet: bytearray, index: int, length: int) -> (Optional[str], int):
        decoded_str: Optional[str] = None
        raw_string_from_packet = packet[index:index + length]

        # assume the data is ascii
        try:
            # if there is a NUL character in the bytearry, it terminates earlier
            nul_terminator = re.compile(b"([^\\x00]+)")

            terminated_string = nul_terminator.match(raw_string_from_packet).group(1)  \
                if nul_terminator.match(raw_string_from_packet) else raw_string_from_packet

            # remove every other control character
            sanitized_str = re.sub(b"[^\x00-\x7F]",b"", terminated_string)

            # decode
            decoded_str = sanitized_str.decode('ascii')
            log.info(f"decoded string: {decoded_str}")

        except UnicodeDecodeError:
            # data not ascii, try to use the decoding shotgun
            decoded_str = ArtBase._decode_bytes(raw_string_from_packet)

        # check if decoding has failed
        if decoded_str is None:
            log.error("Unable to convert bytes to string: {raw_hex}".format(raw_hex=bytes(raw_string_from_packet).hex()))

        return decoded_str, index + length

    @staticmethod
    def _decode_bytes(byte_str: bytearray) -> Optional[str]:
        for encoding in ArtBase.__ENCODINGS__:
            try:
                decoded_str = byte_str.decode(encoding)
                sanitized_str = str(decoded_str).strip().strip('\x00')
                log.debug(f"decoded as {encoding}: {sanitized_str}")
                return sanitized_str
            except UnicodeDecodeError as e:
                log.warning(f"failed ({e.reason} to decode as {encoding}: {bytes(byte_str).hex()}")

    @staticmethod
    def peek_opcode(packet: bytearray) -> OpCode | None:
        if len(packet) < 9:
            return None

        header = packet[0:8]
        if header != b'Art-Net\x00':
            return None

        opcode = ArtBase._consume_int_lsb(packet, 8)
        return OpCode(opcode[0])


class ArtPoll(ArtBase):

    def __init__(self,
                 protocol_version=PROTOCOL_VERSION,
                 enable_vlc_transmission: bool = False,
                 notify_on_change: bool = False,
                 ) -> None:
        super().__init__(OpCode.OP_POLL)
        self.__protocol_version = protocol_version
        self.__enable_vlc_transmission = enable_vlc_transmission
        self.notify_on_change = notify_on_change

        self.__enable_diagnostics = False
        self.__diag_priority = DiagnosticsPriority.DP_LOW
        self.__diag_mode = DiagnosticsMode.BROADCAST

        self.__enable_targeted_mode = False
        self.__target_port_bottom: PortAddress = PortAddress(0x0, 0x0, 0x0)
        self.__target_port_top: PortAddress = PortAddress(0xF, 0xF, 0x199)

    def enable_diagnostics(self,
                           mode: DiagnosticsMode = DiagnosticsMode.BROADCAST,
                           diag_priority: DiagnosticsPriority = DiagnosticsPriority.DP_LOW
                           ):
        self.__enable_diagnostics = True
        self.__diag_priority = diag_priority
        self.__diag_mode = mode

    @property
    def protocol_verison(self):
        return self.__protocol_version

    @property
    def vlc_transmission_enabled(self):
        return self.__enable_vlc_transmission

    @property
    def is_diagnostics_enabled(self):
        return self.__enable_diagnostics

    @property
    def diagnostics_priority(self):
        return self.__diag_priority

    @property
    def diagnostics_mode(self):
        return self.__diag_mode

    @property
    def targeted_mode_enabled(self):
        return self.__enable_targeted_mode

    @property
    def target_port_bounds(self) -> (PortAddress, PortAddress):
        return self.__target_port_bottom, self.__target_port_top

    @target_port_bounds.setter
    def target_port_bounds(self, bounds: (PortAddress, PortAddress)):
        self.__target_port_bottom = bounds[0]
        self.__target_port_top = bounds[0]
        self.__enable_targeted_mode = True

    def serialize(self) -> bytearray:
        packet = super().serialize()
        self._append_int_msb(packet, self.__protocol_version)

        flags = (self.__enable_targeted_mode << 5) \
                + (self.__enable_vlc_transmission << 4) \
                + (self.__diag_mode.value << 3) \
                + (self.__enable_diagnostics << 2) \
                + (self.notify_on_change << 1)

        packet.append(flags)
        packet.append(self.__diag_priority.value)
        self._append_int_msb(packet, self.__target_port_top.port_address)
        self._append_int_msb(packet, self.__target_port_bottom.port_address)
        return packet

    def deserialize(self, packet: bytearray) -> int:
        index = 0
        try:
            index = super().deserialize(packet)
            self.__protocol_version, index = self._consume_int_msb(packet, index)

            flags, index = self._pop(packet, index)
            self.__enable_targeted_mode = bool(flags >> 5 & 1)
            self.__enable_vlc_transmission = bool(flags >> 4 & 1)
            self.__diag_mode = DiagnosticsMode(bool(flags >> 3 & 1))
            self.__enable_diagnostics = bool(flags >> 2 & 1)
            self.notify_on_change = bool(flags >> 1 & 1)

            self.__diag_priority = DiagnosticsPriority(packet[index])
            index += 1
            self.__target_port_top.port_address, index = self._consume_int_msb(packet, index)
            self.__target_port_bottom.port_address, index = self._consume_int_msb(packet, index)
        except SerializationException as e:
            print(e)

        return index


class ArtPollReply(ArtBase):
    def __init__(self,
                 source_ip: bytes = bytes([0x00] * 4),
                 firmware_version: int = 0,
                 net_switch: int = 0,
                 sub_switch: int = 0,
                 oem: int = 0,
                 indicator_state: IndicatorState = IndicatorState.UNKNOWN,
                 port_address_programming_authority: PortAddressProgrammingAuthority = PortAddressProgrammingAuthority.UNKNOWN,
                 boot_process: BootProcess = BootProcess.ROM,
                 supports_rdm: bool = False,
                 esta: int = HOME_ASSISTANT_ESTA,
                 short_name: str = "PyArtNet",
                 long_name: str = "Default long name",
                 node_report: str = "",
                 ports: list[Port] = [],
                 acn_priority: int = 100,
                 sw_macro_bitmap: int = 0,
                 sw_remote_bitmap: int = 0,
                 style: StyleCode = StyleCode.ST_CONTROLLER,
                 mac_address: bytes = bytes([0] * 6),
                 bind_ip: bytes = bytes([0] * 4),
                 bind_index: int = 1,
                 supports_web_browser_configuration: bool = False,
                 dhcp_configured: bool = False,
                 dhcp_capable: bool = False,
                 supports_15_bit_port_address: bool = True,
                 supports_switching_to_sacn: bool = False,
                 squawking: bool = False,
                 supports_switching_of_output_style: bool = False,
                 supports_rdm_through_artnet: bool = False,
                 failsafe_state: FailsafeState = FailsafeState.HOLD_LAST_STATE,
                 supports_failover: bool = False,
                 supports_switching_port_direction: bool = False
                 ) -> None:
        super().__init__(opcode=OpCode.OP_POLL_REPLY)

        assert source_ip.__len__() == 4
        self.source_ip = source_ip
        self.port = PORT
        self.firmware_version = firmware_version
        self.net_switch = net_switch
        self.sub_switch = sub_switch
        self.oem = oem
        self.indicator_state = indicator_state
        self.port_address_programming_authority = port_address_programming_authority
        self.boot_process = boot_process
        self.supports_rdm = supports_rdm
        self.esta = esta

        assert len(short_name) < 18
        self.short_name = short_name

        assert len(long_name) < 64
        self.long_name = long_name

        self.node_report = node_report

        assert len(ports) <= 4
        self.ports = ports
        for i in range(4 - len(ports)):
            self.ports.append(Port())

        self.acn_priority = acn_priority

        self.sw_macro_bitmap = sw_macro_bitmap
        self.sw_remote_bitmap = sw_remote_bitmap
        self.style = style

        assert len(mac_address) == 6
        self.mac_address = mac_address

        assert len(bind_ip) == 4
        self.bind_ip = bind_ip

        self.bind_index = bind_index

        self.supports_web_browser_configuration = supports_web_browser_configuration
        self.dhcp_configured = dhcp_configured
        self.dhcp_capable = dhcp_capable
        self.supports_15_bit_port_address = supports_15_bit_port_address
        self.supports_switching_to_sacn = supports_switching_to_sacn
        self.squawking = squawking
        self.supports_switching_of_output_style = supports_switching_of_output_style
        self.supports_rdm_through_artnet = supports_rdm_through_artnet

        self.failsafe_state = failsafe_state
        self.supports_failover = supports_failover
        self.supports_switching_port_direction = supports_switching_port_direction

        self.__ubea_present = False
        self.__ubea = 0

        self.__supports_llrp = True
        self.__default_resp_uid = [0x0] * 6

    @property
    def ubea(self) -> int | None:
        return self.__ubea if self.__ubea_present else None

    @ubea.setter
    def ubea(self, ubea: int):
        self.__ubea_present = True
        self.__ubea = ubea

    @property
    def default_resp_uid(self):
        return self.__default_resp_uid if self.__supports_llrp else None

    @default_resp_uid.setter
    def default_resp_uid(self, default_resp_uid: bytearray):
        assert len(default_resp_uid) == 6
        self.__supports_llrp = True
        self.__default_resp_uid = default_resp_uid

    def serialize(self) -> bytearray:
        packet = super().serialize()
        packet.extend(self.source_ip)

        port_str = hex(self.port)[2:]
        packet.extend([int(port_str[2:4], 16), int(port_str[0:2], 16)])

        self._append_int_msb(packet, self.firmware_version)
        packet.append(self.net_switch)
        packet.append(self.sub_switch)
        self._append_int_msb(packet, self.oem)
        packet.append(self.ubea or 0x00)

        status1 = (self.indicator_state.value << 6) \
                  + (self.port_address_programming_authority.value << 4) \
                  + (self.boot_process.value << 2) \
                  + (self.supports_rdm < 1) \
                  + self.__ubea_present
        packet.append(status1)

        self._append_int_lsb(packet, self.esta)
        self._append_str(packet, self.short_name, 18)
        self._append_str(packet, self.long_name, 64)
        self._append_str(packet, self.node_report, 64)

        self._append_int_msb(packet, len([p for p in self.ports if p.input or p.output]))
        packet.extend([p.port_types_flags for p in self.ports])
        packet.extend([p.good_input.flags for p in self.ports])
        packet.extend([p.good_output_a.flags for p in self.ports])
        packet.extend([p.sw_in for p in self.ports])
        packet.extend([p.sw_out for p in self.ports])
        packet.append(self.acn_priority)
        packet.append(self.sw_macro_bitmap)
        packet.append(self.sw_remote_bitmap)
        packet.extend([0, 0, 0])
        packet.append(self.style.value[0])
        packet.extend(self.mac_address)
        packet.extend(self.bind_ip)
        packet.append(self.bind_index)

        status2 = self.supports_web_browser_configuration \
                  + (self.dhcp_configured << 1) \
                  + (self.dhcp_capable << 2) \
                  + (self.supports_15_bit_port_address << 3) \
                  + (self.supports_switching_to_sacn << 4) \
                  + (self.squawking << 5) \
                  + (self.supports_switching_of_output_style << 6) \
                  + (self.supports_rdm_through_artnet << 7)
        packet.append(status2)

        packet.extend(map(lambda p: p.good_output_b, self.ports))

        status3 = (self.failsafe_state.value << 6) \
                  + (self.supports_failover << 5) \
                  + (self.__supports_llrp << 4) \
                  + (self.supports_switching_port_direction < 3)
        packet.append(status3)
        packet.extend(self.default_resp_uid)

        packet.extend([0x0] * 15)

        return packet

    def deserialize(self, packet: bytearray) -> int:
        index = 0
        try:
            index = super().deserialize(packet)

            self.source_ip, index = self._take(packet, 4, index)

            self.port, index = self._consume_hex_number_lsb(packet, index)
            self.firmware_version, index = self._consume_hex_number_msb(packet, index)

            self.net_switch, index = self._pop(packet, index)
            self.sub_switch, index = self._pop(packet, index)
            self.oem, index = self._consume_hex_number_msb(packet, index)
            self.ubea, index = self._pop(packet, index)

            status1, index = self._pop(packet, index)
            self.indicator_state = IndicatorState(status1 >> 6 & 2)
            self.port_address_programming_authority = PortAddressProgrammingAuthority(status1 >> 4 & 2)
            self.boot_process = BootProcess(bool(status1 >> 2 & 1))
            self.supports_rdm = bool(status1 >> 1 & 1)
            self.__ubea_present = bool(status1 & 1)

            self.esta, index = self._consume_hex_number_lsb(packet, index)
            self.short_name, index = self._consume_str(packet, index, 18)
            self.long_name, index = self._consume_str(packet, index, 64)
            self.node_report, index = self._consume_str(packet, index, 64)

            port_count, index = self._consume_int_msb(packet, index)
            port_type_flags, index = self._take(packet, 4, index)
            good_input_flags, index = self._take(packet, 4, index)
            good_output_a_flags, index = self._take(packet, 4, index)
            sw_ins, index = self._take(packet, 4, index)
            sw_outs, index = self._take(packet, 4, index)

            self.acn_priority, index = self._pop(packet, index)  # Used to be SwVideo
            self.sw_macro_bitmap, index = self._pop(packet, index)
            self.sw_remote_bitmap, index = self._pop(packet, index)

            index += 3

            self.style, index = self._pop(packet, index)
            self.mac_address, index = self._take(packet, 6, index)
            self.bind_ip, index = self._take(packet, 4, index)
            self.bind_index, index = self._pop(packet, index)

            status2, index = self._pop(packet, index)
            self.supports_web_browser_configuration = bool(status2 & 1)
            self.dhcp_configured = bool(status2 >> 1 & 1)
            self.dhcp_capable = bool(status2 >> 2 & 1)
            self.supports_15_bit_port_address = bool(status2 >> 3 & 1)
            self.supports_switching_to_sacn = bool(status2 >> 4 & 1)
            self.squawking = bool(status2 >> 5 & 1)
            self.supports_switching_of_output_style = bool(status2 >> 6 & 1)
            self.supports_rdm_through_artnet = bool(status2 >> 7 & 1)

            good_output_b_flags, index = self._take(packet, 4, index)

            for i in range(port_count):
                port = self.ports[i]
                port.port_types_flags = port_type_flags[i]
                port.good_input.flags = good_input_flags[i]
                port.good_output_a.flags = good_output_a_flags[i]
                port.sw_in = sw_ins[i]
                port.sw_out = sw_outs[i]
                port.good_output_b = good_output_b_flags[i]

            status3, index = self._pop(packet, index)
            self.failsafe_state = FailsafeState(status3 >> 6)
            self.supports_failover = bool(status3 >> 5 & 1)
            self.__supports_llrp = bool(status3 >> 4 & 1)
            self.supports_switching_port_direction = bool(status3 >> 3 & 1)

            self.default_resp_uid, index = self._take(packet, 6, index)

            index += 15
        except SerializationException as e:
            print(e)
        return index


class ArtIpProg(ArtBase):

    def __init__(self,
                 protocol_version: int = PROTOCOL_VERSION,
                 command: ArtIpProgCommand = ArtIpProgCommand(),
                 prog_ip: bytes = bytes([0x00] * 4),
                 prog_subnet: bytes = bytes([0x00] * 4),
                 prog_gateway: bytes = bytes([0x00] * 4)
                 ) -> None:
        super().__init__(OpCode.OP_IP_PROG)

        assert prog_ip.__len__() == 4
        assert prog_subnet.__len__() == 4
        assert prog_gateway.__len__() == 4

        self.protocol_version = protocol_version
        self.command = command
        self.prog_ip = prog_ip
        self.prog_subnet = prog_subnet
        self.prog_gateway = prog_gateway

    def serialize(self) -> bytearray:
        packet = super().serialize()
        self._append_int_msb(packet, self.protocol_version)
        packet.extend([0x00] * 2)
        packet.append(self.command.flags)
        packet.append(0x00)
        packet.extend(self.prog_ip)
        packet.extend(self.prog_subnet)
        packet.extend([0x00] * 2)
        packet.extend(self.prog_gateway)
        packet.extend([0x00] * 4)
        return packet

    def deserialize(self, packet: bytearray) -> int:
        index = 0
        try:
            index = super().deserialize(packet)
            self.protocol_version, index = self._consume_int_msb(packet, index)
            if self.protocol_version != 14:
                raise SerializationException("Protocol is not 14!")

            index += 2
            self.command.flags, index = self._pop(packet, index)
            index += 1
            self.prog_ip, index = self._take(packet, 4, index)
            self.prog_subnet, index = self._take(packet, 4, index)
            index += 2
            self.prog_gateway, index = self._take(packet, 4, index)

            index += 4
        except SerializationException as e:
            print(e)

        return index


class ArtIpProgReply(ArtBase):

    def __init__(self,
                 protocol_version: int = PROTOCOL_VERSION,
                 prog_ip: bytes = bytes([0x00] * 4),
                 prog_subnet: bytes = bytes([0x00] * 4),
                 prog_gateway: bytes = bytes([0x00] * 4),
                 dhcp_enabled: bool = False
                 ) -> None:
        super().__init__(OpCode.OP_IP_PROG_REPLY)

        assert prog_ip.__len__() == 4
        assert prog_subnet.__len__() == 4
        assert prog_gateway.__len__() == 4

        self.protocol_version = protocol_version
        self.prog_ip = prog_ip
        self.prog_subnet = prog_subnet
        self.prog_gateway = prog_gateway
        self.dhcp_enabled = dhcp_enabled

    def serialize(self) -> bytearray:
        packet = super().serialize()
        self._append_int_msb(packet, self.protocol_version)
        packet.extend([0x00] * 4)
        packet.extend(self.prog_ip)
        packet.extend(self.prog_subnet)
        packet.extend([0x00] * 2)
        packet.append(self.dhcp_enabled << 6)
        packet.append(0x00)
        packet.extend(self.prog_gateway)
        packet.extend([0x00] * 2)
        return packet

    def deserialize(self, packet: bytearray) -> int:
        index = 0
        try:
            index = super().deserialize(packet)
            self.protocol_version, index = self._consume_int_msb(packet, index)
            if self.protocol_version != 14:
                raise SerializationException("Protocol is not 14!")

            index += 4
            self.prog_ip, index = self._take(packet, 4, index)
            self.prog_subnet, index = self._take(packet, 4, index)
            index += 2

            status, index = self._pop(packet, index)
            self.dhcp_enabled = bool(status >> 6 & 1)

            index += 1
            self.prog_gateway, index = self._take(packet, 4, index)

            index += 2
        except SerializationException as e:
            print(e)

        return index


class ArtAddress(ArtBase):
    def __init__(self,
                 protocol_version: int = PROTOCOL_VERSION,
                 net_switch: int = 1,
                 net_action: ValueAction = ValueAction.IGNORE,
                 sub_switch: int = 1,
                 sub_action: ValueAction = ValueAction.IGNORE,
                 bind_index: int = 1,
                 short_name: str = "",
                 long_name: str = "",
                 sw_in: list[int] = [1] * 4,
                 sw_in_actions: list[ValueAction] = [ValueAction.IGNORE] * 4,
                 sw_out: list[int] = [1] * 4,
                 sw_out_actions: list[ValueAction] = [ValueAction.IGNORE] * 4,
                 acn_priority: int = 255,  # 255 means no change
                 command: ArtAddressCommand = ArtAddressCommand.AC_NONE,
                 command_port_index: int = 0
                 ) -> None:
        super().__init__(opcode=OpCode.OP_ADDRESS)

        self.protocol_version = protocol_version
        self.net_switch = net_switch
        self.net_action = net_action
        self.sub_switch = sub_switch
        self.sub_action = sub_action
        self.bind_index = bind_index

        assert len(short_name) < 18
        self.short_name = short_name

        assert len(long_name) < 64
        self.long_name = long_name

        assert len(sw_in) <= 4
        self.sw_in = sw_in + [1] * (4 - len(sw_in))

        assert len(sw_in_actions) <= 4
        self.sw_in_actions = sw_in_actions + [ValueAction.IGNORE] * (4 - len(sw_in_actions))

        assert len(sw_out) <= 4
        self.sw_out = sw_out + [1] * (4 - len(sw_out))

        assert len(sw_out_actions) <= 4
        self.sw_out_actions = sw_out_actions + [ValueAction.IGNORE] * (4 - len(sw_out_actions))

        assert (0 <= acn_priority <= 200) or acn_priority == 255
        self.acn_priority = acn_priority

        self.command = command
        self.command_port_index = command_port_index

    def serialize(self) -> bytearray:
        packet = super().serialize()
        self._append_int_msb(packet, self.protocol_version)
        packet.append(ArtAddress.__apply_value_action(self.net_action, self.net_switch))
        packet.append(self.bind_index)
        self._append_str(packet, self.short_name, 18)
        self._append_str(packet, self.long_name, 64)
        self.__append_sw_in_out(packet, self.sw_in, self.sw_in_actions)
        self.__append_sw_in_out(packet, self.sw_out, self.sw_out_actions)
        packet.append(ArtAddress.__apply_value_action(self.sub_action, self.sub_switch))
        packet.append(self.acn_priority)
        packet.append(self.command.apply_port_index(self.command_port_index))
        return packet

    def deserialize(self, packet: bytearray) -> int:
        index = 0
        try:
            index = super().deserialize(packet)
            self.protocol_version, index = self._consume_int_msb(packet, index)
            if self.protocol_version != 14:
                raise SerializationException("Protocol is not 14!")

            self.net_switch, self.net_action, index = self.__consume_value_and_action(packet, index)
            self.bind_index, index, self._pop(packet, index)
            self.short_name = self._consume_str(packet, index, 18)
            self.long_name = self._consume_str(packet, index, 64)
            self.sw_in, self.sw_in_actions, index = self.__consume_sw_in_out(packet, index)
            self.sw_out, self.sw_out_actions, index = self.__consume_sw_in_out(packet, index)
            self.sub_switch, self.sub_action, index = self.__consume_value_and_action(packet, index)
            self.acn_priority, index = self._pop(packet, index)

            command_byte, index = self._pop(packet, index)
            self.command, self.command_port_index = ArtAddressCommand.decode_with_port_index(command_byte)
        except SerializationException as e:
            print(e)

        return index

    @staticmethod
    def __apply_value_action(action: ValueAction, value: int) -> int:
        if action == ValueAction.RESET:
            return 0x00
        else:
            return (action == ValueAction.WRITE) << 7 | value

    @staticmethod
    def __consume_value_and_action(packet: bytearray, index: int) -> (int, ValueAction, int):
        value = packet[index]
        if value == 0x00:
            action = ValueAction.RESET
        elif value >> 7 & 1:
            action = ValueAction.WRITE
        else:
            action = ValueAction.IGNORE

        return value, action, index + 1

    @staticmethod
    def __append_sw_in_out(packet: bytearray, sw: list[int], sw_actions: list[ValueAction]):
        for i in range(4):
            packet.append(ArtAddress.__apply_value_action(sw_actions[i], sw[i]))

    @staticmethod
    def __consume_sw_in_out(packet: bytearray, index: int) -> (list[int], list[ValueAction], int):
        sw_action = list(map(lambda i: ArtAddress.__consume_value_and_action(packet, index + i), range(4)))
        sws = list(map(lambda sw_a: sw_a[0], sw_action))
        actions = list(map(lambda sw_a: sw_a[1], sw_action))
        return sws, actions, index + 4


class ArtDiagData(ArtBase):
    def __init__(self,
                 protocol_version: int = PROTOCOL_VERSION,
                 diag_priority: DiagnosticsPriority = DiagnosticsPriority,
                 logical_port: int = 0,
                 text: str = ""
                 ) -> None:
        super().__init__(opcode=OpCode.OP_DIAG_DATA)
        self.protocol_version = protocol_version
        self.diag_priority = diag_priority
        self.logical_port = logical_port

        assert len(text) < 512
        self.text = text

    def serialize(self) -> bytearray:
        packet = super().serialize()
        self._append_int_msb(packet, self.protocol_version)
        packet.append(0x00)
        packet.append(self.diag_priority.value)
        packet.append(self.logical_port)
        packet.append(0x00)
        self._append_int_msb(packet, len(self.text))
        self._append_str(packet, self.text, len(self.text) + 1)
        return packet

    def deserialize(self, packet: bytearray) -> int:
        index = 0
        try:
            index = super().deserialize(packet)
            self.protocol_version, index = self._consume_int_msb(packet, index)
            if self.protocol_version != 14:
                raise SerializationException("Protocol is not 14!")
            index += 1
            diag_priority_byte, index = self._pop(packet, index)
            self.diag_priority = DiagnosticsPriority(diag_priority_byte)
            self.logical_port, index = self._pop(packet, index)
            index += 1
            text_length, index = self._consume_int_msb(packet, index)
            self.text, index = self._consume_str(packet, index, text_length + 1)
        except SerializationException as e:
            print(e)

        return index


class ArtTimeCode(ArtBase):
    def __init__(self,
                 protocol_version: int = PROTOCOL_VERSION,
                 frames: int = 0,
                 seconds: int = 0,
                 minutes: int = 0,
                 hours: int = 0,
                 type: TimeCodeType = TimeCodeType.FILM
                 ) -> None:
        super().__init__(opcode=OpCode.OP_TIME_CODE)
        self.protocol_version = protocol_version

        assert 0 <= frames <= 29
        self.frames = frames

        assert 0 <= seconds <= 59
        self.seconds = seconds

        assert 0 <= minutes <= 59
        self.minutes = minutes

        assert 0 <= hours <= 23
        self.hours = hours

        self.type = type

    def serialize(self) -> bytearray:
        packet = super().serialize()
        self._append_int_msb(packet, self.protocol_version)
        packet.extend([0x00] * 2)
        packet.append(self.frames)
        packet.append(self.seconds)
        packet.append(self.minutes)
        packet.append(self.hours)
        packet.append(self.type.value)
        return packet

    def deserialize(self, packet: bytearray) -> int:
        index = 0
        try:
            index = super().deserialize(packet)
            self.protocol_version, index = self._consume_int_msb(packet, index)
            if self.protocol_version != 14:
                raise SerializationException("Protocol is not 14!")
            index += 2
            self.frames, index = self._pop(packet, index)
            self.seconds, index = self._pop(packet, index)
            self.minutes, index = self._pop(packet, index)
            self.hours, index = self._pop(packet, index)

            type_bytes, index = self._pop(packet, index)
            self.type = TimeCodeType(type_bytes)
        except SerializationException as e:
            print(e)

        return index


class ArtCommand(ArtBase):
    def __init__(self,
                 protocol_version: int = PROTOCOL_VERSION,
                 esta: int = 0xFFFF,
                 command: str = ""
                 ):
        super().__init__(opcode=OpCode.OP_COMMAND)
        self.protocol_version = protocol_version
        self.esta = esta

        assert len(command) < 512
        self.command = command

    def serialize(self) -> bytearray:
        packet = super().serialize()
        self._append_int_msb(packet, self.protocol_version)
        self._append_int_msb(packet, self.esta)
        self._append_str(packet, self.command, 512)
        return packet

    def deserialize(self, packet: bytearray) -> int:
        index = 0
        try:
            index = super().deserialize(packet)
            self.protocol_version, index = self._consume_int_msb(packet, index)
            if self.protocol_version != 14:
                raise SerializationException("Protocol is not 14!")

            self.esta, index = self._consume_int_msb(packet, index)
            self.command, index = self._consume_str(packet, index, 512)

        except SerializationException as e:
            print(e)

        return index


class ArtTrigger(ArtBase):
    def __init__(self,
                 protocol_version: int = PROTOCOL_VERSION,
                 oem: int = 0xFFFF,
                 key: int = 0,
                 sub_key: int = 0,
                 payload: bytearray = [0x00] * 512
                 ):
        super().__init__(opcode=OpCode.OP_TRIGGER)
        self.protocol_version = protocol_version
        self.oem = oem
        self.key = key
        self.sub_key = sub_key

        assert len(payload) == 512
        self.payload = payload

    def serialize(self) -> bytearray:
        packet = super().serialize()
        self._append_int_msb(packet, self.protocol_version)
        packet.extend([0x00] * 2)
        self._append_int_msb(packet, self.oem)
        packet.append(self.key)
        packet.append(self.sub_key)
        packet.extend(self.payload)
        return packet

    def deserialize(self, packet: bytearray) -> int:
        index = 0
        try:
            index = super().deserialize(packet)
            self.protocol_version, index = self._consume_int_msb(packet, index)
            index += 2
            self.oem, index = self._consume_hex_number_msb(packet, index)
            if self.protocol_version != 14:
                raise SerializationException("Protocol is not 14!")

            self.key, index = self._pop(packet, index)
            self.sub_key, index = self._pop(packet, index)

            if self.oem == 0xFFFF and self.key > 3:
                print(f"Warning: Trigger key range undefined for OEM '{self.oem}', key '{self.key}'")

            self.payload, index = self._take(packet, index, 512)

        except SerializationException as e:
            print(e)

        return index


class ArtDmx(ArtBase):

    def __init__(self,
                 protocol_version: int = PROTOCOL_VERSION,
                 sequence_number: int = 0,
                 physical: int = 0,
                 port_address: PortAddress = PortAddress(0, 0, 0),
                 data: bytearray = [0x00] * 2
                 ) -> None:
        super().__init__(opcode=OpCode.OP_OUTPUT_DMX),

        self.protocol_version = protocol_version

        assert 0 <= sequence_number <= 0xFF
        self.sequence_number = sequence_number

        assert 0 <= physical <= 3
        self.physical = physical

        self.port_address = port_address

        assert len(data) <= 512
        self.data = data

    def serialize(self) -> bytearray:
        packet = super().serialize()
        self._append_int_msb(packet, self.protocol_version)
        packet.append(self.sequence_number)
        packet.append(self.physical)

        port_address = self.port_address.port_address
        packet.append(port_address & 0x0F)
        packet.append(port_address >> 8 & 0x0F)

        self._append_int_msb(packet, len(self.data))
        packet.extend(self.data)
        return packet

    def deserialize(self, packet: bytearray) -> int:
        index = 0
        try:
            index = super().deserialize(packet)
            self.protocol_version, index = self._consume_int_msb(packet, index)
            self.sequence_number, index = self._pop(packet, index)
            self.physical, index = self._pop(packet, index)

            sub_uni, index = self._pop(packet, index)
            net, index = self._pop(packet, index)
            self.port_address.port_address = net << 8 | sub_uni

            data_length, index = self._consume_int_msb(packet, index)
            self.data, index = self._take(packet, data_length, index)
        except SerializationException as e:
            print(e)

        return index


class SerializationException(Exception):

    def __init__(self, *args: object) -> None:
        super().__init__(*args)
