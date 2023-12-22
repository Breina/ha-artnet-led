class Entity:
    def __init__(self,
                 value: float | str,
                 unit: str | None,
                 allowed_units: list[str | None],
                 keywords: dict[str, int] | None = None):
        if type(value) is str:
            assert keywords
            self.input = value
            self.value: float = keywords[value]
            self.unit = "%"
        else:
            assert unit in allowed_units
            self.input = f"{value}{unit}" if unit else str(value)
            self.value: float = value
            self.unit = unit

    def __str__(self):
        return str(self.input)

    def __repr__(self):
        return self.__str__()


class Speed(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         ["Hz", "bpm", "%"],
                         {
                             "fast reverse": -100,
                             "slow reverse": -1,
                             "stop": 0,
                             "slow": 1,
                             "fast": 100
                         })


class RotationSpeed(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         ["Hz", "rpm", "%"],
                         {
                             "fast CCW": -100,
                             "slow CCW": -1,
                             "stop": 0,
                             "slow CW": 1,
                             "fast CW": 100
                         })


class Time(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         ["s", "ms", "%"],
                         {
                             "instant": 0,
                             "short": 1,
                             "long": 100
                         })


class Distance(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         ["m", "%"],
                         {
                             "near": 1,
                             "far": 100
                         })


class Brightness(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         ["lm", "%"],
                         {
                             "off": 0,
                             "dark": 1,
                             "bright": 100
                         })


class ColorTemperature(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         ["K", "%"],
                         {
                             "warm": -100,
                             "CTO": -100,
                             "default": 0,
                             "cold": 100,
                             "CTB": 100
                         })


class FogOutput(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         ["m^3/min", "%"],
                         {
                             "off": 0,
                             "weak": 1,
                             "strong": 100
                         })


class RotationAngle(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit, ["deg", "%"])


class BeamAngle(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         ["deg", "%"],
                         {
                             "closed": 0,
                             "narrow": 1,
                             "wide": 100
                         })


class HorizontalAngle(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         ["deg", "%"],
                         {
                             "left": -100,
                             "center": 0,
                             "right": 100
                         })


class VerticalAngle(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         ["deg", "%"],
                         {
                             "top": -100,
                             "center": 0,
                             "bottom": 100
                         })


class SwingAngle(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         ["deg", "%"],
                         {
                             "off": 0,
                             "narrow": 1,
                             "wide": 100
                         })


class Parameter(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         [None, "%"],
                         {
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
                         })


class SlotNumber(Entity):
    def __init__(self, value: float | str):
        super().__init__(value, None, [None])


class Percent(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         ["%"],
                         {
                             "off": 0,
                             "low": 1,
                             "high": 100
                         })


class Insertion(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         ["%"],
                         {
                             "out": 0,
                             "in": 100,
                         })


class IrisPercent(Entity):
    def __init__(self, value: float | str, unit: str | None = None):
        super().__init__(value, unit,
                         ["%"],
                         {
                             "closed": 0,
                             "open": 1,
                         })


class ColorHex(Entity):
    def __init__(self, value: int):
        super().__init__(value, None, [None])
