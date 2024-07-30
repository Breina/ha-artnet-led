from copy import deepcopy

from custom_components.dmx.fixture.channel import Channel, ChannelOffset
from custom_components.dmx.fixture.exceptions import FixtureConfigurationError
from custom_components.dmx.fixture.matrix import Matrix, Pixel
from custom_components.dmx.fixture.mode import Mode, MatrixChannelInsertBlock, ChannelOrder
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

        self.matrix: Matrix | None = None
        self.wheels: dict[str, Wheel] = {}

        self.modes: dict[str, Mode] = {}

    def define_channel(self, channel: Channel):
        self.__define_channel_with_aliases(channel, self.channels)

    def define_template_channel(self, channel: Channel):
        self.__define_channel_with_aliases(channel, self.templateChannels)

    @staticmethod
    def __define_channel_with_aliases(channel: Channel, dest: dict[str, ChannelOffset]):
        dest[channel.name] = ChannelOffset(channel, 0)
        for byte_offset, fineChannelAlias in enumerate(channel.fineChannelAliases, start=1):
            dest[fineChannelAlias] = ChannelOffset(channel, byte_offset)

    def define_matrix(self, matrix: Matrix):
        self.matrix = matrix

    def define_wheel(self, wheel: Wheel):
        self.wheels[wheel.name] = wheel

    def define_mode(self, mode: Mode):
        self.modes[mode.name] = mode

    def select_channels(self, mode_name: str) -> list[None | ChannelOffset]:
        assert mode_name in self.modes
        mode = self.modes[mode_name]
        return [channel_offset
                for mode_channel in mode.channels
                for channel_offset in self.__mode_channel_to_channel(mode_channel)
                ]

    def __mode_channel_to_channel(self, mode_channel: None | str | MatrixChannelInsertBlock) \
            -> list[None | ChannelOffset]:

        if mode_channel is None:
            return [None]

        if isinstance(mode_channel, str):
            assert mode_channel in self.channels
            return [self.channels[mode_channel]]

        assert isinstance(mode_channel, MatrixChannelInsertBlock)

        pixels = mode_channel.repeat_for.value(self.matrix)
        if mode_channel.order is ChannelOrder.perPixel:
            return [self.__template_channel_to_channel(template_channel_name, pixel)
                    for pixel in pixels
                    for template_channel_name in mode_channel.template_channels
                    ]
        elif mode_channel.order is ChannelOrder.perChannel:
            return [self.__template_channel_to_channel(template_channel_name, pixel)
                    for template_channel_name in mode_channel.template_channels
                    for pixel in pixels
                    ]
        else:
            raise FixtureConfigurationError(f"{mode_channel.order.name} is not a supported channelOrder.")

    def __template_channel_to_channel(self, template_channel_name: str, pixel: Pixel) -> ChannelOffset:
        template_channel_offset = deepcopy(self.templateChannels[template_channel_name])
        template_channel_offset.channel.name = template_channel_offset.channel.name.replace("$pixelKey", pixel.name)
        return template_channel_offset

    def __str__(self):
        return f"{self.name} ({self.shortName})"
