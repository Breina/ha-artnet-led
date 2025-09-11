"""
The parser is responsible for taking in the fixture format's JSON and creating
convenient model classes from it.

Many model classes, arguments and enum names match the fixture format exactly,
and are instantiated by `typing` trickery, instead of appearing in code.

As it's a parser, we don't care too much about pylint and will be ignoring some.
"""

# pylint: disable=too-many-locals, too-many-branches

import inspect
import json
import logging
import re
import typing
from enum import EnumType
from types import MappingProxyType, UnionType
from typing import Union

from custom_components.dmx.fixture import OFL_URL, capability, wheel
from custom_components.dmx.fixture.capability import Capability, MenuClick
from custom_components.dmx.fixture.channel import Channel, DmxValueResolution
from custom_components.dmx.fixture.entity import Entity
from custom_components.dmx.fixture.exceptions import FixtureConfigurationError
from custom_components.dmx.fixture.fixture import Fixture
from custom_components.dmx.fixture.matrix import matrix_from_pixel_count, matrix_from_pixel_names
from custom_components.dmx.fixture.mode import ChannelOrder, MatrixChannelInsertBlock, Mode, RepeatFor
from custom_components.dmx.fixture.wheel import Wheel, WheelSlot

underscore_pattern = re.compile(r"(?<!^)(?=[A-Z])")
entity_value = re.compile(r"([-\d.]*)(.*)")

log = logging.getLogger(__name__)


def _read_json_file(json_file: str) -> dict:
    """Helper function to read JSON file synchronously."""
    with open(json_file, encoding="utf-8") as json_data:
        return json.load(json_data)


def _parse_fixture_data(data: dict) -> Fixture:
    """
    Internal function to parse fixture data from a dictionary.
    :param data: The parsed JSON data
    :return: The `Fixture` model class.
    """
    fixture_model = __parse_fixture(data)

    matrix_json = data.get("matrix")
    if matrix_json:
        __parse_matrix(fixture_model, matrix_json)

    wheels_json = data.get("wheels")
    if wheels_json:
        __parse_wheels(fixture_model, wheels_json)

    available_channels_json = data.get("availableChannels")
    available_template_channels_json = data.get("templateChannels")

    assert available_channels_json or available_template_channels_json

    if available_channels_json:
        __parse_channels(available_channels_json, fixture_model.define_channel, fixture_model.config_url)

    if available_template_channels_json:
        __parse_channels(
            available_template_channels_json, fixture_model.define_template_channel, fixture_model.config_url
        )

    fixture_model.resolve_channels()

    __parse_modes(fixture_model, data["modes"])

    return fixture_model


async def parse_async(json_file: str, hass) -> Fixture:
    """
    Parses the json fixture-format file asynchronously.
    :param json_file: The fixture-format json file
    :param hass: Home Assistant instance for executor job
    :return: The `Fixture` model class.
    """
    data = await hass.async_add_executor_job(_read_json_file, json_file)
    return _parse_fixture_data(data)


def parse(json_file: str) -> Fixture:
    """
    Parses the json fixture-format file synchronously (for tests only).
    :param json_file: The fixture-format json file
    :return: The `Fixture` model class.
    """
    data = _read_json_file(json_file)
    return _parse_fixture_data(data)


def __parse_fixture(fixture_json: dict) -> Fixture:
    name = fixture_json["name"]
    short_name = fixture_json.get("shortName", name)
    categories = fixture_json["categories"]

    fixture_key = fixture_json.get("fixtureKey")
    manufacturer_key = fixture_json.get("manufacturerKey")

    help_wanted = fixture_json.get("helpWanted")
    config_url = f"{OFL_URL}/{manufacturer_key}/{fixture_key}" if fixture_key and manufacturer_key else None

    if help_wanted:
        if config_url:
            log.warning(
                "HELP WANTED: Looks like the fixture over at %s/%s/%s could use some love: %s.",
                OFL_URL,
                manufacturer_key,
                fixture_key,
                help_wanted,
            )
        else:
            log.warning("HELP WANTED: Looks like the fixture %s could use some love: %s", name, help_wanted)

    return Fixture(name, short_name, categories, config_url)


def __parse_matrix(fixture_model: Fixture, matrix_json: dict):
    pixel_count_json = matrix_json.get("pixelCount")
    pixel_keys_json = matrix_json.get("pixelKeys")
    if pixel_count_json:
        matrix = matrix_from_pixel_count(pixel_count_json[0], pixel_count_json[1], pixel_count_json[2])
    elif pixel_keys_json:
        matrix = matrix_from_pixel_names(pixel_keys_json)
    else:
        raise FixtureConfigurationError("Matrix definition must have either `pixelCount` or `pixelKeys`.")

    pixel_groups_json = matrix_json.get("pixelGroups")
    if pixel_groups_json:
        for name, pixel_group_ref in pixel_groups_json.items():
            matrix.define_group(name, pixel_group_ref)

    fixture_model.define_matrix(matrix)


def __parse_wheels(fixture_model: Fixture, wheels_json: dict):
    for wheel_name, wheel_json in wheels_json.items():
        slots: list[WheelSlot] = []
        direction = wheel_json.get("direction")

        for wheel_slot_json in wheel_json["slots"]:
            slot_type = wheel_slot_json["type"]

            # This is directly mapped to the class names inside wheel.py.
            slot_obj = getattr(wheel, slot_type)

            params = inspect.signature(slot_obj.__init__).parameters
            param_names = [name[0] for name in params.items() if name[0] != "self" and name[0] != "kwargs"]

            args = [None] * len(param_names)

            for key, value_json in wheel_slot_json.items():
                if key in ["type"]:
                    continue

                # Spec is defined in camelCase, but Python likes parameters in snake_case.
                arg_name = underscore_pattern.sub("_", key).lower()

                if arg_name in params:
                    value = __extract_value_type(arg_name, value_json, False, params)
                    args[list.index(param_names, arg_name)] = value

                else:
                    raise FixtureConfigurationError(
                        f"For wheel {wheel_name}, " f"I don't know what kind of argument this is: " f"{arg_name}"
                    )

            slot = slot_obj(*args)
            slots.append(slot)

        fixture_model.define_wheel(Wheel(wheel_name, slots, direction))


def __parse_channels(
    available_channels_json: dict, add_channel: typing.Callable[[Channel], None], config_url: str | None
):
    # pylint: disable=protected-access
    for name, channel_json in available_channels_json.items():
        dmx_value_resolution_str = channel_json.get("dmxValueResolution")
        if dmx_value_resolution_str:
            try:
                dmx_value_resolution = next(
                    dvr for dvr in DmxValueResolution if dvr.name.endswith(dmx_value_resolution_str.upper())
                )
            except StopIteration:
                raise FixtureConfigurationError(
                    f"Invalid dmxValueResolution '{dmx_value_resolution_str}'. "
                    "Must be one of: 8bit, 16bit, 24bit"
                ) from None
        else:
            # Underscore is because we can't start with a number, not because we want to protect it.
            # noinspection PyProtectedMember
            dmx_value_resolution = DmxValueResolution._8BIT

        channel = Channel(
            name,
            channel_json.get("fineChannelAliases", []),
            dmx_value_resolution,
            channel_json.get("defaultValue"),
            channel_json.get("highlightValue"),
            channel_json.get("constant"),
        )

        capability_json = channel_json.get("capability")
        if capability_json:
            channel_json = __parse_capability(channel, capability_json, config_url)
            if channel_json:
                channel.define_capability(channel_json)
            add_channel(channel)
            continue

        capabilities_json = channel_json.get("capabilities")
        if capabilities_json:
            channel_buffer = []
            for capability_json in capabilities_json:
                channel_json = __parse_capability(channel, capability_json, config_url)
                if channel_json and channel_json.menu_click != MenuClick.hidden:
                    channel_buffer.append(channel_json)
            channel.define_capability(channel_buffer)
            add_channel(channel)
            continue


def __parse_capability(channel: Channel, capability_json: dict, config_url: str | None) -> Capability | None:
    capability_type = capability_json["type"]

    # This is directly mapped to the class names inside capability.py.
    capability_obj = getattr(capability, capability_type)

    params = inspect.signature(capability_obj.__init__).parameters
    param_names = [name[0] for name in params.items() if name[0] != "self" and name[0] != "kwargs"]
    parent_params = inspect.signature(Capability.__init__).parameters

    args = [None] * len(param_names)
    kwargs = {}
    kwargs["dmx_value_resolution"] = channel.dmx_value_resolution

    if "name" in param_names:
        # noinspection PyTypeChecker
        args[list.index(param_names, "name")] = channel.name

    start_end_registry = {}

    for key, value_json in capability_json.items():
        if key == "helpWanted":
            if config_url:
                log.warning(
                    "HELP WANTED: Channel '%s' of fixture over at %s could use some love: %s",
                    channel.name,
                    config_url,
                    value_json,
                )
            else:
                log.warning("HELP WANTED: Channel '%s' could use some love: %s", channel.name, value_json)
            continue

        if key in ["type"]:
            continue

        # Spec is defined in camelCase, but Python likes parameters in snake_case.
        arg_name = underscore_pattern.sub("_", key).lower()

        # Bundle the _start and _end capabilities into a list.
        # This reduces the amount of variables we have to write in capabilities.py.
        is_combined = False
        is_start = arg_name.endswith("_start")
        if is_start or arg_name.endswith("_end"):
            shorthand = arg_name[0 : arg_name.rfind("_")]
            value_container = start_end_registry.get(shorthand, [None, None])
            if is_start:
                value_container[0] = value_json
            else:
                value_container[1] = value_json

            if None in value_container:
                start_end_registry[shorthand] = value_container
                continue

            start_end_registry.pop(shorthand)
            value_json = value_container
            arg_name = shorthand
            is_combined = True

        if arg_name in params:
            value = __extract_value_type(arg_name, value_json, is_combined, params)
            args[list.index(param_names, arg_name)] = value

        elif arg_name in parent_params:
            value = __extract_value_type(arg_name, value_json, is_combined, parent_params)
            kwargs[arg_name] = value

        else:
            raise FixtureConfigurationError(
                f"For channel {channel.name}, " f"I don't know what kind of argument this is: {arg_name}"
            )

    return capability_obj(*args, **kwargs)


def __extract_value_type(name: str, value_json, is_combined: bool, params: MappingProxyType[str, inspect.Parameter]):
    param = params[name]
    type_annotation = param.annotation

    should_wrap = False

    # Unwrap if type is typing.Optional
    if (typing.get_origin(type_annotation) is Union or typing.get_origin(type_annotation) is UnionType) and type(
        None
    ) in typing.get_args(type_annotation):
        type_annotation = type_annotation.__args__[0]

    # Unwrap if type is a list and indicate to wrap the value if it's not already
    if typing.get_origin(type_annotation) is list:
        type_annotation = type_annotation.__args__[0]
        should_wrap = not is_combined

    if isinstance(value_json, list):
        # If type is List[List[str]], then unwrap the second time
        if typing.get_origin(type_annotation) is list:
            type_annotation = type_annotation.__args__[0]

        value = [__extract_single_value(val, type_annotation) for val in value_json]
    else:
        value = __extract_single_value(value_json, type_annotation)

    return [value] if should_wrap else value


def __extract_single_value(value_json: str, type_annotation: type):
    if inspect.isclass(type_annotation) and issubclass(type_annotation, Entity):
        if isinstance(value_json, (int, float)):
            return type_annotation(value_json)

        value_parts = entity_value.findall(value_json)[0]
        value = value_parts[0]
        if not value:
            value = value_parts[1]
            unit = None
        else:
            value = float(value)
            unit = value_parts[1] or None

        return type_annotation(value, unit)

    if not isinstance(value_json, str):
        return value_json

    if issubclass(type_annotation, str):
        return value_json

    if isinstance(type_annotation, EnumType):
        # Python enums can't have spaces
        enum_name = value_json.replace(" ", "")
        # Python enums can't start with a number
        if value_json[0].isdigit():
            enum_name = f"_{enum_name}"
        return type_annotation[enum_name]

    if issubclass(type_annotation, bool):
        return bool(value_json)

    raise FixtureConfigurationError(f"I don't know what kind of type this is: {type_annotation}")


def __parse_modes(fixture_model: Fixture, modes_yaml: dict):
    for mode_yaml in modes_yaml:
        name = mode_yaml["name"]
        short_name = mode_yaml.get("shortName")
        channels = mode_yaml["channels"]

        channels = list(map(__parse_mode_channel, channels))

        mode = Mode(name, channels, short_name)
        fixture_model.define_mode(mode)


def __parse_mode_channel(mode_channel: None | str | dict) -> None | str | MatrixChannelInsertBlock:
    if mode_channel is None or isinstance(mode_channel, str):
        return mode_channel

    insert = mode_channel["insert"]
    if insert != "matrixChannels":
        raise FixtureConfigurationError(f"Unknown insert mode: {insert}")

    repeat_for_json = mode_channel["repeatFor"]

    # It's either a string enum or a list of strings
    repeat_for = RepeatFor[repeat_for_json] if isinstance(repeat_for_json, str) else repeat_for_json

    channel_order = ChannelOrder[mode_channel["channelOrder"]]
    template_channels = mode_channel["templateChannels"]
    return MatrixChannelInsertBlock(repeat_for, channel_order, template_channels)
