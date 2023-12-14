from enum import Enum, auto
from typing import Callable, List

from custom_components.dmx.fixture import entity
from custom_components.dmx.fixture.entity import RotationAngle, RotationSpeed, Brightness, SlotNumber, \
    SwingAngle, Parameter, Percent, VerticalAngle, HorizontalAngle, Distance, IrisPercent, Insertion, Entity


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


class DmxValueResolution(Enum):
    _8bit = 1
    _16bit = 2
    _24bit = 3


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


class DynamicMapping:
    def __init__(self, range_start: float, range_end: float, dmx_start: int, dmx_end: int):
        super().__init__()

        self.__interpolate_to_dmx = _make_interpolater(
            range_start, range_end, dmx_start, dmx_end
        )
        self.__interpolate_from_dmx = _make_interpolater(
            dmx_start, dmx_end, range_start, range_end
        )

    def to_dmx(self, value: float) -> int:
        return round(self.__interpolate_to_dmx(value))

    def from_dmx(self, value: int) -> float:
        return self.__interpolate_from_dmx(value)


class DynamicEntity(DynamicMapping):
    def __init__(self, entity_start: Entity, entity_end: Entity, dmx_start: int, dmx_end: int):
        super().__init__(entity_start.value, entity_end.value, dmx_start, dmx_end)

        self.entity_start = entity_start
        self.entity_end = entity_end


class Capability:

    def __init__(self,
                 comment: str | None = None,
                 dmx_range: [int] = None,
                 menu_click: MenuClick = MenuClick.start,
                 fine_channel_aliases: List[str] = None,
                 default_value: int = 0,
                 dmx_value_resolution: DmxValueResolution | None = None,
                 switch_channels: dict[str, str] | None = None
                 ):
        super().__init__()

        self.fineChannelAliases = fine_channel_aliases or []
        self.defaultValue = default_value
        self.dmxValueResolution = dmx_value_resolution or DmxValueResolution(len(self.fineChannelAliases) + 1)

        if dmx_range is None:
            dmx_range = [0, pow(255, self.dmxValueResolution.value)]
        assert len(dmx_range) == 2

        self.comment = comment
        self.dmxRangeStart = dmx_range[0]
        self.dmxRangeEnd = dmx_range[1]

        self.menuClick = menu_click
        self.menuClickValue = {
            MenuClick.start.name: self.dmxRangeStart,
            MenuClick.center.name: int((self.dmxRangeStart + self.dmxRangeEnd) / 2),
            MenuClick.end.name: self.dmxRangeEnd,
            MenuClick.hidden.name: self.dmxRangeStart
        }[menu_click.name or MenuClick.start.name]

        self.switchChannels = switch_channels or {}

        self.static_entities = []
        self.dynamic_entities = []

    def is_applicable(self, dmx_value: int):
        return self.dmxRangeStart <= dmx_value <= self.dmxRangeEnd

    def _define_from_range(self, start: float, end: float):
        self.dynamic_entities.append(DynamicMapping(start, end, self.dmxRangeStart, self.dmxRangeEnd))

    def _define_from_entity(self, entities: list[Entity] | None):
        if not entities:
            return

        size = len(entities)
        if size == 1:
            self.static_entities.append(entities[0])
        else:
            assert size == 2
            self.dynamic_entities.append(DynamicEntity(entities[0], entities[1], self.dmxRangeStart, self.dmxRangeEnd))

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

        self._define_from_entity(speed)
        self._define_from_entity(duration)

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
        self._define_from_entity(speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class StrobeDuration(Capability):
    def __init__(self, duration: List[entity.Time], **kwargs):
        super().__init__(**kwargs)
        self.duration = duration
        self._define_from_entity(duration)

    def __str__(self):
        return self.args_to_str(self.duration)


class Intensity(Capability):
    def __init__(self, brightness: List[Brightness] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.brightness = brightness or [Brightness("off"), Brightness("bright")]
        self._define_from_entity(self.brightness)

    def __str__(self):
        return self.args_to_str(self.brightness)


class ColorIntensity(Capability):
    def __init__(self, color: SingleColor, brightness: List[Brightness] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.color = color
        self.brightness = brightness or [Brightness("off"), Brightness("bright")]
        self._define_from_entity(self.brightness)

    def __str__(self):
        return self.args_to_str(self.color, self.brightness)


class ColorPreset(Capability):
    def __init__(self,
                 colors: List[List[str]] | None = None,
                 color_temperature: List[entity.ColorTemperature] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.colors = colors
        self.color_temperature = color_temperature

        if colors and len(colors) == 2:
            self._define_from_range(0, 100)

        self._define_from_entity(color_temperature)

    def __str__(self):
        return self.args_to_str(self.colors, self.color_temperature)


class ColorTemperature(Capability):
    def __init__(self, color_temperature: List[entity.ColorTemperature], **kwargs):
        super().__init__(**kwargs)
        self.color_temperature = color_temperature
        self._define_from_entity(self.color_temperature)

    def __str__(self):
        return self.args_to_str(self.color_temperature)


class Pan(Capability):
    def __init__(self, angle: List[RotationAngle], **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(angle)

    def __str__(self):
        return self.args_to_str(self.angle)


class PanContinuous(Capability):
    def __init__(self, speed: List[RotationSpeed], **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self._define_from_entity(speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class Tilt(Capability):
    def __init__(self, angle: List[RotationAngle], **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(angle)

    def __str__(self):
        return self.args_to_str(self.angle)


class TiltContinuous(Capability):
    def __init__(self, speed: List[RotationSpeed], **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self._define_from_entity(speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class PanTiltSpeed(Capability):
    def __init__(self,
                 speed: List[entity.Speed] | None,
                 duration: List[entity.Time] | None,
                 **kwargs):
        super().__init__(**kwargs)
        assert bool(speed) != bool(duration)
        self.speed = speed
        self.duration = duration

        self._define_from_entity(speed)
        self._define_from_entity(duration)

    def __str__(self):
        return self.args_to_str(self.speed, self.duration)


class WheelSlot(Capability):
    def __init__(self, name: str, slot_number: List[SlotNumber], wheel: str = None, **kwargs):
        super().__init__(**kwargs)
        self.wheel = wheel or name
        self.slot_number = slot_number
        self._define_from_entity(slot_number)

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

        self._define_from_entity(slot_number)
        self._define_from_entity(shake_speed)
        self._define_from_entity(shake_angle)

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
        assert bool(angle) != bool(speed)
        self.wheel = wheel or name
        self.slot_number = slot_number

        self._define_from_entity(speed)
        self._define_from_entity(angle)

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

        self._define_from_entity(speed)
        self._define_from_entity(angle)

    def __str__(self):
        return self.args_to_str(self.wheel, self.speed, self.angle)


class Effect(Capability):
    def __init__(self,
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

        self._define_from_entity(speed)
        self._define_from_entity(duration)
        self._define_from_entity(parameter)
        self._define_from_entity(sound_sensitivity)

    def __str__(self):
        return self.args_to_str(self.effect_name, self.effect_preset, self.speed, self.duration, self.parameter,
                                "sound controlled" if self.sound_controlled else None,
                                self.sound_sensitivity
                                )


class BeamAngle(Capability):
    def __init__(self, angle: List[entity.BeamAngle], **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(angle)

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

        self._define_from_entity(horizontal_angle)
        self._define_from_entity(vertical_angle)

    def __str__(self):
        return self.args_to_str(self.horizontal_angle, self.vertical_angle)


class EffectSpeed(Capability):
    def __init__(self, speed: List[entity.Speed], **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self._define_from_entity(speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class EffectDuration(Capability):
    def __init__(self, duration: List[entity.Time], **kwargs):
        super().__init__(**kwargs)
        self.duration = duration
        self._define_from_entity(duration)

    def __str__(self):
        return self.args_to_str(self.duration)


class EffectParameter(Capability):
    def __init__(self, parameter: List[Parameter], **kwargs):
        super().__init__(**kwargs)
        self.parameter = parameter
        self._define_from_entity(parameter)

    def __str__(self):
        return self.args_to_str(self.parameter)


class SoundSensitivity(Capability):
    def __init__(self, sound_sensitivity: List[Percent], **kwargs):
        super().__init__(**kwargs)
        self.soundSensitivity = sound_sensitivity
        self._define_from_entity(sound_sensitivity)

    def __str__(self):
        return self.args_to_str(self.soundSensitivity)


class Focus(Capability):
    def __init__(self, distance: List[Distance], **kwargs):
        super().__init__(**kwargs)
        self.distance = distance
        self._define_from_entity(distance)

    def __str__(self):
        return self.args_to_str(self.distance)


class Zoom(Capability):
    def __init__(self, angle: List[entity.BeamAngle], **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(angle)

    def __str__(self):
        return self.args_to_str(self.angle)


class Iris(Capability):
    def __init__(self, open_percent: List[IrisPercent], **kwargs):
        super().__init__(**kwargs)
        self.open_percent = open_percent
        self._define_from_entity(open_percent)

    def __str__(self):
        return self.args_to_str(self.open_percent)


class IrisEffect(Capability):
    def __init__(self, effect_name: str, speed: List[entity.Speed] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.effect_name = effect_name
        self.speed = speed
        self._define_from_entity(speed)

    def __str__(self):
        return self.args_to_str(self.effect_name, self.speed)


class Frost(Capability):
    def __init__(self, frost_intensity: List[Percent], **kwargs):
        super().__init__(**kwargs)
        self.frost_intensity = frost_intensity
        self._define_from_entity(frost_intensity)

    def __str__(self):
        return self.args_to_str(self.frost_intensity)


class FrostEffect(Capability):
    def __init__(self, effect_name: str, speed: List[entity.Speed] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.effect_name = effect_name
        self.speed = speed
        self._define_from_entity(speed)

    def __str__(self):
        return self.args_to_str(self.effect_name, self.speed)


class Prism(Capability):
    def __init__(self,
                 speed: List[RotationSpeed] | None = None,
                 angle: List[RotationAngle] | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        assert not (bool(speed) and bool(angle))
        self.speed = speed
        self.angle = angle

        self._define_from_entity(speed)
        self._define_from_entity(angle)

    def __str__(self):
        return self.args_to_str(self.speed, self.angle)


class PrismRotation(Capability):
    def __init__(self,
                 speed: List[RotationSpeed] | None = None,
                 angle: List[RotationAngle] | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        assert bool(speed) != bool(angle)
        self.speed = speed
        self.angle = angle

        self._define_from_entity(speed)
        self._define_from_entity(angle)

    def __str__(self):
        return self.args_to_str(self.speed, self.angle)


class BladeInsertion(Capability):
    def __init__(self,
                 blade: BladePosition | int,
                 insertion: List[Insertion],
                 **kwargs):
        super().__init__(**kwargs)
        self.blade = blade
        self._define_from_entity(insertion)

    def __str__(self):
        return self.args_to_str(self.blade)


class BladeRotation(Capability):
    def __init__(self,
                 blade: BladePosition | int,
                 angle: List[RotationAngle],
                 **kwargs):
        super().__init__(**kwargs)
        self.blade = blade
        self._define_from_entity(angle)

    def __str__(self):
        return self.args_to_str(self.blade)


class BladeSystemRotation(Capability):
    def __init__(self,
                 angle: List[RotationAngle],
                 **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(angle)

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
        self._define_from_entity(fog_output)

    def __str__(self):
        return self.args_to_str(self.fog_type, self.fog_output)


class FogOutput(Capability):
    def __init__(self,
                 fog_output: List[entity.FogOutput],
                 **kwargs):
        super().__init__(**kwargs)
        self.fog_output = fog_output
        self._define_from_entity(fog_output)

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
        assert bool(speed) != bool(angle)
        self.speed = speed
        self.angle = angle

        self._define_from_entity(speed)
        self._define_from_entity(angle)

    def __str__(self):
        return self.args_to_str(self.speed, self.angle)


class Speed(Capability):
    def __init__(self,
                 speed: List[entity.Speed],
                 **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self._define_from_entity(speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class Time(Capability):
    def __init__(self,
                 time: List[entity.Time],
                 **kwargs):
        super().__init__(**kwargs)
        self.time = time
        self._define_from_entity(time)

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
        self._define_from_entity(parameter)

    def __str__(self):
        return self.args_to_str(self.hold, self.parameter)


class Generic(Capability):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
