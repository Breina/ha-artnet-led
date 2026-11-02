from dataclasses import dataclass, replace

from homeassistant.components.light import ColorMode
from homeassistant.helpers.entity import DeviceInfo, Entity

from custom_components.dmx.correction import OutputCorrection
from custom_components.dmx.entity.light import ChannelMapping, ChannelType
from custom_components.dmx.entity.light.light_entity import DmxLightEntity
from custom_components.dmx.entity.number import DmxNumberEntity
from custom_components.dmx.entity.select import DmxSelectEntity, capability_options
from custom_components.dmx.fixture.capability import (
    ColorIntensity,
    ColorTemperature,
    Intensity,
    NoFunction,
    SingleColor,
)
from custom_components.dmx.fixture.channel import Channel, ChannelOffset, SwitchingChannel, range_value_to_dmx_bytes
from custom_components.dmx.io.dmx_io import DmxUniverse
from custom_components.dmx.util.fixture_fingerprint import generate_fixture_fingerprint


@dataclass
class MappedChannel:
    dmx_channel_indexes: list[int]
    channel: Channel


def __get_channel(source: tuple[int, ChannelOffset | SwitchingChannel | None]) -> list[tuple[int, ChannelOffset]]:
    if isinstance(source[1], ChannelOffset):
        return [(source[0], source[1])]
    elif isinstance(source[1], SwitchingChannel):
        return [(source[0], c) for c in source[1].controlled_channels.values()]
    else:
        return []


def __get_all_channels(
    index_channels: list[tuple[int, ChannelOffset | SwitchingChannel | None]],
) -> list[tuple[int, ChannelOffset]]:
    return [c for channel_sub in index_channels for c in __get_channel(channel_sub)]


def _group_by_channel(
    channels: list[tuple[int, ChannelOffset]],
) -> list[tuple[Channel, list[tuple[int, ChannelOffset]]]]:
    """
    Groups the bytes of each channel, which don't need to be next to each other, like Pan, Tilt, Pan fine, Tilt fine.
    A channel occupying the same byte in multiple slots is that many separate groups.
    """
    groups: list[tuple[Channel, list[tuple[int, ChannelOffset]]]] = []
    for slot, channel_offset in channels:
        for channel, group in groups:
            if channel is channel_offset.channel and all(g[1].byte_offset != channel_offset.byte_offset for g in group):
                group.append((slot, channel_offset))
                break
        else:
            groups.append((channel_offset.channel, [(slot, channel_offset)]))
    return groups


def _correction_for_channel(channel: Channel, output_correction: OutputCorrection | None) -> OutputCorrection | None:
    """Return correction only for correctable intensity channels (not CT, pan, tilt, etc.)."""
    if output_correction is None:
        return None
    cap = channel.capabilities
    if isinstance(cap, list):
        cap = cap[0] if cap else None
    return output_correction if isinstance(cap, (ColorIntensity, Intensity)) else None


def __accumulate_light_entities(
    accumulator: dict[str, list[ChannelMapping]],
    dmx_channel_indexes: list[int],
    channel: Channel,
    output_correction: OutputCorrection | None = None,
) -> None:
    capabilities = channel.capabilities
    if isinstance(capabilities, list):
        assert len(capabilities) == 1
        capability = capabilities[0]
    else:
        capability = capabilities

    if not capability.is_dynamic_entity():
        return

    if isinstance(capability, ColorIntensity):
        if capability.color == SingleColor.Red:
            light_channel = ChannelType.RED
        elif capability.color == SingleColor.Green:
            light_channel = ChannelType.GREEN
        elif capability.color == SingleColor.Blue:
            light_channel = ChannelType.BLUE
        elif capability.color == SingleColor.ColdWhite:
            light_channel = ChannelType.COLD_WHITE
        elif (
            capability.color == SingleColor.WarmWhite or capability.color == SingleColor.White
        ):  # Treat normal white as Warm white so make logic simpler
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

    correction_for_channel = None if light_channel == ChannelType.COLOR_TEMPERATURE else output_correction
    accumulated_light_channel = ChannelMapping(dmx_channel_indexes, channel, light_channel, correction_for_channel)
    matrix_key = channel.matrix_key or ""  # Use empty string as default key for non-matrix channels
    if matrix_key in accumulator:
        accumulator[matrix_key].append(accumulated_light_channel)
    else:
        accumulator[matrix_key] = [accumulated_light_channel]


def _color_temperature_bounds(mapping: ChannelMapping) -> tuple[int, int]:
    """
    Return the Kelvin bounds of a color temperature channel, lowest first.

    Fixture profiles may run either way (Robe: 8000K -> 2700K), but ColorConverter and Home Assistant both
    need min < max. The direction itself is handled by the channel's own DMX mapping.
    """
    min_kelvin, max_kelvin = 2000, 6500

    capabilities = mapping.channel.capabilities
    capability = capabilities[0] if isinstance(capabilities, list) else capabilities
    if not isinstance(capability, ColorTemperature) or len(capability.color_temperature) != 2:
        return min_kelvin, max_kelvin

    start, end = capability.color_temperature
    if start.unit == "K":
        min_kelvin = int(start.value)
    if end.unit == "K":
        max_kelvin = int(end.value)

    return min(min_kelvin, max_kelvin), max(min_kelvin, max_kelvin)


def __build_light_entities(
    name: str,
    entity_id_prefix: str | None,
    accumulator: dict[str, list[ChannelMapping]],
    device: DeviceInfo,
    universe: DmxUniverse,
    fixture_fingerprint: str,
) -> list[Entity]:
    entities: list[Entity] = []

    for matrix_key, accumulated_channels in accumulator.items():
        channel_map: dict[ChannelType, ChannelMapping] = {}
        for accumulated_channel in accumulated_channels:
            if accumulated_channel.channel_type == ChannelType.COLOR_TEMPERATURE:
                # Later CCT channels are secondary, e.g. Kelvin Epos' "RGB Device white point"; they stay numbers.
                channel_map.setdefault(ChannelType.COLOR_TEMPERATURE, accumulated_channel)
            else:
                channel_map[accumulated_channel.channel_type] = accumulated_channel

        # A lone white channel is a white intensity, whatever its shade: same convention as plain White above.
        if ChannelType.COLD_WHITE in channel_map and ChannelType.WARM_WHITE not in channel_map:
            channel_map[ChannelType.WARM_WHITE] = replace(
                channel_map.pop(ChannelType.COLD_WHITE), channel_type=ChannelType.WARM_WHITE
            )

        has_rgb = (
            ChannelType.RED in channel_map and ChannelType.GREEN in channel_map and ChannelType.BLUE in channel_map
        )

        has_cold_warm = ChannelType.COLD_WHITE in channel_map and ChannelType.WARM_WHITE in channel_map

        has_color_temp = ChannelType.COLOR_TEMPERATURE in channel_map

        has_temp_control = has_cold_warm or has_color_temp

        has_single_white = ChannelType.WARM_WHITE in channel_map and not has_cold_warm

        has_dimmer = ChannelType.DIMMER in channel_map

        channels_data = []
        has_separate_dimmer = False
        min_kelvin = 2000
        max_kelvin = 6500
        supported_color_modes: set[ColorMode] | None = None

        if has_rgb:
            if has_dimmer:
                has_separate_dimmer = True
                channels_data.append(channel_map[ChannelType.DIMMER])

            channels_data.append(channel_map[ChannelType.RED])
            channels_data.append(channel_map[ChannelType.GREEN])
            channels_data.append(channel_map[ChannelType.BLUE])

            if has_cold_warm:
                color_mode = ColorMode.RGBWW

                channels_data.append(channel_map[ChannelType.COLD_WHITE])
                channels_data.append(channel_map[ChannelType.WARM_WHITE])

                if has_color_temp:
                    channels_data.append(channel_map[ChannelType.COLOR_TEMPERATURE])
                    min_kelvin, max_kelvin = _color_temperature_bounds(channel_map[ChannelType.COLOR_TEMPERATURE])

            elif has_color_temp and (has_single_white or has_dimmer):
                # RGB next to a CCT channel, without separately controllable cold and warm whites. Home Assistant
                # models this as two modes, either showing a color or showing white at a color temperature.
                # Without a dimmer or white channel, there is nothing to dim or switch off that white with, so
                # that case is handled as plain RGB below and CCT stays available as a number entity.
                color_mode = ColorMode.COLOR_TEMP
                supported_color_modes = {ColorMode.COLOR_TEMP, ColorMode.RGBW if has_single_white else ColorMode.RGB}

                if has_single_white:
                    channels_data.append(channel_map[ChannelType.WARM_WHITE])

                channels_data.append(channel_map[ChannelType.COLOR_TEMPERATURE])
                min_kelvin, max_kelvin = _color_temperature_bounds(channel_map[ChannelType.COLOR_TEMPERATURE])

            elif has_single_white:
                color_mode = ColorMode.RGBW

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

            if has_color_temp:
                channels_data.append(channel_map[ChannelType.COLOR_TEMPERATURE])
                min_kelvin, max_kelvin = _color_temperature_bounds(channel_map[ChannelType.COLOR_TEMPERATURE])

        elif has_single_white or has_dimmer:
            color_mode = ColorMode(ColorMode.BRIGHTNESS)

            if has_dimmer:
                has_separate_dimmer = True
                channels_data.append(channel_map[ChannelType.DIMMER])

            if has_single_white:
                channels_data.append(channel_map[ChannelType.WARM_WHITE])

        else:
            # No suitable channels for a light entity
            continue

        entities.append(
            DmxLightEntity(
                fixture_name=name,
                entity_id_prefix=entity_id_prefix,
                matrix_key=matrix_key,
                color_mode=color_mode,
                supported_color_modes=supported_color_modes,
                channels=channels_data,
                device=device,
                universe=universe,
                fixture_fingerprint=fixture_fingerprint,
                has_separate_dimmer=has_separate_dimmer,
                min_kelvin=min_kelvin,
                max_kelvin=max_kelvin,
            )
        )

    return entities


def create_entities(
    name: str,
    dmx_start: int,
    channels: list[ChannelOffset | SwitchingChannel | None],
    device: DeviceInfo,
    universe: DmxUniverse,
    entity_id_prefix: str | None = None,
    fixture_name: str | None = None,
    mode_name: str | None = None,
    output_correction: OutputCorrection | None = None,
) -> list[Entity]:
    entities: list[Entity] = []
    lights_accumulator: dict[str, list[ChannelMapping]] = {}

    fixture_fingerprint = generate_fixture_fingerprint(fixture_name or name, mode_name or "default", channels)

    channel_occurrences: dict[str, int] = {}

    for channel, group in _group_by_channel(__get_all_channels(list(enumerate(channels)))):
        # A mode may use the same channel in several slots, which are independent of each other.
        channel_occurrences[channel.name] = channel_occurrences.get(channel.name, 0) + 1
        occurrence = channel_occurrences[channel.name]
        channel_name = f"{channel.name} {occurrence}" if occurrence > 1 else channel.name

        dmx_indexes = []
        for channel_group in sorted(group, key=lambda g: g[1].byte_offset):
            dmx_indexes.append(channel_group[0] + dmx_start)

        if channel.constant:
            default_bytes = range_value_to_dmx_bytes(channel.default_value, len(dmx_indexes), channel.range_bytes)
            for dmx_index, default_byte in zip(dmx_indexes, default_bytes, strict=True):
                universe.set_constant_value([dmx_index], default_byte)

        if not channel.has_multiple_capabilities():
            capabilities = channel.capabilities
            single_capability = capabilities[0] if isinstance(capabilities, list) else capabilities
            if isinstance(single_capability, NoFunction) and not single_capability.is_dynamic_entity():
                continue

            entities.append(
                DmxNumberEntity(
                    name,
                    channel_name,
                    entity_id_prefix,
                    single_capability,
                    universe,
                    dmx_indexes,
                    device,
                    fixture_fingerprint,
                    output_correction=_correction_for_channel(channel, output_correction),
                )
            )
            __accumulate_light_entities(lights_accumulator, dmx_indexes, channel, output_correction)

        else:
            number_entities: dict[str, DmxNumberEntity] = {}
            slider_names: set[str] = set()
            for option, capability in capability_options(channel).items():
                if not capability.is_dynamic_entity():
                    continue

                # The first slider of a name keeps the plain name: its entity already exists under that unique ID.
                slider_name = option if str(capability) in slider_names else str(capability)
                slider_names.add(str(capability))
                number_entities[option] = DmxNumberEntity(
                    name,
                    f"{channel_name} {slider_name}",
                    entity_id_prefix,
                    capability,
                    universe,
                    dmx_indexes,
                    device,
                    fixture_fingerprint,
                    available=False,
                    owns_channel=False,
                )

            select_entity = DmxSelectEntity(
                name,
                channel_name,
                entity_id_prefix or "",
                channel,
                number_entities,
                universe,
                dmx_indexes,
                device,
                fixture_fingerprint,
            )

            entities.append(select_entity)
            entities.extend(number_entities.values())

    for entity in entities:
        if isinstance(entity, DmxSelectEntity):
            number_entities_only = [e for e in entities if isinstance(e, DmxNumberEntity)]
            entity.link_switching_entities(number_entities_only)

    entities.extend(
        __build_light_entities(name, entity_id_prefix, lights_accumulator, device, universe, fixture_fingerprint)
    )

    return entities
