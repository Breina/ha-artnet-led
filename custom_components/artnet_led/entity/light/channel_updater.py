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

    def has_channel(self, channel_type: ChannelType) -> bool:
        return channel_type in self.channels

    def has_rgb(self) -> bool:
        return all(self.has_channel(t) for t in [ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE])

    def has_cw_ww(self) -> bool:
        return all(self.has_channel(t) for t in [ChannelType.COLD_WHITE, ChannelType.WARM_WHITE])
