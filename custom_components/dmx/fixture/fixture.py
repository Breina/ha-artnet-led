from copy import deepcopy

from custom_components.dmx.fixture.channel import Channel, ChannelOffset, SwitchingChannel
from custom_components.dmx.fixture.exceptions import FixtureConfigurationError
from custom_components.dmx.fixture.matrix import Matrix
from custom_components.dmx.fixture.mode import Mode, MatrixChannelInsertBlock, ChannelOrder
from custom_components.dmx.fixture.wheel import Wheel

PIXEL_KEY = "$pixelKey"


class Fixture:
    def __init__(self, name: str, short_name: str, categories: list[str], config_url: str | None):
        self.name = name
        self.shortName = short_name or name

        assert categories
        self.categories = categories

        self.configUrl = config_url

        self.channels: dict[str, ChannelOffset] = {}
        self.templateChannels: dict[str, Channel] = {}

        self.switchingChannelNames: dict[str, set[str]] = {}
        self.switchingChannels: dict[str, SwitchingChannel] = {}

        self.matrix: Matrix | None = None
        self.wheels: dict[str, Wheel] = {}

        self.modes: dict[str, Mode] = {}

    def define_channel(self, channel: Channel):
        self.__define_channel_with_aliases(channel, self.channels, self.switchingChannelNames)

    def define_template_channel(self, channel: Channel):
        self.templateChannels[channel.name] = channel

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
        if self.matrix:
            self.__resolve_matrix()

        self.__resolve_switching_channels(self.switchingChannelNames, self.channels, self.switchingChannels)

        del self.switchingChannelNames

    def __resolve_matrix(self):
        for name in list(self.matrix.pixelsByName.keys()) + list(self.matrix.pixelGroups.keys()):
            for templateChannel in self.templateChannels.values():
                channel_copy = self.__renamed_copy(templateChannel, name)
                self.define_channel(channel_copy)

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
            return [self.__resolve_channel(mode_channel)]

        assert isinstance(mode_channel, MatrixChannelInsertBlock)

        if isinstance(mode_channel.repeat_for, list):
            names = mode_channel.repeat_for
        else:
            names = list(map(lambda pixel: pixel.name, mode_channel.repeat_for.value(self.matrix)))

        if mode_channel.order is ChannelOrder.perPixel:
            return [self.__resolve_channel(template_channel_name.replace(PIXEL_KEY, name))
                    for name in names
                    for template_channel_name in mode_channel.template_channels
                    ]
        elif mode_channel.order is ChannelOrder.perChannel:
            return [self.__resolve_channel(template_channel_name.replace(PIXEL_KEY, name))
                    for template_channel_name in mode_channel.template_channels
                    for name in names
                    ]
        else:
            raise FixtureConfigurationError(f"{mode_channel.order.name} is not a supported channelOrder.")

    def __resolve_channel(self, channel_name: str) -> ChannelOffset | SwitchingChannel:
        if channel_name in self.channels:
            return self.channels[channel_name]
        elif channel_name in self.switchingChannels:
            return self.switchingChannels[channel_name]
        else:
            raise FixtureConfigurationError(f"Channel {channel_name} is undefined.")

    @staticmethod
    def __renamed_copy(channel: Channel, new_name: str) -> Channel:
        copy = deepcopy(channel)
        copy.name = copy.name.replace(PIXEL_KEY, new_name)
        copy.fineChannelAliases = [
            fineChannelAlias.replace(PIXEL_KEY, new_name) for fineChannelAlias in copy.fineChannelAliases
        ]
        for capability in copy.capabilities:
            capability.switchChannels = {
                switchingChannel.replace(PIXEL_KEY, new_name): referencedChannel.replace(PIXEL_KEY, new_name)
                for switchingChannel, referencedChannel in capability.switchChannels.items()
            }
        return copy

    def __str__(self):
        return f"{self.name} ({self.shortName})"
