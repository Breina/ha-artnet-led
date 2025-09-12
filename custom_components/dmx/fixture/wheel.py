"""
The wheel module contains all wheel related model classes.
https://github.com/OpenLightingProject/open-fixture-library/blob/master/docs/fixture-format.md#wheels

Most arguments, instance attributes and class names are directly mapped to
values of the fixture format. Therefore, we will excuse the python linter.
"""

# pylint: disable=too-few-public-methods


from custom_components.dmx.fixture import entity
from custom_components.dmx.fixture.entity import IrisPercent, Percent


class WheelSlot:
    """
    A wheel slot superclass, just to group all wheel slots together under one
    umbrella.
    """

    def __init__(self) -> None:
        pass


class Open(WheelSlot):
    """
    An Open wheel slot.
    Class name matches the fixture format exactly.
    """

    def __repr__(self) -> str:
        return "Open"


class Closed(WheelSlot):
    """
    An Closed wheel slot.
    Class name matches the fixture format exactly.
    """

    def __repr__(self) -> str:
        return "Closed"


class Color(WheelSlot):
    """
    A Color wheel slot.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(
        self,
        name: str | None = None,
        colors: list[str] | None = None,
        color_temperature: entity.ColorTemperature | None = None,
    ) -> None:
        super().__init__()
        assert not colors or len(colors) >= 1
        self.name = name
        self.color = colors
        self.color_temperature = color_temperature

    def __repr__(self) -> str:
        if self.name:
            return self.name
        if self.color_temperature:
            return str(self.color_temperature)
        if self.color:
            return str(self.color)
        return "Color"


class Gobo(WheelSlot):
    """
    A Gobo wheel slot.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, name: str | None, resource: str | None) -> None:
        super().__init__()
        self.name = name
        self.resource = resource

    def __repr__(self) -> str:
        return self.name or self.resource or "Gobo"


class Prism(WheelSlot):
    """
    A Prism wheel slot.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, name: str | None, facets: int | None = None) -> None:
        super().__init__()
        assert facets is None or facets >= 2
        self.name = name
        self.facets = facets

    def __repr__(self) -> str:
        return self.name or "Prism"


class Iris(WheelSlot):
    """
    A Iris wheel slot.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, open_percent: IrisPercent | None = None) -> None:
        super().__init__()
        self.iris_percent = open_percent

    def __repr__(self) -> str:
        if self.iris_percent:
            return f"Iris {self.iris_percent}"
        return "Iris"


class Frost(WheelSlot):
    """
    A Frost wheel slot.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, frost_intensity: Percent | None = None) -> None:
        super().__init__()
        self.frost_intensity = frost_intensity

    def __repr__(self) -> str:
        if self.frost_intensity:
            return f"Frost {self.frost_intensity}"
        return "Frost"


class AnimationGoboStart(WheelSlot):
    """
    A AnimationGoboStart wheel slot.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    def __repr__(self) -> str:
        return self.name or "AnimationGoboStart"


class AnimationGoboEnd(WheelSlot):
    """
    A AnimationGoboEnd wheel slot.
    Class name and instance arguments match the fixture format exactly.
    """

    def __repr__(self) -> str:
        return "AnimationGoboEnd"


class Wheel:
    """
    The Wheel model class, containing all of its wheel slots.
    """

    def __init__(self, name: str, slots: list[WheelSlot], direction: str | None = None) -> None:
        assert len(slots) >= 2

        self.name = name
        self.direction = direction
        self.slots = slots

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return f"{self.name}: {self.slots}"
