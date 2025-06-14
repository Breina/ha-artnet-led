from typing import Dict

from custom_components.artnet_led.io.dmx_io import DmxUniverse
from custom_components.artnet_led.entity.light import ChannelType, ChannelMapping


class ChannelUpdater:
    def __init__(self, channels: Dict[ChannelType, ChannelMapping], universe: DmxUniverse):
        self.channels = channels
        self.universe = universe

    async def send_updates(self, updates: Dict[ChannelType, int]):
        dmx_updates = {}
        for channel_type, value in updates.items():
            if channel_type in self.channels:
                for dmx_idx in self.channels[channel_type].dmx_indexes:
                    dmx_updates[dmx_idx] = max(0, min(255, value))

        if dmx_updates:
            await self.universe.update_multiple_values(dmx_updates)

    def has_channel(self, channel_type: ChannelType) -> bool:
        return channel_type in self.channels

    def has_rgb(self) -> bool:
        return all(self.has_channel(t) for t in [ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE])

    def has_cw_ww(self) -> bool:
        return all(self.has_channel(t) for t in [ChannelType.COLD_WHITE, ChannelType.WARM_WHITE])
