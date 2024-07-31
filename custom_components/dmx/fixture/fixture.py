from copy import deepcopy

from custom_components.dmx.fixture.channel import Channel, ChannelOffset, SwitchingChannel
from custom_components.dmx.fixture.exceptions import FixtureConfigurationError
from custom_components.dmx.fixture.matrix import Matrix, Pixel
from custom_components.dmx.fixture.mode import Mode, MatrixChannelInsertBlock, ChannelOrder, RepeatFor
from custom_components.dmx.fixture.wheel import Wheel


class Fixture:
    def __init__(self, name: str, short_name: str, categories: list[str], config_url: str | None):
        self.name = name
        self.shortName = short_name or name

        assert categories
        self.categories = categories

        self.configUrl = config_url

        self.channels: dict[str, ChannelOffset] = {}
        self.templateChannels: dict[str, ChannelOffset] = {}

        self.switchingChannelNames: dict[str, set[str]] = {}
        self.templateSwitchingChannelNames: dict[str, set[str]] = {}

        self.switchingChannels: dict[str, SwitchingChannel] = {}
        self.templateSwitchingChannels: dict[str, SwitchingChannel] = {}

        self.matrix: Matrix | None = None
        self.wheels: dict[str, Wheel] = {}

        self.modes: dict[str, Mode] = {}

    def define_channel(self, channel: Channel):
        self.__define_channel_with_aliases(channel, self.channels, self.switchingChannelNames)

    def define_template_channel(self, channel: Channel):
        self.__define_channel_with_aliases(channel, self.templateChannels, self.templateSwitchingChannelNames)

    @staticmethod
    def __define_channel_with_aliases(channel: Channel, dest: dict[str, ChannelOffset],
                                      switching_dest: dict[str, set[str]]):
        dest[channel.name] = ChannelOffset(channel, 0)
        for byte_offset, fineChannelAlias in enumerate(channel.fineChannelAliases, start=1):
            dest[fineChannelAlias] = ChannelOffset(channel, byte_offset)

        for capability in channel.capabilities:
            for switchChannelKey, switchChannelValue in capability.switchChannels.items():
                if switchChannelKey not in switching_dest:
                    switching_dest[switchChannelKey] = set()
                switching_dest[switchChannelKey].add(switchChannelValue)

    def define_matrix(self, matrix: Matrix):
        self.matrix = matrix

    def define_wheel(self, wheel: Wheel):
        self.wheels[wheel.name] = wheel

    def define_mode(self, mode: Mode):
        self.modes[mode.name] = mode

    def resolve_channels(self):
        self.__resolve_switching_channels(
            self.templateSwitchingChannelNames, self.templateChannels, self.templateSwitchingChannels
        )

        if self.matrix:
            self.__resolve_matrix()

        self.__resolve_switching_channels(self.switchingChannelNames, self.channels, self.switchingChannels)

        del self.switchingChannelNames
        del self.templateSwitchingChannelNames

    def __resolve_matrix(self):
        for name in list(self.matrix.pixelsByName.keys()) + list(self.matrix.pixelGroups.keys()):
            for templateChannel in self.templateChannels.values():
                self.define_channel(self.__renamed_copy(templateChannel, name).channel)

            for templateSwitchingChannel in self.templateSwitchingChannels.values():
                channels = [self.__renamed_copy(channel, name) for channel in templateSwitchingChannel.channels]
                switchingChannel = SwitchingChannel(
                    templateSwitchingChannel.name.replace("$pixelKey", name), channels
                )
                self.switchingChannels[switchingChannel.name] = switchingChannel

    @staticmethod
    def __resolve_switching_channels(switching_channel_names: dict[str, set[str]],
                                     channels: dict[str, ChannelOffset], dest: dict[str, SwitchingChannel]):

        for switchingChannelName, switchedChannelNames in switching_channel_names.items():
            switchedChannels = [channels[channelName] for channelName in switchedChannelNames]
            dest[switchingChannelName] = SwitchingChannel(switchingChannelName, switchedChannels)

    def select_channels(self, mode_name: str) -> list[None | ChannelOffset]:
        assert mode_name in self.modes
        mode = self.modes[mode_name]
        return [channel_offset
                for mode_channel in mode.channels
                for channel_offset in self.__mode_channel_to_channel(mode_channel)
                ]

    def __mode_channel_to_channel(self, mode_channel: None | str | MatrixChannelInsertBlock) \
            -> list[None | ChannelOffset | SwitchingChannel]:

        if mode_channel is None:
            return [None]

        if isinstance(mode_channel, str):
            assert mode_channel in self.channels or mode_channel in self.switchingChannels
            if mode_channel in self.channels:
                return [self.channels[mode_channel]]
            elif mode_channel in self.switchingChannels:
                return [self.switchingChannels[mode_channel]]
            else:
                raise FixtureConfigurationError(f"Channel {mode_channel} is undefined.")

        assert isinstance(mode_channel, MatrixChannelInsertBlock)

        if isinstance(mode_channel.repeat_for, list):
            names = mode_channel.repeat_for
        else:
            names = list(map(lambda pixel: pixel.name, mode_channel.repeat_for.value(self.matrix)))

        if mode_channel.order is ChannelOrder.perPixel:
            return [self.__template_channel_to_channel(template_channel_name, name)
                    for name in names
                    for template_channel_name in mode_channel.template_channels
                    ]
        elif mode_channel.order is ChannelOrder.perChannel:
            return [self.__template_channel_to_channel(template_channel_name, pixel)
                    for template_channel_name in mode_channel.template_channels
                    for pixel in names
                    ]
        else:
            raise FixtureConfigurationError(f"{mode_channel.order.name} is not a supported channelOrder.")

    def __template_channel_to_channel(self, template_channel_name: str, value: str) \
            -> ChannelOffset | SwitchingChannel:

        if template_channel_name in self.templateChannels:
            return self.__renamed_copy(
                self.templateChannels[template_channel_name], value
            )
        elif template_channel_name in self.templateSwitchingChannels:
            switchingChannel = self.templateSwitchingChannels[template_channel_name]
            channels = [self.__renamed_copy(channel, value) for channel in switchingChannel.channels.values()]
            return SwitchingChannel(switchingChannel.name.replace("$pixelKey", value), channels)
        else:
            raise FixtureConfigurationError(f"Template {template_channel_name} is undefined.")

    @staticmethod
    def __renamed_copy(channel: ChannelOffset, new_name: str) -> ChannelOffset:
        copy = deepcopy(channel)
        copy.channel.name = copy.channel.name.replace("$pixelKey", new_name)
        return copy

    def __str__(self):
        return f"{self.name} ({self.shortName})"
