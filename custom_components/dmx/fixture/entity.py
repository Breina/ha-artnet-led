class Entity:
    def __init__(self, value: int, unit: str | None):
        super().__init__()
        self.value = value
        self.unit = unit

    def __str__(self):
        return f"{self.value}{self.unit}"


class Speed(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "fast reverse": -100,
                "slow reverse": -1,
                "stop": 0,
                "slow": 1,
                "fast": 100
            }[value]
            unit = "%"
        else:
            assert unit in ["Hz", "bpm", "%"]

        super().__init__(value, unit)


class RotationSpeed(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "fast CCW": -100,
                "slow CCW": -1,
                "stop": 0,
                "slow CW": 1,
                "fast CW": 100
            }[value]
            unit = "%"
        else:
            assert unit in ["Hz", "rpm", "%"]

        super().__init__(value, unit)


class Time(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "instant": 0,
                "short": 1,
                "long": 100
            }[value]
            unit = "%"
        else:
            assert unit in ["s", "ms", "%"]

        super().__init__(value, unit)


class Distance(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "near": 1,
                "far": 100
            }[value]
            unit = "%"
        else:
            assert unit in ["m", "%"]

        super().__init__(value, unit)


class Brightness(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "off": 0,
                "dark": 1,
                "bright": 100
            }[value]
            unit = "%"
        else:
            assert unit in ["lm", "%"]

        super().__init__(value, unit)


class ColorTemperature(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "warm": -100,
                "CTO": -100,
                "default": 0,
                "cold": 100,
                "CTB": 100
            }[value]
            unit = "%"
        else:
            assert unit in ["K", "%"]

        super().__init__(value, unit)


class FogOutput(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "off": 0,
                "weak": 1,
                "strong": 100
            }[value]
            unit = "%"
        else:
            assert unit in ["m^3/min", "%"]

        super().__init__(value, unit)


class RotationAngle(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        assert unit in ["deg", "%"]

        super().__init__(value, unit)


class BeamAngle(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "closed": 0,
                "narrow": 1,
                "wide": 100
            }[value]
            unit = "%"
        else:
            assert unit in ["deg", "%"]

        super().__init__(value, unit)


class HorizontalAngle(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "left": -100,
                "center": 0,
                "right": 100
            }[value]
            unit = "%"
        else:
            assert unit in ["deg", "%"]

        super().__init__(value, unit)


class VerticalAngle(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "top": -100,
                "center": 0,
                "bottom": 100
            }[value]
            unit = "%"
        else:
            assert unit in ["deg", "%"]

        super().__init__(value, unit)


class SwingAngle(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "off": 0,
                "narrow": 1,
                "wide": 100
            }[value]
            unit = "%"
        else:
            assert unit in ["deg", "%"]

        super().__init__(value, unit)


class Parameter(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "off": 0,
                "instant": 0,
                "low": 1,
                "slow": 1,
                "small": 1,
                "short": 1,
                "high": 100,
                "fast": 100,
                "big": 100,
                "long": 100
            }[value]
            unit = "%"
        else:
            assert unit in [None, "%"]

        super().__init__(value, unit)


class SlotNumber(Entity):
    def __init__(self, value: int | str):
        super().__init__(value, None)


class Percent(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "off": 0,
                "low": 1,
                "high": 100
            }[value]
            unit = "%"
        else:
            assert unit == "%"

        super().__init__(value, unit)


class Insertion(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "out": 0,
                "in": 100,
            }[value]
            unit = "%"
        else:
            assert unit == "%"

        super().__init__(value, unit)


class IrisPercent(Entity):
    def __init__(self, value: int | str, unit: str | None = None):
        if type(value) is str:
            value = {
                "closed": 0,
                "open": 1,
            }[value]
            unit = "%"
        else:
            assert unit == "%"

        super().__init__(value, unit)


class ColorHex(Entity):
    def __init__(self, value: int):
        super().__init__(value, None)
