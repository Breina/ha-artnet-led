from dataclasses import dataclass
from enum import Enum, auto
from typing import List

from custom_components.artnet_led.fixture.channel import Channel


class ChannelType(Enum):
    RED = auto()
    GREEN = auto()
    BLUE = auto()
    COLD_WHITE = auto()
    WARM_WHITE = auto()
    COLOR_TEMPERATURE = auto()
    DIMMER = auto()


@dataclass
class ChannelMapping:
    dmx_indexes: List[int]
    channel: Channel
    channel_type: ChannelType
