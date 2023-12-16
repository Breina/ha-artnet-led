import inspect
import json
import os
import re
import typing
from enum import EnumType
from types import MappingProxyType, UnionType
from typing import Union

import capability
from custom_components.dmx.fixture.capability import Capability, MenuClick
from custom_components.dmx.fixture.entity import Entity
from custom_components.dmx.fixture.exceptions import FixtureConfigurationError
from custom_components.dmx.fixture.fixture import Fixture
from custom_components.dmx.fixture.matrix import matrix_from_pixel_count, matrix_from_pixel_names, Matrix

underscore_pattern = re.compile(r"(?<!^)(?=[A-Z])")
entity_value = re.compile(f"([-\d.]*)(.*)")


def parse(json_file: str) -> Fixture:
    with open(json_file, encoding='utf-8') as json_data:
        data = json.load(json_data)

    matrix_json = data.get("matrix")
    matrix = parse_matrix(matrix_json) if matrix_json else None

    channels = {}
    for name, channel in data.get("availableChannels", {}).items():
        capability_json = channel.get("capability")
        if capability_json:
            channel = parse_capability(name, capability_json)
            if channel:
                channels[name] = channel
            continue

        capabilities_json = channel.get("capabilities")
        if capabilities_json:
            channel_buffer = []
            for capability_json in capabilities_json:
                channel = parse_capability(name, capability_json)
                if channel and channel.menuClick != MenuClick.hidden:
                    channel_buffer.append(channel)
            channels[name] = channel_buffer
            continue

    return Fixture(channels, matrix)


def parse_matrix(matrix_json: dict) -> Matrix:
    pixel_count_json = matrix_json.get('pixelCount')
    pixel_keys_json = matrix_json.get("pixelKeys")
    if pixel_count_json:
        matrix = matrix_from_pixel_count(pixel_count_json[0], pixel_count_json[1], pixel_count_json[2])
    elif pixel_keys_json:
        matrix = matrix_from_pixel_names(pixel_keys_json)
    else:
        raise FixtureConfigurationError(f"Matrix definition must have either `pixelCount` or `pixelKeys`.")

    pixel_groups_json = matrix_json.get('pixelGroups')
    if pixel_groups_json:
        for name, pixel_group_ref in pixel_groups_json.items():
            matrix.create_group(name, pixel_group_ref)

    return matrix


def parse_capability(name: str, capability_json: dict) -> Capability | None:
    capability_type = capability_json["type"]
    if capability_type == "NoFunction":
        return None

    # This is directly mapped to the class names inside capability.py.
    capability_obj = getattr(capability, capability_type)

    params = inspect.signature(capability_obj.__init__).parameters
    param_names = [name[0] for name in params.items() if name[0] != "self" and name[0] != "kwargs"]
    parent_params = inspect.signature(Capability.__init__).parameters

    args = [None] * len(param_names)
    kwargs = {}

    if "name" in param_names:
        # noinspection PyTypeChecker
        args[list.index(param_names, "name")] = name

    startEndRegistry = {}

    for key, value_json in capability_json.items():
        # TODO switchChannels
        if key in ["type", "helpWanted", "switchChannels"]:
            continue

        # Spec is defined in camelCase, but Python likes parameters in snake_case.
        arg_name = underscore_pattern.sub('_', key).lower()

        # Bundle the _start and _end capabilities into a list.
        # This reduces the amount of variables we have to write in capabilities.py.
        is_combined = False
        isStart = arg_name.endswith("_start")
        if isStart or arg_name.endswith("_end"):
            shorthand = arg_name[0:arg_name.rfind("_")]
            value_container = startEndRegistry.get(shorthand, [None, None])
            if isStart:
                value_container[0] = value_json
            else:
                value_container[1] = value_json

            if None in value_container:
                startEndRegistry[shorthand] = value_container
                continue
            else:
                startEndRegistry.pop(shorthand)
                value_json = value_container
                arg_name = shorthand
                is_combined = True

        if arg_name in params:
            value = extract_value_type(arg_name, value_json, is_combined, params)
            args[list.index(param_names, arg_name)] = value

        elif arg_name in parent_params:
            value = extract_value_type(arg_name, value_json, is_combined, parent_params)
            kwargs[arg_name] = value

        else:
            raise FixtureConfigurationError(f"I don't know what kind of argument this is: {arg_name}")

    return capability_obj(*args, **kwargs)


def extract_value_type(name: str, value_json, is_combined: bool, params: MappingProxyType[str, inspect.Parameter]):
    param = params[name]
    type_annotation = param.annotation

    should_wrap = False

    # Unwrap if type is typing.Optional
    if ((typing.get_origin(type_annotation) is Union or typing.get_origin(type_annotation) is UnionType)
            and type(None) in typing.get_args(type_annotation)):
        type_annotation = type_annotation.__args__[0]

    # Unwrap if type is a list and indicate to wrap the value if it's not already
    if typing.get_origin(type_annotation) == list:
        type_annotation = type_annotation.__args__[0]
        should_wrap = not is_combined

    if isinstance(value_json, list):
        # If type is List[List[str]], then unwrap the second time
        if typing.get_origin(type_annotation) == list:
            type_annotation = type_annotation.__args__[0]

        value = list(map(lambda val: extract_single_value(val, type_annotation), value_json))
    else:
        value = extract_single_value(value_json, type_annotation)

    return [value] if should_wrap else value


def extract_single_value(value_json: str, type_annotation: type):
    if inspect.isclass(type_annotation) and issubclass(type_annotation, Entity):
        if isinstance(value_json, int) or isinstance(value_json, float):
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
        enumName = value_json.replace(" ", "")
        # Python enums can't start with a number
        if value_json[0].isdigit():
            enumName = f"_{enumName}"
        return type_annotation[enumName]

    if issubclass(type_annotation, bool):
        return bool(value_json)

    raise FixtureConfigurationError(f"I don't know what kind of type this is: {type_annotation}")


dir = "F:/Projects/Home/open-fixture-library/fixtures/"
for brand in os.listdir(dir):
    if brand.endswith("json"):
        continue
    print(brand)
    for file in os.listdir(dir + brand):
        print(f"  {file}")
        try:
            fixture = parse(dir + brand + "/" + file)
        except Exception as e:
            print(f"{file}: {e}")

# capabilities = parse("F:/Projects/Home/open-fixture-library/fixtures/chroma-q/color-force-ii-48.json")
# capabilities = parse("../../../staging/fixtures/dj_scan_led.json")
# capabilities = parse("../../../staging/fixtures/l10-c.json")
# print(capabilities)
