"""
One Channel maps to one DMX value.
"""

import math
from dataclasses import dataclass

from custom_components.dmx.fixture.capability import Capability, \
    DmxValueResolution

Capabilities = Capability | list[Capability]


def percent_to_byte(default_value: str | int):
    """
    Converts a percent string (75%) into a byte (196).
    :param default_value: If a string, converts it into byte. Otherwise pass
                          through the number.
    :return: The converted byte.
    """
    if isinstance(default_value, str):
        assert default_value[-1] == '%'
        return int(2.55 * int(default_value[:-1]))
    return default_value


class Channel:
    """
    One DMX channel.
    """

    # pylint: disable=too-many-arguments
    def __init__(self, name: str,
                 fine_channel_aliases: [str],
                 dmx_value_resolution: DmxValueResolution,
                 default_value: int | str | None = None,
                 highlight_value: int | str | None = None,
                 constant: bool = False
                 ):
        self.name = name
        self.matrix_key = None  # Used to identify channels part of a templated matrix

        if fine_channel_aliases is None:
            fine_channel_aliases = []
        self.fine_channel_aliases = fine_channel_aliases

        self.dmx_value_resolution = dmx_value_resolution

        if default_value:
            self.default_value = percent_to_byte(default_value)
        else:
            self.default_value = 0

        if not highlight_value:
            self.highlight_value = math.pow(255, dmx_value_resolution.value)
        else:
            self.highlight_value = percent_to_byte(highlight_value)

        # TODO use this somewhere?
        self.constant = constant

        self.capabilities: Capabilities = []

    def define_capability(self, capability: Capabilities) -> None:
        """
        Defines capabilities, add it to this channel.
        :param capability: The capabilities to define.
        """
        if isinstance(capability, list):
            self.capabilities = capability
        else:
            self.capabilities = [capability]

    def has_multiple_capabilities(self) -> bool:
        return len(self.capabilities) > 1

    def __str__(self):
        return f"{self.name}: {self.capabilities}"

    def __repr__(self):
        return self.name


@dataclass
class ChannelOffset:
    """
    A channel, combined with its offset for fine channels.
    Offset starts at 0 and increments per fine channel.
    """

    channel: Channel
    byte_offset: int

    def __repr__(self):
        return f"{self.channel.__repr__()}#{self.byte_offset}"


@dataclass
class SwitchingChannel:
    """
    A switching channel, which can forward itself to multiple other channels.
    """
    name: str
    controlled_channels: dict[str, ChannelOffset]

    def __repr__(self):
        return f"{self.name}{self.controlled_channels}"