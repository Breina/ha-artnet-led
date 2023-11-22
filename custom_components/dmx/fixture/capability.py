from enum import Enum, auto
from typing import Callable, List

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
    Burst = auto()


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


def _make_interpolater(from_range_min: float, from_range_max: float,
                       to_range_min: float, to_range_max: float) -> Callable[[float], float]:
    if from_range_min == from_range_max:
        return lambda _: to_range_min

    from_range = from_range_max - from_range_min
    to_range = to_range_max - to_range_min
    scaleFactor = float(to_range) / float(from_range)

    def interp_fn(value: float) -> float:
        return int(to_range_min + (value - from_range_min) * scaleFactor)

    return interp_fn


class Capability:

    def __init__(self,
                 comment: str | None = None,
                 dmx_range: [int] = None,
                 menu_click: MenuClick = MenuClick.start,
                 fine_channel_aliases: List[str] = None):
        super().__init__()
        if dmx_range is None:
            dmx_range = [0, 255]
        assert len(dmx_range) == 2

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

    def _define_as_dynamic_value(self, range_start: float, range_end: float):
        self.__is_static = False
        self.__interpolate_to_dmx = _make_interpolater(
            range_start, range_end, self.dmxRangeStart, self.dmxRangeEnd
        )
        self.__interpolate_from_dmx = _make_interpolater(
            self.dmxRangeStart, self.dmxRangeEnd, range_start, range_end
        )

    def __str__(self):
        if self.comment:
            return self.comment
        elif self.dmxRangeStart and self.dmxRangeEnd:
            return f"[{self.dmxRangeStart},{self.dmxRangeEnd}]"
        else:
            return "Capability"

    def __repr__(self):
        return self.__str__()

    def args_to_str(self, *args) -> str:
        if self.comment:
            return self.comment

        s = ""
        for arg in args:
            if arg:
                if isinstance(arg, Enum):
                    arg = arg.name
                elif isinstance(arg, list) and len(arg) == 1:
                    arg = arg[0]
                s = s + f" {arg}"

        return s[1:]


class ShutterStrobe(Capability):
    def __init__(self, shutter_effect: ShutterEffect,
                 sound_controlled: bool = False,
                 random_timing: bool = False,
                 speed: List[entity.Speed] | None = None,
                 duration: List[entity.Time] | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.effect = shutter_effect
        self.sound_controlled = sound_controlled
        self.random_timing = random_timing
        self.speed = speed
        self.duration = duration

        if speed:
            if len(speed) == 2:
                assert not duration or len(duration) != 2
                self._define_from_entity(*speed)

        elif duration:
            if len(duration) == 2:
                assert not speed or len(speed) != 2
                self._define_from_entity(*duration)

    def __str__(self):
        return self.args_to_str(self.effect,
                                "sound controlled" if self.sound_controlled else None,
                                "random timing" if self.random_timing else None,
                                self.speed,
                                self.duration
                                )


class StrobeSpeed(Capability):
    def __init__(self, speed: List[entity.Speed], **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self._define_from_entity(*speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class StrobeDuration(Capability):
    def __init__(self, duration: List[entity.Time], **kwargs):
        super().__init__(**kwargs)
        self.duration = duration
        self._define_from_entity(*duration)

    def __str__(self):
        return self.args_to_str(self.duration)


class Intensity(Capability):
    def __init__(self, brightness: List[Brightness] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.brightness = brightness or [Brightness("off"), Brightness("bright")]
        self._define_from_entity(*self.brightness)

    def __str__(self):
        return self.args_to_str(self.brightness)


class ColorIntensity(Capability):
    def __init__(self, color: SingleColor, brightness: List[Brightness] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.color = color
        self.brightness = brightness or [Brightness("off"), Brightness("bright")]
        self._define_from_entity(*self.brightness)

    def __str__(self):
        return self.args_to_str(self.color, self.brightness)


class ColorPreset(Capability):
    def __init__(self,
                 colors: List[List[str]] | None = None,
                 color_temperature: List[entity.ColorTemperature] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.colors = colors
        self.color_temperature = color_temperature

        if colors:
            size = len(colors)
            if size == 1:
                self._define_as_static_value()
            else:
                assert size == 2
                assert not color_temperature
                self._define_as_dynamic_value(0, 100)

        if color_temperature:
            if len(color_temperature) == 2:
                assert not colors
            self._define_from_entity(*color_temperature)

    def __str__(self):
        return self.args_to_str(self.colors, self.color_temperature)


class ColorTemperature(Capability):
    def __init__(self, color_temperature: List[entity.ColorTemperature], **kwargs):
        super().__init__(**kwargs)
        self.color_temperature = color_temperature
        self._define_from_entity(*self.color_temperature)

    def __str__(self):
        return self.args_to_str(self.color_temperature)


class Pan(Capability):
    def __init__(self, angle: List[RotationAngle], **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(*angle)

    def __str__(self):
        return self.args_to_str(self.angle)


class PanContinuous(Capability):
    def __init__(self, speed: List[RotationSpeed], **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self._define_from_entity(*speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class Tilt(Capability):
    def __init__(self, angle: List[RotationAngle], **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(*angle)

    def __str__(self):
        return self.args_to_str(self.angle)


class TiltContinuous(Capability):
    def __init__(self, speed: List[RotationSpeed], **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self._define_from_entity(*speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class PanTiltSpeed(Capability):
    def __init__(self,
                 speed: List[entity.Speed] | None,
                 duration: List[entity.Time] | None,
                 **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self.duration = duration
        assert speed or duration
        if speed:
            assert not duration
            self._define_from_entity(*speed)
        elif duration:
            self._define_from_entity(*duration)

    def __str__(self):
        return self.args_to_str(self.speed, self.duration)


class WheelSlot(Capability):
    def __init__(self, name: str, slot_number: List[SlotNumber], wheel: str = None, **kwargs):
        super().__init__(**kwargs)
        self.wheel = wheel or name
        self.slot_number = slot_number
        self._define_from_entity(*slot_number)

    def __str__(self):
        return self.args_to_str(self.wheel, self.slot_number)


class WheelShake(Capability):
    def __init__(self, name: str,
                 is_shaking: WheelOrSlot = WheelOrSlot.wheel,
                 wheel: str | List[str] | None = None,
                 slot_number: List[SlotNumber] | None = None,
                 shake_speed: List[entity.Speed] | None = None,
                 shake_angle: List[SwingAngle] | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.is_shaking = is_shaking
        self.wheel = wheel or name
        self.slot_number = slot_number
        self.shake_speed = shake_speed
        self.shake_angle = shake_angle

        if slot_number:
            if len(slot_number) == 2:
                assert not shake_speed or len(shake_speed) != 2
                assert not shake_angle or len(shake_angle) != 2
                self._define_as_dynamic_value(slot_number[0].value, slot_number[1].value)

        if shake_speed:
            if len(shake_speed) == 2:
                assert not slot_number or len(slot_number) != 2
                assert not shake_angle or len(shake_angle) != 2
                self._define_as_dynamic_value(shake_speed[0].value, shake_speed[1].value)

        if shake_angle:
            if len(shake_angle) == 2:
                assert not slot_number or len(slot_number) != 2
                assert not shake_speed or len(shake_speed) != 2
                self._define_as_dynamic_value(shake_angle[0].value, shake_angle[1].value)

    def __str__(self):
        return self.args_to_str(self.wheel, self.slot_number, self.shake_speed, self.shake_angle, self.is_shaking)


class WheelSlotRotation(Capability):
    def __init__(self, name: str,
                 wheel: str | List[str] | None = None,
                 slot_number: SlotNumber | None = None,
                 speed: List[RotationSpeed] | None = None,
                 angle: List[RotationAngle] | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.wheel = wheel or name
        self.slot_number = slot_number

        if speed:
            assert not angle
            self._define_from_entity(*speed)
        elif angle:
            self._define_from_entity(*angle)

    def __str__(self):
        return self.args_to_str(self.wheel, self.slot_number)


class WheelRotation(Capability):
    def __init__(self, name: str,
                 wheel: str | List[str] | None = None,
                 speed: List[RotationSpeed] | None = None,
                 angle: List[RotationAngle] | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.wheel = wheel or name
        self.speed = speed
        self.angle = angle

        if speed:
            assert not angle
            self._define_from_entity(*speed)
        elif angle:
            self._define_from_entity(*angle)

    def __str__(self):
        return self.args_to_str(self.wheel, self.speed, self.angle)


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
        super().__init__(**kwargs)

        assert effect_name or effect_preset
        self.effect_name = effect_name
        self.effect_preset = effect_preset
        self.sound_controlled = sound_controlled
        self.speed = speed
        self.duration = duration
        self.parameter = parameter
        self.sound_sensitivity = sound_sensitivity

        if speed:
            if len(self.speed) == 2:
                assert not duration or len(duration) != 2
                assert not parameter or len(parameter) != 2
                assert not sound_sensitivity or len(sound_sensitivity) != 2
                self._define_as_dynamic_value(speed[0].value, speed[1].value)
        if duration:
            if len(self.duration) == 2:
                assert not speed or len(speed) != 2
                assert not parameter or len(parameter) != 2
                assert not sound_sensitivity or len(sound_sensitivity) != 2
                self._define_as_dynamic_value(duration[0].value, duration[1].value)

        if parameter:
            if len(self.parameter) == 2:
                assert not speed or len(speed) != 2
                assert not duration or len(duration) != 2
                assert not sound_sensitivity or len(sound_sensitivity) != 2
                self._define_as_dynamic_value(parameter[0].value, parameter[1].value)

        if sound_sensitivity:
            if len(self.sound_sensitivity) == 2:
                assert not speed or len(speed) != 2
                assert not duration or len(duration) != 2
                assert not parameter or len(parameter) != 2
                self._define_as_dynamic_value(sound_sensitivity[0].value, sound_sensitivity[1].value)

    def __str__(self):
        return self.args_to_str(self.effect_name, self.effect_preset, self.speed, self.duration, self.parameter,
                                "sound controlled" if self.sound_controlled else None,
                                self.sound_sensitivity
                                )


class BeamAngle(Capability):
    def __init__(self, angle: List[entity.BeamAngle], **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(*angle)

    def __str__(self):
        return self.args_to_str(self.angle)


class BeamPosition(Capability):
    def __init__(self, name: str,
                 horizontal_angle: List[HorizontalAngle] | None = None,
                 vertical_angle: List[VerticalAngle] | None = None,
                 **kwargs):
        super().__init__(**kwargs)

        assert horizontal_angle or vertical_angle
        self.horizontal_angle = horizontal_angle
        self.vertical_angle = vertical_angle

        if horizontal_angle:
            if len(horizontal_angle) == 2:
                assert not vertical_angle or len(vertical_angle) != 2
                self._define_from_entity(*horizontal_angle)

        if vertical_angle:
            if len(vertical_angle) == 2:
                assert not horizontal_angle or len(horizontal_angle) != 2
                self._define_from_entity(*vertical_angle)

    def __str__(self):
        return self.args_to_str(self.horizontal_angle, self.vertical_angle)


class EffectSpeed(Capability):
    def __init__(self, speed: List[entity.Speed], **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self._define_from_entity(*speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class EffectDuration(Capability):
    def __init__(self, duration: List[entity.Time], **kwargs):
        super().__init__(**kwargs)
        self.duration = duration
        self._define_from_entity(*duration)

    def __str__(self):
        return self.args_to_str(self.duration)


class EffectParameter(Capability):
    def __init__(self, parameter: List[Parameter], **kwargs):
        super().__init__(**kwargs)
        self.parameter = parameter
        self._define_from_entity(*parameter)

    def __str__(self):
        return self.args_to_str(self.parameter)


class SoundSensitivity(Capability):
    def __init__(self, sound_sensitivity: List[Percent], **kwargs):
        super().__init__(**kwargs)
        self.soundSensitivity = sound_sensitivity
        self._define_from_entity(*sound_sensitivity)

    def __str__(self):
        return self.args_to_str(self.soundSensitivity)


class Focus(Capability):
    def __init__(self, distance: List[Distance], **kwargs):
        super().__init__(**kwargs)
        self.distance = distance
        self._define_from_entity(*distance)

    def __str__(self):
        return self.args_to_str(self.distance)


class Zoom(Capability):
    def __init__(self, angle: List[entity.BeamAngle], **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(*angle)

    def __str__(self):
        return self.args_to_str(self.angle)


class Iris(Capability):
    def __init__(self, open_percent: List[IrisPercent], **kwargs):
        super().__init__(**kwargs)
        self.open_percent = open_percent
        self._define_from_entity(*open_percent)

    def __str__(self):
        return self.args_to_str(self.open_percent)


class IrisEffect(Capability):
    def __init__(self, effect_name: str, speed: List[entity.Speed] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.effect_name = effect_name
        self.speed = speed
        if speed:
            self._define_from_entity(*speed)

    def __str__(self):
        return self.args_to_str(self.effect_name, self.speed)


class Frost(Capability):
    def __init__(self, frost_intensity: List[Percent], **kwargs):
        super().__init__(**kwargs)
        self.frost_intensity = frost_intensity
        self._define_from_entity(*frost_intensity)

    def __str__(self):
        return self.args_to_str(self.frost_intensity)


class FrostEffect(Capability):
    def __init__(self, effect_name: str, speed: List[entity.Speed] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.effect_name = effect_name
        self.speed = speed

        if speed:
            self._define_from_entity(*speed)

    def __str__(self):
        return self.args_to_str(self.effect_name, self.speed)


class Prism(Capability):
    def __init__(self,
                 speed: List[RotationSpeed] | None = None,
                 angle: List[RotationAngle] | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self.angle = angle

        if speed:
            assert not angle
            self._define_from_entity(*speed)
        elif angle:
            self._define_from_entity(*angle)

    def __str__(self):
        return self.args_to_str(self.speed, self.angle)


class PrismRotation(Capability):
    def __init__(self,
                 speed: List[RotationSpeed] | None = None,
                 angle: List[RotationAngle] | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self.angle = angle

        if speed:
            assert not angle
            self._define_from_entity(*speed)
        else:
            assert angle
            self._define_from_entity(*angle)

    def __str__(self):
        return self.args_to_str(self.speed, self.angle)


class BladeInsertion(Capability):
    def __init__(self,
                 blade: BladePosition | int,
                 insertion: List[Insertion],
                 **kwargs):
        super().__init__(**kwargs)
        self.blade = blade
        self._define_from_entity(*insertion)

    def __str__(self):
        return self.args_to_str(self.blade)


class BladeRotation(Capability):
    def __init__(self,
                 blade: BladePosition | int,
                 angle: List[RotationAngle],
                 **kwargs):
        super().__init__(**kwargs)
        self.blade = blade
        self._define_from_entity(*angle)

    def __str__(self):
        return self.args_to_str(self.blade)


class BladeSystemRotation(Capability):
    def __init__(self,
                 angle: List[RotationAngle],
                 **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(*angle)

    def __str__(self):
        return self.args_to_str(self.angle)


class Fog(Capability):
    def __init__(self,
                 fog_type: FogTypeOutput | None = None,
                 fog_output: List[entity.FogOutput] | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.fog_type = fog_type
        self.fog_output = fog_output

        if fog_output:
            self._define_from_entity(*fog_output)

    def __str__(self):
        return self.args_to_str(self.fog_type, self.fog_output)


class FogOutput(Capability):
    def __init__(self,
                 fog_output: List[entity.FogOutput],
                 **kwargs):
        super().__init__(**kwargs)
        self.fog_output = fog_output
        self._define_from_entity(*fog_output)

    def __str__(self):
        return self.args_to_str(self.fog_output)


class FogType(Capability):
    def __init__(self,
                 fog_type: FogTypeOutput | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.fog_type = fog_type

    def __str__(self):
        return self.args_to_str(self.fog_type)


class Rotation(Capability):
    def __init__(self,
                 speed: List[RotationSpeed] | None = None,
                 angle: List[RotationAngle] | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        assert speed or angle
        self.speed = speed
        self.angle = angle

        if speed:
            self._define_from_entity(*speed)
        else:
            self._define_from_entity(*angle)

    def __str__(self):
        return self.args_to_str(self.speed, self.angle)


class Speed(Capability):
    def __init__(self,
                 speed: List[entity.Speed],
                 **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self._define_from_entity(*speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class Time(Capability):
    def __init__(self,
                 time: List[entity.Time],
                 **kwargs):
        super().__init__(**kwargs)
        self.time = time
        self._define_from_entity(*time)

    def __str__(self):
        return self.args_to_str(self.time)


class Maintenance(Capability):
    def __init__(self,
                 parameter: List[Parameter] | None = None,
                 hold: entity.Time | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.hold = hold
        self.parameter = parameter

        if parameter:
            self._define_from_entity(*parameter)

    def __str__(self):
        return self.args_to_str(self.hold, self.parameter)


class Generic(Capability):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
