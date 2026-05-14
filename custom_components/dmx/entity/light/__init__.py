from dataclasses import dataclass, field
from enum import Enum, auto

from custom_components.dmx.correction import OutputCorrection
from custom_components.dmx.fixture.channel import Channel


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
    dmx_indexes: list[int]
    channel: Channel
    channel_type: ChannelType
    output_correction: OutputCorrection | None = field(default=None)
