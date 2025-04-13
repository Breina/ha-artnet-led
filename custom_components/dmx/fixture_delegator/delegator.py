from dataclasses import dataclass
from enum import Enum, auto
from itertools import groupby
from typing import List

from homeassistant.components.light import ColorMode
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from custom_components.dmx.entity.light import DMXLightChannel, LightChannel, DMXLightEntity
from custom_components.dmx.entity.number import DmxNumberEntity
from custom_components.dmx.entity.select import DmxSelectEntity
from custom_components.dmx.fixture.capability import ColorIntensity, \
    SingleColor, Intensity, ColorTemperature
from custom_components.dmx.fixture.channel import ChannelOffset, \
    SwitchingChannel, Channel
from custom_components.dmx.io.dmx_io import DmxUniverse


@dataclass
class MappedChannel:
    dmx_channel_indexes: list[int]
    channel: Channel


def __get_channel(source: tuple[int, None | ChannelOffset | SwitchingChannel]) -> list[tuple[int, ChannelOffset]]:
    if isinstance(source[1], ChannelOffset):
        return [source]
    elif isinstance(source[1], SwitchingChannel):
        return [(source[0], c) for c in source[1].controlled_channels.values()]
    else:
        return [source]


def __get_all_channels(index_channels: list[tuple[int, None | ChannelOffset | SwitchingChannel]]) -> list[tuple[int, ChannelOffset]]:
    return [c for channel_sub in index_channels for c in __get_channel(channel_sub)]


def __accumulate_light_entities(accumulator: dict[str, list[DMXLightChannel]],
                                dmx_channel_indexes: List[int], channel: Channel, universe: DmxUniverse) -> None:
    assert len(channel.capabilities) == 1

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
        else:
            return

    elif isinstance(capability, Intensity):
        light_channel = LightChannel.DIMMER

    elif isinstance(capability, ColorTemperature):
        light_channel = LightChannel.COLOR_TEMPERATURE

    # TODO how to handle hue / saturation? Not in the standard. See arri/l10-c.json for example.

    else:
        return

    accumulated_light_channel = DMXLightChannel(dmx_channel_indexes, channel, light_channel)
    if channel.matrix_key in accumulator:
        accumulator[channel.matrix_key].append(accumulated_light_channel)
    else:
        accumulator[channel.matrix_key] = [accumulated_light_channel]


def __build_light_entities(accumulator: dict[str, list[DMXLightChannel]], device: DeviceInfo, universe: DmxUniverse) -> list[Entity]:
    entities = []

    for matrix_key, accumulated_channels in accumulator.items():
        channel_map = {}
        for accumulated_channel in accumulated_channels:
            channel_map[accumulated_channel.light_channel] = accumulated_channel

        has_rgb = (LightChannel.RED in channel_map and
                   LightChannel.GREEN in channel_map and
                   LightChannel.BLUE in channel_map)

        has_cold_warm = (LightChannel.COLD_WHITE in channel_map and
                         LightChannel.WARM_WHITE in channel_map)

        has_color_temp = LightChannel.COLOR_TEMPERATURE in channel_map

        has_temp_control = has_cold_warm or has_color_temp

        has_single_white = (LightChannel.COLD_WHITE in channel_map or
                            LightChannel.WARM_WHITE in channel_map)

        has_dimmer = LightChannel.DIMMER in channel_map

        channels_data = []
        has_separate_dimmer = False

        if has_rgb:
            if has_dimmer:
                has_separate_dimmer = True
                channels_data.append(channel_map[LightChannel.DIMMER])

            channels_data.append(channel_map[LightChannel.RED])
            channels_data.append(channel_map[LightChannel.GREEN])
            channels_data.append(channel_map[LightChannel.BLUE])

            if has_temp_control:
                color_mode = ColorMode.RGBWW

                if LightChannel.COLD_WHITE in channel_map:
                    channels_data.append(channel_map[LightChannel.COLD_WHITE])

                if LightChannel.WARM_WHITE in channel_map:
                    channels_data.append(channel_map[LightChannel.WARM_WHITE])

                if LightChannel.COLOR_TEMPERATURE in channel_map:
                    channels_data.append(channel_map[LightChannel.COLOR_TEMPERATURE])

            elif has_single_white:
                color_mode = ColorMode.RGBW

                if LightChannel.COLD_WHITE in channel_map:
                    channels_data.append(channel_map[LightChannel.COLD_WHITE])
                elif LightChannel.WARM_WHITE in channel_map:
                    channels_data.append(channel_map[LightChannel.WARM_WHITE])

            else:
                color_mode = ColorMode.RGB

        elif has_temp_control:
            color_mode = ColorMode.COLOR_TEMP

            if has_dimmer:
                has_separate_dimmer = True
                channels_data.append(channel_map[LightChannel.DIMMER])

            if LightChannel.COLD_WHITE in channel_map:
                channels_data.append(channel_map[LightChannel.COLD_WHITE])

            if LightChannel.WARM_WHITE in channel_map:
                channels_data.append(channel_map[LightChannel.WARM_WHITE])

            if LightChannel.COLOR_TEMPERATURE in channel_map:
                channels_data.append(channel_map[LightChannel.COLOR_TEMPERATURE])

        elif has_single_white or has_dimmer:
            color_mode = ColorMode.BRIGHTNESS

            if has_dimmer:
                has_separate_dimmer = True
                channels_data.append(channel_map[LightChannel.DIMMER])

            if has_single_white:
                if LightChannel.COLD_WHITE in channel_map:
                    channels_data.append(channel_map[LightChannel.COLD_WHITE])
                elif LightChannel.WARM_WHITE in channel_map:
                    channels_data.append(channel_map[LightChannel.WARM_WHITE])

        else:
            # No suitable channels for a light entity
            continue

        entities.append(DMXLightEntity(
            matrix_key=matrix_key,
            color_mode=color_mode,
            channels=channels_data,
            device=device,
            universe=universe,
            has_separate_dimmer=has_separate_dimmer,
        ))

    return entities


def create_entities(
        dmx_start: int,
        channels: list[None | ChannelOffset | SwitchingChannel],
        device: DeviceInfo,
        universe: DmxUniverse
) -> list[Entity]:
    entities = []
    lights_accumulator: dict[str, list[DMXLightChannel]] = {}

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
            __accumulate_light_entities(lights_accumulator, dmx_indexes, channel, universe)

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

    entities.extend(__build_light_entities(lights_accumulator, device, universe))

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
