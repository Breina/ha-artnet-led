import inspect
import json
import os
import re
import typing
from enum import EnumType
from types import MappingProxyType, UnionType
from typing import Union

from homeassistant.exceptions import IntegrationError

import capability
from custom_components.dmx.fixture.capability import Capability, MenuClick
from custom_components.dmx.fixture.entity import Entity

underscore_pattern = re.compile(r"(?<!^)(?=[A-Z])")
entity_value = re.compile(f"([-\d.]*)(.*)")


class FixtureConfigurationError(IntegrationError):
    def __init__(self, msg: str, *args):
        super().__init__(*args)
        self.msg = msg

    def __str__(self) -> str:
        return self.msg


def parse(json_file: str):
    with open(json_file, encoding='utf-8') as json_data:
        data = json.load(json_data)

    channels = {}
    for name, channel in data["availableChannels"].items():
        capability_yaml = channel.get("capability")
        if capability_yaml:
            channel = parse_capability(name, capability_yaml)
            if channel:
                channels[name] = channel
            continue

        capabilities_yaml = channel.get("capabilities")
        if capabilities_yaml:
            channel_buffer = []
            for capability_yaml in capabilities_yaml:
                channel = parse_capability(name, capability_yaml)
                if channel and channel.menu_click != MenuClick.hidden:
                    channel_buffer.append(channel)
            channels[name] = channel_buffer
            continue

    return channels


def parse_capability(name: str, capability_yaml: dict) -> Capability | None:
    capability_type = capability_yaml["type"]
    if capability_type == "NoFunction":
        return None

    # This is directly mapped to the class names inside capability.py.
    capability_obj = getattr(capability, capability_type)

    params = inspect.signature(capability_obj.__init__).parameters
    param_names = [name[0] for name in params.items() if name[0] != "self" and name[0] != "kwargs"]
    parent_params = inspect.signature(Capability.__init__).parameters

    args = [None] * len(param_names)
    kwargs = {}

    # noinspection PyTypeChecker
    if "name" in param_names:
        args[list.index(param_names, "name")] = name

    startEndRegistry = {}

    for key, value_yaml in capability_yaml.items():
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
                value_container[0] = value_yaml
            else:
                value_container[1] = value_yaml

            if None in value_container:
                startEndRegistry[shorthand] = value_container
                continue
            else:
                startEndRegistry.pop(shorthand)
                value_yaml = value_container
                arg_name = shorthand
                is_combined = True

        if arg_name in params:
            value = extract_value_type(arg_name, value_yaml, is_combined, params)
            args[list.index(param_names, arg_name)] = value

        elif arg_name in parent_params:
            value = extract_value_type(arg_name, value_yaml, is_combined, parent_params)
            kwargs[arg_name] = value

        else:
            raise FixtureConfigurationError(f"I don't know what kind of argument this is: {arg_name}")

    return capability_obj(*args, **kwargs)


def extract_value_type(name: str, value_yaml, is_combined: bool, params: MappingProxyType[str, inspect.Parameter]):
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

    if isinstance(value_yaml, list):
        # If type is List[List[str]], then unwrap the second time
        if typing.get_origin(type_annotation) == list:
            type_annotation = type_annotation.__args__[0]

        value = list(map(lambda val: extract_single_value(val, type_annotation), value_yaml))
    else:
        value = extract_single_value(value_yaml, type_annotation)

    return [value] if should_wrap else value


def extract_single_value(value_yaml: str, type_annotation: type):
    if inspect.isclass(type_annotation) and issubclass(type_annotation, Entity):
        if isinstance(value_yaml, int) or isinstance(value_yaml, float):
            return type_annotation(value_yaml)

        value_parts = entity_value.findall(value_yaml)[0]
        value = value_parts[0]
        if not value:
            value = value_parts[1]
            unit = None
        else:
            value = float(value)
            unit = value_parts[1] or None

        return type_annotation(value, unit)

    if not isinstance(value_yaml, str):
        return value_yaml

    if issubclass(type_annotation, str):
        return value_yaml

    if isinstance(type_annotation, EnumType):
        return type_annotation[value_yaml.replace(" ", "")]

    if issubclass(type_annotation, bool):
        return bool(value_yaml)

    raise FixtureConfigurationError(f"I don't know what kind of type this is: {type_annotation}")

dir = "F:/Projects/Home/open-fixture-library/fixtures/"
for brand in os.listdir(dir):
    if brand.endswith("json"):
        continue
    # print(brand)
    for file in os.listdir(dir + brand):
        # print(f"  {file}")
        try:
            capabilities = parse(dir + brand + "/" + file)
            # print(f"  {capabilities}")
        except Exception as e:
            print(f"{file}: {e}")


# capabilities = parse("../../../staging/fixtures/spica-250m.json")
# print(capabilities)