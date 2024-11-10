from dataclasses import dataclass
from itertools import groupby

from custom_components.dmx.entity.number import DmxNumberEntity
from custom_components.dmx.entity.select import DmxSelectEntity
from custom_components.dmx.fixture.channel import ChannelOffset, \
    SwitchingChannel, Channel
from custom_components.dmx.fixture.parser import parse
from custom_components.dmx.io.dmx_io import Universe


@dataclass
class MappedChannel:
    dmx_channel_indexes: list[int]
    channel: Channel


def __get_channel(source: tuple[int, None | ChannelOffset | SwitchingChannel]):
    if isinstance(source[1], ChannelOffset):
        return [source]
    elif isinstance(source[1], SwitchingChannel):
        return [(source[0], c) for c in source[1].controlled_channels.values()]
    else:
        return [source]


def __get_all_channels(index_channels: list[tuple[int, None | ChannelOffset | SwitchingChannel]]):
    return [c for channel_sub in index_channels for c in __get_channel(channel_sub)]


def create_entities(
        dmx_start: int,
        channels: list[None | ChannelOffset | SwitchingChannel]
):
    universe = Universe()
    entities = []

    for channel, group in groupby(__get_all_channels(enumerate(channels)),
                                  lambda c: c[1].channel):
        dmx_indexes = []
        for channel_group in sorted(group, key=lambda g: g[1].byte_offset):
            dmx_indexes.append(channel_group[0] + dmx_start)

        if not channel.has_multiple_capabilities():
            entities.append(
                DmxNumberEntity(
                    channel.name, channel.capabilities[0], universe, dmx_indexes
                )
            )
        else:
            assert len(dmx_indexes) == 1
            number_entities = {
                str(capability): DmxNumberEntity(
                    f"{channel.name} {str(capability)}", capability,
                    universe, dmx_indexes,
                    available=False
                )
                for capability in channel.capabilities
                if capability.is_dynamic_entity()
            }

            select_entity = DmxSelectEntity(
                channel, number_entities, universe, dmx_indexes[0]
            )

            entities.append(select_entity)
            entities.extend(number_entities.values())

    for entity in entities:
        if isinstance(entity, DmxSelectEntity):
            entity.link_switching_entities(entities)

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
