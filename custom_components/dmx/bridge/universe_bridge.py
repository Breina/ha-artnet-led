from typing import Literal

from pyartnet import BaseUniverse

from custom_components.dmx.bridge.channel_bridge import ChannelBridge


class UniverseBridge(BaseUniverse):
    def receive_data(self, data: bytearray):
        channels = self._channels

        for channel in channels.values():
            channel.from_buffer(data)

    def add_channel(self, start: int, width: int, channel_name: str = '', byte_size: int = 1,
                    byte_order: Literal['big', 'little'] = 'big') -> ChannelBridge:
        channel_bridge = ChannelBridge(super().add_channel(start, width, channel_name, byte_size, byte_order))
        self._channels[channel_name] = channel_bridge
        return channel_bridge
