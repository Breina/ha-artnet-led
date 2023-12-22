from custom_components.dmx.fixture.capability import Capability
from custom_components.dmx.fixture.matrix import Matrix
from custom_components.dmx.fixture.wheel import Wheel


class Fixture:
    def __init__(self, name: str, short_name: str, categories: list[str], config_url: str | None):
        self.name = name
        self.shortName = short_name or name

        assert categories
        self.categories = categories

        self.configUrl = config_url

        self.channels: dict[str, Capability | list[Capability]] = {}
        self.matrix: Matrix | None = None

        self.wheels: dict[str, Wheel] = {}

    def define_channel(self, name: str, capability: Capability | list[Capability]):
        self.channels[name] = capability

    def define_matrix(self, matrix: Matrix):
        self.matrix = matrix

    def define_wheel(self, wheel: Wheel):
        self.wheels[wheel.name] = wheel

    def __str__(self):
        return f"{self.name} ({self.shortName})"
