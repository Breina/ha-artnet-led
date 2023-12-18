from custom_components.dmx.fixture import entity
from custom_components.dmx.fixture.entity import IrisPercent, Percent


class WheelSlot:
    def __init__(self):
        pass


class Open(WheelSlot):
    def __init__(self):
        super().__init__()


class Closed(WheelSlot):
    def __init__(self):
        super().__init__()


class Color(WheelSlot):
    def __init__(self, name: str | None = None,
                 colors: list[str] | None = None, color_temperature: entity.ColorTemperature | None = None):
        super().__init__()
        assert len(colors) >= 1
        self.name = name
        self.color = colors
        self.color_temperature = color_temperature


class Gobo(WheelSlot):
    def __init__(self, name: str | None, resource: str | None):
        super().__init__()
        self.name = name
        self.resource = resource


class Prism(WheelSlot):
    def __init__(self, name: str | None, facets: int | None = None):
        super().__init__()
        assert facets >= 2
        self.name = name
        self.facets = facets


class Iris(WheelSlot):
    def __init__(self, iris_percent: IrisPercent | None = None):
        super().__init__()
        self.iris_percent = iris_percent


class Frost(WheelSlot):
    def __init__(self, frost_intensity: Percent | None = None):
        super().__init__()
        self.frost_intensity = frost_intensity


class AnimationGoboStart(WheelSlot):
    def __init__(self, name: str):
        super().__init__()
        self.name = name


class AnimationGoboEnd(WheelSlot):
    def __init__(self):
        super().__init__()


class Wheel:
    def __init__(self, name: str, slots: list[WheelSlot], direction: str | None = None):
        assert len(slots) >= 2

        self.name = name
        self.direction = direction
        self.slots = slots
