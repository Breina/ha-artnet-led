import math

from custom_components.dmx.fixture.capability import Capability, DmxValueResolution

Capabilities = Capability | list[Capability]


def percent_to_byte(default_value: str | int):
    if type(default_value) is str:
        assert default_value[-1] == '%'
        return int(2.55 * int(default_value[:-1]))
    return default_value


class Channel:
    def __init__(self, name: str,
                 fine_channel_aliases: [str],
                 dmx_value_resolution: DmxValueResolution,
                 default_value: int | str | None = None,
                 highlight_value: int | str | None = None,
                 constant: bool = False
                 ):
        self.name = name

        if fine_channel_aliases is None:
            fine_channel_aliases = []
        self.fineChannelAliases = fine_channel_aliases

        self.dmxValueResolution = dmx_value_resolution

        if default_value:
            self.defaultValue = percent_to_byte(default_value)
        else:
            self.defaultValue = 0

        if not highlight_value:
            self.highlightValue = math.pow(255, dmx_value_resolution.value)
        else:
            self.highlightValue = percent_to_byte(highlight_value)

        self.constant = constant

        self.capabilities: Capabilities = []

    def define_capability(self, capability: Capabilities):
        if isinstance(capability, list):
            self.capabilities = capability
        else:
            self.capabilities = [capability]

    def __str__(self):
        return f"{self.name}: {self.capabilities}"

    def __repr__(self):
        return self.name


class ChannelOffset:
    def __init__(self, channel: Channel, byte_offset: int):
        super().__init__()
        self.channel = channel
        self.byte_offset = byte_offset

    def __repr__(self):
        return f"{self.channel.__repr__()}#{self.byte_offset}"


class SwitchingChannel:
    def __init__(self, name: str, channel_offsets: list[ChannelOffset]):
        self.name = name
        self.channels = {channel_offset.channel.name: channel_offset for channel_offset in channel_offsets}

    def __repr__(self):
        return f"{self.name}{self.channels}"
