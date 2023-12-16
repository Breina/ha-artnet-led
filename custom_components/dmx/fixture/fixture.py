from custom_components.dmx.fixture.capability import Capability
from custom_components.dmx.fixture.matrix import Matrix


class Fixture:
    def __init__(self, channels: dict[str, Capability], matrix: Matrix | None = None):
        self.channels = channels
        self.matrix = matrix