from custom_components.dmx.fixture.capability import Capability
from custom_components.dmx.fixture.matrix import Matrix
from custom_components.dmx.fixture.mode import Mode
from custom_components.dmx.fixture.wheel import Wheel

Capabilities = Capability | list[Capability]


class FineChannelAlias:
    def __init__(self, channel_name: str, channel: Capabilities, channel_alias_index: int):
        self.channel_name = channel_name
        self.channel = channel
        self.channel_alias_index = channel_alias_index


FineChannelAliases = FineChannelAlias | list[FineChannelAlias]


class Fixture:
    def __init__(self, name: str, short_name: str, categories: list[str], config_url: str | None):
        self.name = name
        self.shortName = short_name or name

        assert categories
        self.categories = categories

        self.configUrl = config_url

        self.capabilities: dict[str, Capabilities | FineChannelAliases] = {}
        self.templateChannels: dict[str, Capability | list[Capability]] = {}

        self.matrix: Matrix | None = None
        self.wheels: dict[str, Wheel] = {}

        self.modes: dict[str, Mode] = {}

    def define_capability(self, name: str, capability: Capabilities):
        self.capabilities[name] = capability

        channel_alias_index = 1
        for fineChannelAlias in capability.fineChannelAliases:
            self.capabilities[fineChannelAlias] = FineChannelAlias(name, capability, channel_alias_index)
            channel_alias_index += 1

    def define_template_channel(self, name: str, capability: Capabilities):
        assert "$pixelKey" in name
        self.templateChannels[name] = capability

    def define_matrix(self, matrix: Matrix):
        self.matrix = matrix

    def define_wheel(self, wheel: Wheel):
        self.wheels[wheel.name] = wheel

    def define_mode(self, mode: Mode):
        self.modes[mode.name] = mode

    def __str__(self):
        return f"{self.name} ({self.shortName})"
