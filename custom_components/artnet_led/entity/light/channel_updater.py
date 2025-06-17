from typing import Dict

from custom_components.artnet_led.io.dmx_io import DmxUniverse
from custom_components.artnet_led.entity.light import ChannelType, ChannelMapping


def from_dmx_value(dmx_values) -> float:
    total = 0
    for dmx_value in dmx_values:
        total = total * 256 + dmx_value
    max_value = 256 ** len(dmx_values) - 1
    value = 255 * (total / max_value)
    return value


class ChannelUpdater:
    def __init__(self, channels: Dict[ChannelType, ChannelMapping], universe: DmxUniverse):
        self.channels = channels
        self.universe = universe

    async def send_updates(self, updates: Dict[ChannelType, int]):
        dmx_updates = {}
        for channel_type, value in updates.items():
            if channel_type in self.channels:
                dmx_indexes = self.channels[channel_type].dmx_indexes
                num_channels = len(dmx_indexes)
                max_value = 256 ** num_channels - 1

                scaled_total = int((value / 255) * max_value)

                for i in range(num_channels):
                    shift = 8 * (num_channels - i - 1)
                    dmx_value = (scaled_total >> shift) & 0xFF
                    dmx_updates[dmx_indexes[i]] = dmx_value

        if dmx_updates:
            await self.universe.update_multiple_values(dmx_updates)

    def has_channel(self, channel_type: ChannelType) -> bool:
        return channel_type in self.channels

    def has_rgb(self) -> bool:
        return all(self.has_channel(t) for t in [ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE])

    def has_cw_ww(self) -> bool:
        return all(self.has_channel(t) for t in [ChannelType.COLD_WHITE, ChannelType.WARM_WHITE])
