from dataclasses import dataclass
from enum import Enum, auto
from itertools import groupby

from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.dmx.entity.number import DmxNumberEntity
from custom_components.dmx.entity.select import DmxSelectEntity
from custom_components.dmx.fixture.capability import ColorIntensity, \
    SingleColor, Intensity, ColorTemperature
from custom_components.dmx.fixture.channel import ChannelOffset, \
    SwitchingChannel, Channel
from custom_components.dmx.io.dmx_io import Universe


@dataclass
class MappedChannel:
    dmx_channel_indexes: list[int]
    channel: Channel


class LightChannel(Enum):
    RED = auto()
    GREEN = auto()
    BLUE = auto()
    COLD_WHITE = auto()
    WARM_WHITE = auto()
    COLOR_TEMPERATURE = auto()
    DIMMER = auto()


def __get_channel(source: tuple[int, None | ChannelOffset | SwitchingChannel]) -> list[tuple[int, ChannelOffset]]:
    if isinstance(source[1], ChannelOffset):
        return [source]
    elif isinstance(source[1], SwitchingChannel):
        return [(source[0], c) for c in source[1].controlled_channels.values()]
    else:
        return [source]


def __get_all_channels(index_channels: list[tuple[int, None | ChannelOffset | SwitchingChannel]]) -> list[
    tuple[int, ChannelOffset]]:
    return [c for channel_sub in index_channels for c in __get_channel(channel_sub)]


def __accumulate_light_entities(accumulator: dict[str, dict[LightChannel, list[ChannelOffset]]],
                                channel_offset: ChannelOffset) -> None:

    channel = channel_offset.channel
    assert len(channel.capabilities) == 1

    if channel.matrix_key not in accumulator:
        accumulator[channel.matrix_key] = {}

    light_channel = None
    capability = channel.capabilities[0]
    if isinstance(capability, ColorIntensity):
        if capability.color == SingleColor.Red:
            light_channel = LightChannel.RED
        elif capability.color == SingleColor.Green:
            light_channel = LightChannel.GREEN
        elif capability.color == SingleColor.Blue:
            light_channel = LightChannel.BLUE
        elif capability.color == SingleColor.ColdWhite:
            light_channel = LightChannel.COLD_WHITE
        elif capability.color == SingleColor.WarmWhite:
            light_channel = LightChannel.WARM_WHITE
    elif isinstance(capability, Intensity):
        light_channel = LightChannel.DIMMER
    elif isinstance(capability, ColorTemperature):
        light_channel = LightChannel.COLOR_TEMPERATURE

    if light_channel in accumulator[channel.matrix_key]:
        accumulator[channel.matrix_key][light_channel].append(channel_offset)
    else:
        accumulator[channel.matrix_key][light_channel] = [channel_offset]


def __build_light_entities(accumulator: dict[str, dict[LightChannel, list[ChannelOffset]]]) -> :



def create_entities(
        dmx_start: int,
        channels: list[None | ChannelOffset | SwitchingChannel],
        device: DeviceInfo
) -> list[Entity]:
    universe = Universe()
    entities = []
    lights_accumulator: dict[str[str, list[ChannelOffset]]] = {}

    for channel, group in groupby(__get_all_channels(enumerate(channels)), lambda c: c[1].channel):
        dmx_indexes = []
        for channel_group in sorted(group, key=lambda g: g[1].byte_offset):
            dmx_indexes.append(channel_group[0] + dmx_start)

        if not channel.has_multiple_capabilities():
            entities.append(
                DmxNumberEntity(
                    channel.name, channel.capabilities[0], universe,
                    dmx_indexes, device
                )
            )
            __accumulate_light_entities(lights_accumulator, channel)

        else:
            assert len(dmx_indexes) == 1
            number_entities = {
                str(capability): DmxNumberEntity(
                    f"{channel.name} {str(capability)}", capability,
                    universe, dmx_indexes, device,
                    available=False
                )
                for capability in channel.capabilities
                if capability.is_dynamic_entity()
            }

            select_entity = DmxSelectEntity(
                channel, number_entities, universe, dmx_indexes[0], device
            )

            entities.append(select_entity)
            entities.extend(number_entities.values())

    for entity in entities:
        if isinstance(entity, DmxSelectEntity):
            entity.link_switching_entities(entities)

    entities.extend(__build_light_entities(lights_accumulator))

    return entities

# fixture = parse("../../../staging/fixtures/hotbox-rgbw.json")
# channels = fixture.select_mode("9-channel B")
# fixture = parse("../../../staging/fixtures/hydrabeam-300-rgbw.json")
# channels = fixture.select_mode("42-channel")
# fixture = parse("../../../staging/fixtures/jbled-a7.json")
# channels = fixture.select_mode("Standard 16bit")
#
# entities = create_entities(100, channels)
#
# print("\nThe entities:")
# for entity in entities:
#     print(entity)
