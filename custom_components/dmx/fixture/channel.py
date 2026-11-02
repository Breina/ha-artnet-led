"""
One Channel maps to one DMX value.
"""

from dataclasses import dataclass

from custom_components.dmx.fixture.capability import Capability, DmxValueResolution

Capabilities = Capability | list[Capability]


def percent_to_dmx(value: str | int, resolution: DmxValueResolution) -> int:
    """
    Converts a percent string ("75%") or raw integer to a DMX value scaled to
    the given resolution (8-bit → 0-255, 16-bit → 0-65535, 24-bit → 0-16777215).
    Raw integers are passed through unchanged (assumed already in range).
    """
    if isinstance(value, str):
        assert value[-1] == "%"
        max_val = (256**resolution.value) - 1
        return round(int(value[:-1]) * max_val / 100)
    return value


def dmx_bytes_to_range_value(values: list[int], range_bytes: int) -> int:
    """
    Combines the bytes of a channel into a value comparable to its capabilities' dmxRange.
    A mode doesn't have to use all fine channels, so the bytes may be fewer or more than the range's resolution.
    :param values: The DMX values, coarse to fine
    :param range_bytes: The bytes in which the channel's dmxRange is expressed
    """
    combined = int.from_bytes(bytes(values), "big")
    extra_bytes = len(values) - range_bytes
    return combined >> (8 * extra_bytes) if extra_bytes > 0 else combined << (-8 * extra_bytes)


def range_value_to_dmx_bytes(value: int, num_bytes: int, range_bytes: int) -> list[int]:
    """
    Splits a value expressed like a capability's dmxRange into the bytes a mode has for it.
    With too few bytes it rounds up, as a capability's start must not end up in the capability before it.
    :param value: The value, in the resolution of the range
    :param num_bytes: The amount of bytes to split it in
    :param range_bytes: The bytes in which the channel's dmxRange is expressed
    """
    extra_bytes = num_bytes - range_bytes
    if extra_bytes >= 0:
        combined = value << (8 * extra_bytes)
    else:
        lost_bits = -8 * extra_bytes
        combined = min((value + (1 << lost_bits) - 1) >> lost_bits, (256**num_bytes) - 1)
    return list(combined.to_bytes(num_bytes, "big"))


class Channel:
    """
    One DMX channel.
    """

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        name: str,
        fine_channel_aliases: list[str] | None,
        dmx_value_resolution: DmxValueResolution,
        default_value: int | str | None = None,
        highlight_value: int | str | None = None,
        constant: bool = False,
    ) -> None:
        self.name: str = name
        self.matrix_key: str | None = None  # Used to identify channels part of a templated matrix

        if fine_channel_aliases is None:
            fine_channel_aliases = []
        self.fine_channel_aliases: list[str] = fine_channel_aliases

        self.dmx_value_resolution: DmxValueResolution = dmx_value_resolution

        self.default_value: int = percent_to_dmx(default_value, dmx_value_resolution) if default_value else 0

        self.highlight_value: int = (
            (256**dmx_value_resolution.value) - 1
            if not highlight_value
            else percent_to_dmx(highlight_value, dmx_value_resolution)
        )

        self.constant: bool = constant

        self.capabilities: Capabilities = []

        # The bytes in which the capabilities' dmxRange is expressed.
        self.range_bytes: int = 1

    def define_capability(self, capability: Capabilities) -> None:
        """
        Defines capabilities, add it to this channel.
        :param capability: The capabilities to define.
        """
        if isinstance(capability, list):
            self.capabilities = capability
        else:
            self.capabilities = [capability]

        highest_value = max((c.dmx_range_end for c in self.capabilities), default=0)
        self.range_bytes = 3 if highest_value > 0xFFFF else 2 if highest_value > 0xFF else 1
        for defined_capability in self.capabilities:
            for dynamic_entity in defined_capability.dynamic_entities:
                dynamic_entity.range_bytes = self.range_bytes

    def has_multiple_capabilities(self) -> bool:
        return isinstance(self.capabilities, list) and len(self.capabilities) > 1

    def __str__(self) -> str:
        return f"{self.name}: {self.capabilities}"

    def __repr__(self) -> str:
        return self.name


@dataclass
class ChannelOffset:
    """
    A channel, combined with its offset for fine channels.
    Offset starts at 0 and increments per fine channel.
    """

    channel: Channel
    byte_offset: int

    def __repr__(self) -> str:
        return f"{self.channel.__repr__()}#{self.byte_offset}"


@dataclass
class SwitchingChannel:
    """
    A switching channel, which can forward itself to multiple other channels.
    """

    name: str
    controlled_channels: dict[str, ChannelOffset]

    def __repr__(self) -> str:
        return f"{self.name}{self.controlled_channels}"
