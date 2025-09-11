"""
The fixture is the God class on which can be operated. It holds the parsed
fixture data from the fixture format and can be used to get specific bits out.
"""

from copy import deepcopy

from custom_components.dmx.fixture.channel import Channel, ChannelOffset, SwitchingChannel
from custom_components.dmx.fixture.exceptions import FixtureConfigurationError
from custom_components.dmx.fixture.matrix import Matrix
from custom_components.dmx.fixture.mode import Mode, MatrixChannelInsertBlock, ChannelOrder
from custom_components.dmx.fixture.wheel import Wheel

PIXEL_KEY = "$pixelKey"


class Fixture:
    """
    The fixture model class containing all other model classes related to the
    fixture.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, name: str, short_name: str, categories: list[str], config_url: str | None):
        self.name = name
        self.short_name = short_name or name

        assert categories
        self.categories = categories

        self.config_url = config_url

        self.channels: dict[str, ChannelOffset] = {}
        self.template_channels: dict[str, Channel] = {}

        self.switching_channel_names: dict[str, set[str]] = {}
        self.switching_channels: dict[str, SwitchingChannel] = {}

        self.matrix: Matrix | None = None
        self.wheels: dict[str, Wheel] = {}

        self.modes: dict[str, Mode] = {}

    def define_channel(self, channel: Channel) -> None:
        """
        Defines a new channel. Will generate additional offset channels
        based on the aliases and parses switching channels.
        :param channel: The channel to be added to the fixture.
        """
        self.__define_channel_with_aliases(channel, self.channels, self.switching_channel_names)

    def define_template_channel(self, channel: Channel) -> None:
        """
        Defines a template channel. It is just added until `resolve_channels()`
        is called.
        :param channel: The template channel to be added.
        """
        self.template_channels[channel.name] = channel

    @staticmethod
    def __define_channel_with_aliases(
        channel: Channel, dest: dict[str, ChannelOffset], switching_dest: dict[str, set[str]]
    ) -> None:

        dest[channel.name] = ChannelOffset(channel, 0)
        for byte_offset, fine_channel_alias in enumerate(channel.fine_channel_aliases, start=1):
            dest[fine_channel_alias] = ChannelOffset(channel, byte_offset)

        for capability in channel.capabilities:
            for switch_channel_key, switch_channel_value in capability.switch_channels.items():
                if switch_channel_key not in switching_dest:
                    switching_dest[switch_channel_key] = set()
                switching_dest[switch_channel_key].add(switch_channel_value)

    def define_matrix(self, matrix: Matrix) -> None:
        """
        Adds a matrix to the fixture.
        :param matrix: The matrix to be added
        """
        self.matrix = matrix

    def define_wheel(self, wheel: Wheel) -> None:
        """
        Adds a wheel to the fixture.
        :param wheel: The wheel to be added
        """
        self.wheels[wheel.name] = wheel

    def define_mode(self, mode: Mode) -> None:
        """
        Adds a mode to the fixture.
        :param mode: The mode to be added
        """
        self.modes[mode.short_name] = mode

    def resolve_channels(self) -> None:
        """
        Creates channels for every template channel according to the defined
        matrix. Also links switching channels so that they can be used through
        the property `switchingChannels`.
        """
        if self.matrix:
            self.__resolve_matrix()

        self.__resolve_switching_channels(self.switching_channel_names, self.channels, self.switching_channels)

        del self.switching_channel_names

    def __resolve_matrix(self):
        for name in list(self.matrix.pixels_by_name.keys()) + list(self.matrix.pixel_groups.keys()):
            for template_channel in self.template_channels.values():
                channel_copy = self.__renamed_copy(template_channel, name)
                self.define_channel(channel_copy)

    @staticmethod
    def __resolve_switching_channels(
        switching_channel_names: dict[str, set[str]],
        channels: dict[str, ChannelOffset],
        dest: dict[str, SwitchingChannel],
    ):

        for switching_channel_name, switched_channel_names in switching_channel_names.items():
            switched_channels = [channels[channelName] for channelName in switched_channel_names]
            dest[switching_channel_name] = SwitchingChannel(
                switching_channel_name,
                {channel_offset.channel.name: channel_offset for channel_offset in switched_channels},
            )

    def select_mode(self, mode_name: str) -> list[None | ChannelOffset | SwitchingChannel]:
        """
        Selects a mode based on its name, and returns the relevant channels.
        :param mode_name: The name of the mode, which should exist.
        :return: The list of channels of that mode.
        """

        if mode_name not in self.modes:
            raise FixtureConfigurationError(
                f"Could not find mode {mode_name}, should be one of {list(self.modes.keys())}"
            )

        mode = self.modes[mode_name]
        return [
            channel_offset
            for mode_channel in mode.channels
            for channel_offset in self.__mode_channel_to_channel(mode_channel)
        ]

    def __mode_channel_to_channel(
        self, mode_channel: None | str | MatrixChannelInsertBlock
    ) -> list[None | ChannelOffset | SwitchingChannel]:

        if mode_channel is None:
            return [None]

        if isinstance(mode_channel, str):
            assert mode_channel in self.channels or mode_channel in self.switching_channels
            return [self.__resolve_channel(mode_channel)]

        assert isinstance(mode_channel, MatrixChannelInsertBlock)

        if isinstance(mode_channel.repeat_for, list):
            names = mode_channel.repeat_for
        else:
            names = list(map(lambda pixel: pixel.name, mode_channel.repeat_for.value(self.matrix)))

        if mode_channel.order is ChannelOrder.perPixel:
            return [
                self.__resolve_channel(template_channel_name.replace(PIXEL_KEY, name))
                for name in names
                for template_channel_name in mode_channel.template_channels
            ]
        if mode_channel.order is ChannelOrder.perChannel:
            return [
                self.__resolve_channel(template_channel_name.replace(PIXEL_KEY, name))
                for template_channel_name in mode_channel.template_channels
                for name in names
            ]
        raise FixtureConfigurationError(f"{mode_channel.order.name} is not a supported channelOrder.")

    def __resolve_channel(self, channel_name: str) -> ChannelOffset | SwitchingChannel:

        if channel_name in self.channels:
            return self.channels[channel_name]
        if channel_name in self.switching_channels:
            return self.switching_channels[channel_name]
        raise FixtureConfigurationError(f"Channel {channel_name} is undefined.")

    @staticmethod
    def __renamed_copy(channel: Channel, new_name: str) -> Channel:
        copy = deepcopy(channel)
        copy.matrix_key = new_name
        copy.name = copy.name.replace(PIXEL_KEY, new_name)
        copy.fine_channel_aliases = [
            fine_channel_alias.replace(PIXEL_KEY, new_name) for fine_channel_alias in copy.fine_channel_aliases
        ]
        for capability in copy.capabilities:
            capability.switch_channels = {
                switchingChannel.replace(PIXEL_KEY, new_name): referenced_channel.replace(PIXEL_KEY, new_name)
                for switchingChannel, referenced_channel in capability.switch_channels.items()
            }
        return copy

    def __str__(self):
        return f"{self.name} ({self.short_name})"
