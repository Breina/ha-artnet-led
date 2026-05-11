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
        max_val = (256 ** resolution.value) - 1
        return round(int(value[:-1]) * max_val / 100)
    return value


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
            (256 ** dmx_value_resolution.value) - 1
            if not highlight_value
            else percent_to_dmx(highlight_value, dmx_value_resolution)
        )

        self.constant: bool = constant

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
