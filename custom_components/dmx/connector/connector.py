from custom_components.dmx.fixture.fixture import Fixture, FineChannelAlias
from custom_components.dmx.fixture.mode import MatrixChannelInsertBlock, RepeatFor


class ConnectedChannels:
    def __init__(self, name: str, channel: FineChannelAlias):
        self.name = name
        self.channels = [channel]

    def add_channel(self, channel: FineChannelAlias):
        self.channels.append(channel)


def connect(fixture: Fixture, mode_name: str, dmx_address: int):
    mode = fixture.modes[mode_name]

    defined_channels: [FineChannelAlias, ConnectedChannels] = {}

    for mode_channel in mode.channels:
        if isinstance(mode_channel, str):
            capability = fixture.capabilities[mode_channel]

        elif isinstance(mode_channel, MatrixChannelInsertBlock):
            for pixel in mode_channel.repeat_for.value()(fixture.matrix):
                pixelKey = str(pixel)




        else:
            dmx_address += 1
            continue

        if capability in defined_channels:
            connected_channel = capability[capability]

        dmx_address += 1




