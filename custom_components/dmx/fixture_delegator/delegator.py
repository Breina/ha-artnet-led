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


def create_entities(
        dmx_start: int,
        channels: list[None | ChannelOffset | SwitchingChannel]
):
    universe = Universe()
    entities = []

    for name, group in groupby(enumerate(channels), lambda c: c[1].channel):
        # print(list(sorted(group, key=lambda channel: channel[1].byte_offset)))
        dmx_indexes = []
        channel: Channel | None = None
        for channel_group in sorted(group, key=lambda g: g[1].byte_offset):
            if not channel:
                channel = channel_group[1].channel
            dmx_indexes.append(channel_group[0] + dmx_start)

        print(channel, dmx_indexes)

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
            entities.extend(number_entities)



fixture = parse("../../../staging/fixtures/hydrabeam-300-rgbw.json")
channels = fixture.select_mode("42-channel")

create_entities(100, channels)
