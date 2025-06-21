from dataclasses import dataclass
from itertools import groupby
from typing import List

from homeassistant.components.light import ColorMode
from homeassistant.helpers.entity import Entity, DeviceInfo

from custom_components.dmx.entity.light import ChannelMapping, ChannelType
from custom_components.dmx.entity.light.light_entity import DmxLightEntity
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


def __accumulate_light_entities(accumulator: dict[str, list[ChannelMapping]], dmx_channel_indexes: List[int], channel: Channel) -> None:
    assert len(channel.capabilities) == 1

    capability = channel.capabilities[0]
    if isinstance(capability, ColorIntensity):
        if capability.color == SingleColor.Red:
            light_channel = ChannelType.RED
        elif capability.color == SingleColor.Green:
            light_channel = ChannelType.GREEN
        elif capability.color == SingleColor.Blue:
            light_channel = ChannelType.BLUE
        elif capability.color == SingleColor.ColdWhite:
            light_channel = ChannelType.COLD_WHITE
        elif capability.color == SingleColor.WarmWhite or capability.color == SingleColor.White: # Treat normal white as Warm white so make logic simpler
            light_channel = ChannelType.WARM_WHITE
        else:
            return

    elif isinstance(capability, Intensity):
        light_channel = ChannelType.DIMMER

    elif isinstance(capability, ColorTemperature):
        light_channel = ChannelType.COLOR_TEMPERATURE

    # TODO hue / saturation https://github.com/OpenLightingProject/open-fixture-library/issues/4927
    # TODO XY color https://github.com/OpenLightingProject/open-fixture-library/issues/4900

    else:
        return

    accumulated_light_channel = ChannelMapping(dmx_channel_indexes, channel, light_channel)
    if channel.matrix_key in accumulator:
        accumulator[channel.matrix_key].append(accumulated_light_channel)
    else:
        accumulator[channel.matrix_key] = [accumulated_light_channel]


def __build_light_entities(name: str, accumulator: dict[str, list[ChannelMapping]], device: DeviceInfo, universe: DmxUniverse) -> list[Entity]:
    entities = []

    for matrix_key, accumulated_channels in accumulator.items():
        channel_map: dict[ChannelType, ChannelMapping] = {}
        for accumulated_channel in accumulated_channels:
            channel_map[accumulated_channel.channel_type] = accumulated_channel

        has_rgb = (ChannelType.RED in channel_map and
                   ChannelType.GREEN in channel_map and
                   ChannelType.BLUE in channel_map)

        has_cold_warm = (ChannelType.COLD_WHITE in channel_map and
                         ChannelType.WARM_WHITE in channel_map)

        has_color_temp = ChannelType.COLOR_TEMPERATURE in channel_map

        has_temp_control = has_cold_warm or has_color_temp

        has_single_white = (ChannelType.COLD_WHITE in channel_map or
                            ChannelType.WARM_WHITE in channel_map)

        has_dimmer = ChannelType.DIMMER in channel_map

        channels_data = []
        has_separate_dimmer = False
        min_kelvin = 2000
        max_kelvin = 6500

        if has_rgb:
            if has_dimmer:
                has_separate_dimmer = True
                channels_data.append(channel_map[ChannelType.DIMMER])

            channels_data.append(channel_map[ChannelType.RED])
            channels_data.append(channel_map[ChannelType.GREEN])
            channels_data.append(channel_map[ChannelType.BLUE])

            if has_temp_control:
                color_mode = ColorMode.RGBWW

                if ChannelType.COLD_WHITE in channel_map:
                    channels_data.append(channel_map[ChannelType.COLD_WHITE])

                if ChannelType.WARM_WHITE in channel_map:
                    channels_data.append(channel_map[ChannelType.WARM_WHITE])

                if ChannelType.COLOR_TEMPERATURE in channel_map:
                    channel_temp = channel_map[ChannelType.COLOR_TEMPERATURE]
                    channels_data.append(channel_temp)

                    if isinstance(channel_temp.channel.capabilities[0], ColorTemperature):
                        color_temperature: ColorTemperature = channel_temp.channel.capabilities[0]

                        min_color_temp_entity, max_color_temp_entity = color_temperature.color_temperature
                        if min_color_temp_entity.unit == 'K':
                            min_kelvin = min_color_temp_entity.value

                        if max_color_temp_entity.unit == 'K':
                            max_kelvin = max_color_temp_entity.value

            elif has_single_white:
                color_mode = ColorMode.RGBW

                if ChannelType.COLD_WHITE in channel_map:
                    channels_data.append(channel_map[ChannelType.COLD_WHITE])
                elif ChannelType.WARM_WHITE in channel_map:
                    channels_data.append(channel_map[ChannelType.WARM_WHITE])

            else:
                color_mode = ColorMode.RGB

        elif has_temp_control:
            color_mode = ColorMode.COLOR_TEMP

            if has_dimmer:
                has_separate_dimmer = True
                channels_data.append(channel_map[ChannelType.DIMMER])

            # TODO color temperature bounds https://github.com/OpenLightingProject/open-fixture-library/issues/4922

            if ChannelType.COLD_WHITE in channel_map:
                channels_data.append(channel_map[ChannelType.COLD_WHITE])

            if ChannelType.WARM_WHITE in channel_map:
                channels_data.append(channel_map[ChannelType.WARM_WHITE])

            if ChannelType.COLOR_TEMPERATURE in channel_map:
                channel_temp = channel_map[ChannelType.COLOR_TEMPERATURE]
                channels_data.append(channel_temp)

                if isinstance(channel_temp.channel.capabilities[0], ColorTemperature):
                    color_temperature: ColorTemperature = channel_temp.channel.capabilities[0]

                    min_color_temp_entity, max_color_temp_entity = color_temperature.color_temperature
                    if min_color_temp_entity.unit == 'K':
                        min_kelvin = min_color_temp_entity.value

                    if max_color_temp_entity.unit == 'K':
                        max_kelvin = max_color_temp_entity.value

        elif has_single_white or has_dimmer:
            color_mode = ColorMode.BRIGHTNESS

            if has_dimmer:
                has_separate_dimmer = True
                channels_data.append(channel_map[ChannelType.DIMMER])

            if has_single_white:
                if ChannelType.COLD_WHITE in channel_map:
                    channels_data.append(channel_map[ChannelType.COLD_WHITE])
                elif ChannelType.WARM_WHITE in channel_map:
                    channels_data.append(channel_map[ChannelType.WARM_WHITE])

        else:
            # No suitable channels for a light entity
            continue

        entities.append(DmxLightEntity(
            name=name,
            matrix_key=matrix_key,
            color_mode=color_mode,
            channels=channels_data,
            device=device,
            universe=universe,
            has_separate_dimmer=has_separate_dimmer,
            min_kelvin=min_kelvin,
            max_kelvin=max_kelvin,
        ))

    return entities


def create_entities(
        name: str,
        dmx_start: int,
        channels: list[None | ChannelOffset | SwitchingChannel],
        device: DeviceInfo,
        universe: DmxUniverse
) -> list[Entity]:
    entities = []
    lights_accumulator: dict[str, list[ChannelMapping]] = {}

    for channel, group in groupby(__get_all_channels(enumerate(channels)), lambda c: c[1].channel):
        dmx_indexes = []
        for channel_group in sorted(group, key=lambda g: g[1].byte_offset):
            dmx_indexes.append(channel_group[0] + dmx_start)

        if channel.constant:
            universe.set_constant_value(dmx_indexes, channel.default_value)

        if not channel.has_multiple_capabilities():
            entities.append(
                DmxNumberEntity(
                    f"{name} {channel.name}", channel.capabilities[0], universe,
                    dmx_indexes, device
                )
            )
            __accumulate_light_entities(lights_accumulator, dmx_indexes, channel)

        else:
            assert len(dmx_indexes) == 1
            number_entities = {
                str(capability): DmxNumberEntity(
                    f"{name} {channel.name} {str(capability)}", capability,
                    universe, dmx_indexes, device,
                    available=False
                )
                for capability in channel.capabilities
                if capability.is_dynamic_entity()
            }

            select_entity = DmxSelectEntity(
                f"{name} {channel.name}", channel, number_entities, universe, dmx_indexes[0], device
            )

            entities.append(select_entity)
            entities.extend(number_entities.values())

    for entity in entities:
        if isinstance(entity, DmxSelectEntity):
            entity.link_switching_entities(entities)

    entities.extend(__build_light_entities(name, lights_accumulator, device, universe))

    return entities
