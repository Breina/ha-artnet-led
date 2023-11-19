from enum import Enum, auto
from typing import Callable, List

from matplotlib.testing.jpl_units import Duration

from custom_components.dmx.fixture import entity
from custom_components.dmx.fixture.entity import RotationAngle, RotationSpeed, Brightness, SlotNumber, \
    SwingAngle, Parameter, Percent, VerticalAngle, HorizontalAngle, Distance, IrisPercent, Insertion


class MenuClick(Enum):
    start = auto()
    center = auto()
    end = auto()
    hidden = auto()


class ShutterEffect(Enum):
    Open = auto()
    Closed = auto()
    Strobe = auto()
    Pulse = auto()
    RampUp = auto()
    RampDown = auto()
    RampUpDown = auto()
    Lightning = auto()
    Spikes = auto()


class SingleColor(Enum):
    Red = auto()
    Green = auto()
    Blue = auto()
    Cyan = auto()
    Magenta = auto()
    Yellow = auto()
    Amber = auto()
    White = auto()
    WarmWhite = auto()
    ColdWhite = auto()
    UV = auto()
    Lime = auto()
    Indigo = auto()


class WheelOrSlot(Enum):
    wheel = auto()
    slot = auto()


class EffectPreset(Enum):
    ColorJump = auto()
    ColorFade = auto()


class BladePosition(Enum):
    Top = auto()
    Right = auto()
    Bottom = auto()
    Left = auto()


class FogTypeOutput(Enum):
    Fog = auto()
    Haze = auto()


def _make_interpolater(from_range_min: int, from_range_max: int,
                       to_range_min: int, to_range_max: int) -> Callable[[int], int]:
    valueRange = from_range_max - from_range_min
    dmxRange = to_range_max - to_range_min
    scaleFactor = float(dmxRange) / float(valueRange)

    def interp_fn(value: int) -> int:
        return int(to_range_min + (value - from_range_min) * scaleFactor)

    return interp_fn


class Capability:

    def __init__(self, name: str,
                 comment: str | None = None,
                 dmx_range: [int] = None,
                 menu_click: MenuClick = MenuClick.start,
                 fine_channel_aliases: List[str] = None):
        super().__init__()
        if dmx_range is None:
            dmx_range = [0, 255]
        assert len(dmx_range) == 2

        self.name = name
        self.comment = comment
        self.dmxRangeStart = dmx_range[0]
        self.dmxRangeEnd = dmx_range[1]

        self.menu_click = menu_click
        self.fine_channel_aliases = fine_channel_aliases or []

        self.__is_static = True
        self.__interpolate_to_dmx, self.__interpolate_from_dmx = [None, None]

    def is_applicable(self, dmx_value: int):
        return self.dmxRangeStart <= dmx_value <= self.dmxRangeEnd

    def to_dmx(self, *value) -> int:
        if self.__is_static:
            if self.menu_click == MenuClick.start:
                return self.dmxRangeStart
            elif self.menu_click == MenuClick.center:
                return int((self.dmxRangeStart + self.dmxRangeEnd) / 2)
            elif self.menu_click == MenuClick.end:
                return self.dmxRangeEnd
        else:
            assert len(value) == 1
            return self.__interpolate_to_dmx(value[0])

    def from_dmx(self, dmx_value: int):
        assert not self.__is_static
        return self.__interpolate_from_dmx(dmx_value)

    def _define_from_entity(self, *entities):
        size = len(entities)
        if size == 1:
            self._define_as_static_value()
        else:
            assert size == 2
            self._define_as_dynamic_value(entities[0].value, entities[1].value)

    def _define_as_static_value(self):
        self.__is_static = True

    def _define_as_dynamic_value(self, range_start: int, range_end: int):
        self.__is_static = False
        self.__interpolate_to_dmx = _make_interpolater(
            range_start, range_end, self.dmxRangeStart, self.dmxRangeEnd
        )
        self.__interpolate_from_dmx = _make_interpolater(
            self.dmxRangeStart, self.dmxRangeEnd, range_start, range_end
        )

    def __str__(self):
        return self.name if not self.comment else self.comment

    def __repr__(self):
        return self.__str__()


class ShutterStrobe(Capability):
    def __init__(self, name: str, shutter_effect: ShutterEffect,
                 sound_controlled: bool = False,
                 random_timing: bool = False,
                 speed: List[entity.Speed] | None = None,
                 duration: List[entity.Time] | None = None,
                 **kwargs):
        super().__init__(name, **kwargs)
        self.effect = shutter_effect
        self.sound_controlled = sound_controlled
        self.random_timing = random_timing

        if speed:
            assert not duration
            self.speed = speed
            self._define_from_entity(*speed)

        elif duration:
            assert not speed
            self.duration = duration
            self._define_from_entity(*duration)


class StrobeSpeed(Capability):
    def __init__(self, name: str, speed: List[entity.Speed], **kwargs):
        super().__init__(name, **kwargs)
        self.speed = speed
        self._define_from_entity(*speed)


class StrobeDuration(Capability):
    def __init__(self, name: str, duration: List[entity.Time], **kwargs):
        super().__init__(name, **kwargs)
        self.duration = duration
        self._define_from_entity(*duration)


class Intensity(Capability):
    def __init__(self, name: str, brightness: List[Brightness] | None = None, **kwargs):
        super().__init__(name, **kwargs)
        self.brightness = brightness or [Brightness("off"), Brightness("bright")]
        self._define_from_entity(*self.brightness)


class ColorIntensity(Capability):
    def __init__(self, name: str, color: SingleColor, brightness: List[Brightness] | None = None, **kwargs):
        super().__init__(name, **kwargs)
        self.color = color
        self.brightness = brightness or [Brightness("off"), Brightness("bright")]
        self._define_from_entity(*self.brightness)


class ColorPreset(Capability):
    def __init__(self, name: str,
                 colors: List[List[str]] | None = None,
                 color_temperature: List[entity.ColorTemperature] | None = None, **kwargs):
        super().__init__(name, **kwargs)

        if colors:
            self.colors = colors
            size = len(colors)
            if size == 1:
                self._define_as_static_value()
            else:
                assert size == 2
                assert not color_temperature
                self._define_as_dynamic_value(0, 100)

        if color_temperature:
            self.color_temperature = color_temperature
            if len(color_temperature) == 2:
                assert not colors
            self._define_from_entity(*color_temperature)


class ColorTemperature(Capability):
    def __init__(self, name: str, color_temperature: List[entity.ColorTemperature], **kwargs):
        super().__init__(name, **kwargs)
        self.color_temperature = color_temperature
        self._define_from_entity(*self.color_temperature)


class Pan(Capability):
    def __init__(self, name: str, angle: List[RotationAngle], **kwargs):
        super().__init__(name, **kwargs)
        self.angle = angle
        self._define_from_entity(*angle)


class PanContinuous(Capability):
    def __init__(self, name: str, speed: List[RotationSpeed], **kwargs):
        super().__init__(name, **kwargs)
        self.speed = speed
        self._define_from_entity(*speed)


class Tilt(Capability):
    def __init__(self, name: str, angle: List[RotationAngle], **kwargs):
        super().__init__(name, **kwargs)
        self.angle = angle
        self._define_from_entity(*angle)


class TiltContinuous(Capability):
    def __init__(self, name: str, speed: List[RotationSpeed], **kwargs):
        super().__init__(name, **kwargs)
        self.speed = speed
        self._define_from_entity(*speed)


class PanTiltSpeed(Capability):
    def __init__(self, name: str,
                 speed: List[entity.Speed] | None,
                 duration: List[Duration] | None,
                 **kwargs):
        super().__init__(name, **kwargs)
        assert speed or duration
        if speed:
            assert not duration
            self.speed = speed
            self._define_from_entity(*speed)
        elif duration:
            self.duration = duration
            self._define_from_entity(*duration)


class WheelSlot(Capability):
    def __init__(self, name: str, slot_number: List[SlotNumber], wheel: str = None, **kwargs):
        super().__init__(name, **kwargs)
        self.wheel = wheel or name
        self.slot_number = slot_number
        self._define_from_entity(*slot_number)


class WheelShake(Capability):
    def __init__(self, name: str,
                 is_shaking: WheelOrSlot = WheelOrSlot.wheel,
                 wheel: str | List[str] | None = None,
                 slot_number: List[SlotNumber] | None = None,
                 shake_speed: List[entity.Speed] | None = None,
                 shake_angle: List[SwingAngle] | None = None,
                 **kwargs):
        super().__init__(name, **kwargs)
        self.is_shaking = is_shaking
        self.wheel = wheel or name

        if slot_number:
            self.slot_number = slot_number
            if len(slot_number) == 2:
                assert not shake_speed or len(shake_speed) != 2
                assert not shake_angle or len(shake_angle) != 2
                self._define_as_dynamic_value(slot_number[0].value, slot_number[1].value)

        if shake_speed:
            self.shake_speed = shake_speed
            if len(shake_speed) == 2:
                assert not slot_number or len(slot_number) != 2
                assert not shake_angle or len(shake_angle) != 2
                self._define_as_dynamic_value(shake_speed[0].value, shake_speed[1].value)

        if shake_angle:
            self.shake_angle = shake_angle
            if len(shake_angle) == 2:
                assert not slot_number or len(slot_number) != 2
                assert not shake_speed or len(shake_speed) != 2
                self._define_as_dynamic_value(shake_angle[0].value, shake_angle[1].value)


class WheelSlotRotation(Capability):
    def __init__(self, name: str,
                 wheel: str | List[str] | None = None,
                 slot_number: SlotNumber | None = None,
                 speed: List[RotationSpeed] | None = None,
                 angle: List[RotationAngle] | None = None,
                 **kwargs):
        super().__init__(name, **kwargs)

        self.wheel = wheel or name
        self.slot_number = slot_number
        if speed:
            assert not angle
            self._define_from_entity(*speed)
        elif angle:
            self._define_from_entity(*angle)


class WheelRotation(Capability):
    def __init__(self, name: str,
                 wheel: str | List[str] | None = None,
                 speed: List[RotationSpeed] | None = None,
                 angle: List[RotationAngle] | None = None,
                 **kwargs):
        super().__init__(name, **kwargs)

        self.wheel = wheel or name
        if speed:
            assert not angle
            self._define_from_entity(*speed)
        elif angle:
            self._define_from_entity(*angle)


class Effect(Capability):
    def __init__(self, name: str,
                 effect_name: str | None = None,
                 effect_preset: EffectPreset | None = None,
                 speed: List[entity.Speed] | None = None,
                 duration: List[entity.Time] | None = None,
                 parameter: List[Parameter] | None = None,
                 sound_controlled: bool = False,
                 sound_sensitivity: List[Percent] | None = None,
                 **kwargs):
        super().__init__(name, **kwargs)

        assert effect_name or effect_preset
        self.effect_name = effect_name
        self.effect_preset = effect_preset
        self.sound_controlled = sound_controlled

        if speed:
            self.speed = speed
            if len(self.speed) == 2:
                assert not duration or len(duration) != 2
                assert not parameter or len(parameter) != 2
                assert not sound_sensitivity or len(sound_sensitivity) != 2
                self._define_as_dynamic_value(speed[0].value, speed[1].value)

        if duration:
            self.duration = duration
            if len(self.duration) == 2:
                assert not speed or len(speed) != 2
                assert not parameter or len(parameter) != 2
                assert not sound_sensitivity or len(sound_sensitivity) != 2
                self._define_as_dynamic_value(duration[0].value, duration[1].value)

        if parameter:
            self.parameter = parameter
            if len(self.parameter) == 2:
                assert not speed or len(speed) != 2
                assert not duration or len(duration) != 2
                assert not sound_sensitivity or len(sound_sensitivity) != 2
                self._define_as_dynamic_value(parameter[0].value, parameter[1].value)

        if sound_sensitivity:
            self.sound_sensitivity = sound_sensitivity
            if len(self.sound_sensitivity) == 2:
                assert not speed or len(speed) != 2
                assert not duration or len(duration) != 2
                assert not parameter or len(parameter) != 2
                self._define_as_dynamic_value(sound_sensitivity[0].value, sound_sensitivity[1].value)


class BeamAngle(Capability):
    def __init__(self, name: str, angle: List[entity.BeamAngle], **kwargs):
        super().__init__(name, **kwargs)
        self.angle = angle
        self._define_from_entity(*angle)


class BeamPosition(Capability):
    def __init__(self, name: str,
                 horizontal_angle: List[HorizontalAngle] | None = None,
                 vertical_angle: List[VerticalAngle] | None = None,
                 **kwargs):
        super().__init__(name, **kwargs)

        assert horizontal_angle or vertical_angle

        if horizontal_angle:
            self.horizontal_angle = horizontal_angle
            if len(horizontal_angle) == 2:
                assert not vertical_angle or len(vertical_angle) != 2
                self._define_from_entity(*horizontal_angle)

        if vertical_angle:
            self.vertical_angle = vertical_angle
            if len(vertical_angle) == 2:
                assert not horizontal_angle or len(horizontal_angle) != 2
                self._define_from_entity(*vertical_angle)


class EffectSpeed(Capability):
    def __init__(self, name: str, speed: List[entity.Speed], **kwargs):
        super().__init__(name, **kwargs)
        self.speed = speed
        self._define_from_entity(*speed)


class EffectDuration(Capability):
    def __init__(self, name: str, duration: List[entity.Time], **kwargs):
        super().__init__(name, **kwargs)
        self.duration = duration
        self._define_from_entity(*duration)


class EffectParameter(Capability):
    def __init__(self, name: str, parameter: List[Parameter], **kwargs):
        super().__init__(name, **kwargs)
        self.parameter = parameter
        self._define_from_entity(*parameter)


class SoundSensitivity(Capability):
    def __init__(self, name: str, sound_sensitivity: List[Percent], **kwargs):
        super().__init__(name, **kwargs)
        self.soundSensitivity = sound_sensitivity
        self._define_from_entity(*sound_sensitivity)


class Focus(Capability):
    def __init__(self, name: str, distance: List[Distance], **kwargs):
        super().__init__(name, **kwargs)
        self.distance = distance
        self._define_from_entity(*distance)


class Zoom(Capability):
    def __init__(self, name: str, angle: List[BeamAngle], **kwargs):
        super().__init__(name, **kwargs)
        self.angle = angle
        self._define_from_entity(*angle)


class Iris(Capability):
    def __init__(self, name: str, open_percent: List[IrisPercent], **kwargs):
        super().__init__(name, **kwargs)
        self.open_percent = open_percent
        self._define_from_entity(*open_percent)


class IrisEffect(Capability):
    def __init__(self, name: str, effect_name: str, speed: List[entity.Speed] | None = None, **kwargs):
        super().__init__(name, **kwargs)
        self.effect_name = effect_name
        if speed:
            self.speed = speed
            self._define_from_entity(*speed)


class Frost(Capability):
    def __init__(self, name: str, frost_intensity: List[Percent], **kwargs):
        super().__init__(name, **kwargs)
        self.frost_intensity = frost_intensity
        self._define_from_entity(*frost_intensity)


class FrostEffect(Capability):
    def __init__(self, name: str, effect_name: str, speed: List[entity.Speed] | None = None, **kwargs):
        super().__init__(name, **kwargs)
        self.effect_name = effect_name
        if speed:
            self.speed = speed
            self._define_from_entity(*speed)


class Prism(Capability):
    def __init__(self, name: str,
                 speed: List[RotationSpeed] | None = None,
                 angle: List[RotationAngle] | None = None,
                 **kwargs):
        super().__init__(name, **kwargs)
        if speed:
            assert not angle
            self.speed = speed
            self._define_from_entity(*speed)

        elif angle:
            self.angle = angle
            self._define_from_entity(*angle)


class PrismRotation(Capability):
    def __init__(self, name: str,
                 speed: List[RotationSpeed] | None = None,
                 angle: List[RotationAngle] | None = None,
                 **kwargs):
        super().__init__(name, **kwargs)
        if speed:
            assert not angle
            self.speed = speed
            self._define_from_entity(*speed)

        else:
            assert angle
            self.angle = angle
            self._define_from_entity(*angle)


class BladeInsertion(Capability):
    def __init__(self, name: str,
                 blade: BladePosition | int,
                 insertion: List[Insertion],
                 **kwargs):
        super().__init__(name, **kwargs)
        self.blade = blade
        self._define_from_entity(*insertion)


class BladeRotation(Capability):
    def __init__(self, name: str,
                 blade: BladePosition | int,
                 angle: List[RotationAngle],
                 **kwargs):
        super().__init__(name, **kwargs)
        self.blade = blade
        self._define_from_entity(*angle)


class BladeSystemRotation(Capability):
    def __init__(self, name: str,
                 angle: List[RotationAngle],
                 **kwargs):
        super().__init__(name, **kwargs)
        self._define_from_entity(*angle)


class Fog(Capability):
    def __init__(self, name: str,
                 fog_type: FogTypeOutput | None = None,
                 fog_output: List[entity.FogOutput] | None = None,
                 **kwargs):
        super().__init__(name, **kwargs)
        self.fog_type = fog_type
        if fog_output:
            self.fog_output = fog_output
            self._define_from_entity(*fog_output)


class FogOutput(Capability):
    def __init__(self, name: str,
                 fog_output: List[entity.FogOutput],
                 **kwargs):
        super().__init__(name, **kwargs)
        self.fog_output = fog_output
        self._define_from_entity(*fog_output)


class FogType(Capability):
    def __init__(self, name: str,
                 fog_type: FogTypeOutput | None = None,
                 **kwargs):
        super().__init__(name, **kwargs)
        self.fog_type = fog_type


class Rotation(Capability):
    def __init__(self, name: str,
                 speed: List[RotationSpeed] | None = None,
                 angle: List[RotationAngle] | None = None,
                 **kwargs):
        super().__init__(name, **kwargs)
        assert speed or angle
        if speed:
            self.speed = speed
            self._define_from_entity(*speed)

        else:
            self.angle = angle
            self._define_from_entity(*speed)


class Speed(Capability):
    def __init__(self, name: str,
                 speed: List[entity.Speed],
                 **kwargs):
        super().__init__(name, **kwargs)
        self.speed = speed
        self._define_from_entity(*speed)


class Time(Capability):
    def __init__(self, name: str,
                 time: List[entity.Time],
                 **kwargs):
        super().__init__(name, **kwargs)
        self.time = time
        self._define_from_entity(*time)


class Maintenance(Capability):
    def __init__(self, name: str,
                 parameter: List[Parameter] | None = None,
                 hold: Time | None = None,
                 **kwargs):
        super().__init__(name, **kwargs)
        self.hold = hold
        if parameter:
            self.parameter = parameter
            self._define_from_entity(*parameter)


class Generic(Capability):
    def __init__(self, name: str, **kwargs):
        super().__init__(name, **kwargs)
