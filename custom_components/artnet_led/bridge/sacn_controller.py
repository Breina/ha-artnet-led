import logging
from typing import Literal

from pyartnet.impl_sacn import SacnNode, SacnUniverse

from custom_components.artnet_led.bridge.channel_bridge import ChannelBridge
from custom_components.artnet_led.bridge.universe_bridge import UniverseBridge

log = logging.getLogger(__name__)


class SacnUniverseBridge(UniverseBridge, SacnUniverse):
    def __init__(self, node: SacnNode, universe: int = 1) -> None:
        SacnUniverse.__init__(self, node, universe)

    def receive_data(self, data: bytearray):
        channels = self._channels
        if isinstance(channels, list):
            for channel in channels:
                if hasattr(channel, "from_buffer"):
                    channel.from_buffer(data)
        elif isinstance(channels, dict):
            for channel in channels.values():
                if hasattr(channel, "from_buffer"):
                    channel.from_buffer(data)

    def add_channel(self, start: int, width: int, channel_name: str = '', byte_size: int = 1,
                    byte_order: Literal['big', 'little'] = 'big') -> ChannelBridge:
        base_channel = SacnUniverse.add_channel(self, start, width, channel_name, byte_size, byte_order)
        channel_bridge = ChannelBridge(base_channel)
        if isinstance(self._channels, list):
            for i, ch in enumerate(self._channels):
                if ch is base_channel:
                    self._channels[i] = channel_bridge
                    break
        elif isinstance(self._channels, dict):
            self._channels[channel_name] = channel_bridge
        return channel_bridge



class SacnNodeBridge(SacnNode):
    def _create_universe(self, nr: int) -> SacnUniverseBridge:
        return SacnUniverseBridge(self, self._validate_universe_nr(nr))


SacnController = SacnNodeBridge

