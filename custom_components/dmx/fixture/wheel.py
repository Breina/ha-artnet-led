from custom_components.dmx.fixture import entity
from custom_components.dmx.fixture.entity import IrisPercent, Percent


class WheelSlot:
    def __init__(self):
        pass


class Open(WheelSlot):
    def __init__(self):
        super().__init__()

    def __repr__(self):
        return "Open"


class Closed(WheelSlot):
    def __init__(self):
        super().__init__()

    def __repr__(self):
        return "Closed"


class Color(WheelSlot):
    def __init__(self, name: str | None = None,
                 colors: list[str] | None = None,
                 color_temperature: entity.ColorTemperature | None = None):
        super().__init__()
        assert not colors or len(colors) >= 1
        self.name = name
        self.color = colors
        self.color_temperature = color_temperature

    def __repr__(self):
        if self.name:
            return self.name
        elif self.color_temperature:
            return str(self.color_temperature)
        elif self.color:
            return str(self.color)
        else:
            return "Color"


class Gobo(WheelSlot):
    def __init__(self, name: str | None, resource: str | None):
        super().__init__()
        self.name = name
        self.resource = resource

    def __repr__(self):
        return self.name or self.resource or "Gobo"


class Prism(WheelSlot):
    def __init__(self, name: str | None, facets: int | None = None):
        super().__init__()
        assert facets >= 2
        self.name = name
        self.facets = facets

    def __repr__(self):
        return self.name or "Prism"


class Iris(WheelSlot):
    def __init__(self, open_percent: IrisPercent | None = None):
        super().__init__()
        self.iris_percent = open_percent

    def __repr__(self):
        if self.iris_percent:
            return f"Iris {self.iris_percent}"
        else:
            return "Iris"


class Frost(WheelSlot):
    def __init__(self, frost_intensity: Percent | None = None):
        super().__init__()
        self.frost_intensity = frost_intensity

    def __repr__(self):
        if self.frost_intensity:
            return f"Frost {self.frost_intensity}"
        else:
            return "Frost"


class AnimationGoboStart(WheelSlot):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def __repr__(self):
        return self.name or "AnimationGoboStart"


class AnimationGoboEnd(WheelSlot):
    def __init__(self):
        super().__init__()

    def __repr__(self):
        return "AnimationGoboEnd"


class Wheel:
    def __init__(self, name: str, slots: list[WheelSlot], direction: str | None = None):
        assert len(slots) >= 2

        self.name = name
        self.direction = direction
        self.slots = slots

    def __repr__(self):
        return self.name

    def __str__(self):
        return f"{self.name}: {self.slots}"
