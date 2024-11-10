"""
All capability definitions.
https://github.com/OpenLightingProject/open-fixture-library/blob/master/docs/capability-types.md

Most arguments, instance attributes and class names are directly mapped to
values of the fixture format. Therefore, we will excuse the python linter.
"""
# pylint: disable=too-many-lines, too-many-arguments
# pylint: disable=too-many-instance-attributes


from enum import Enum, auto
from typing import Callable, List

from custom_components.dmx.fixture import entity
from custom_components.dmx.fixture.entity import RotationAngle, RotationSpeed, \
    Brightness, SlotNumber, SwingAngle, Parameter, Percent, VerticalAngle, \
    HorizontalAngle, Distance, \
    IrisPercent, Insertion, Entity, ColorHex


class DmxValueResolution(Enum):
    """
    Defines the bit depth of the configured DMX values in the fixture;
    defaultValue, dmxStartValue, dmxEndValue, ...
    """
    _8BIT = 1
    _16BIT = 2
    _24BIT = 3


class MenuClick(Enum):
    """
    The menuClick property defines which DMX value to use if the whole
    capability is selected: start / center / end sets the channel's DMX value
    to the start / center / end of the range, respectively. hidden hides this
    capability from the trigger menu. This is one of those special features
    that are supported only by some lighting programs.

    Names match fixture format exactly.
    """
    # pylint: disable=invalid-name
    start = auto()
    center = auto()
    end = auto()
    hidden = auto()


class ShutterEffect(Enum):
    """
    Supported types of shutter effects. Names match fixture format exactly.
    """
    # pylint: disable=invalid-name
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
    """
    Supported types of colors. Names match fixture format exactly.
    """
    # pylint: disable=invalid-name
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
    """
    Supported types for wheels/slots. Names match fixture format exactly.
    """
    # pylint: disable=invalid-name
    wheel = auto()
    slot = auto()


class EffectPreset(Enum):
    """
    Supported effects. Names match fixture format exactly.
    """
    # pylint: disable=invalid-name
    ColorJump = auto()
    ColorFade = auto()


class BladePosition(Enum):
    """
    Supported blade positions. Names match fixture format exactly.
    """
    # pylint: disable=invalid-name
    Top = auto()
    Right = auto()
    Bottom = auto()
    Left = auto()


class FogTypeOutput(Enum):
    """
    Supported fog types. Names match fixture format exactly.
    """
    # pylint: disable=invalid-name
    Fog = auto()
    Haze = auto()


def _make_interpolater(from_range_min: float, from_range_max: float,
                       to_range_min: float, to_range_max: float) -> Callable[
    [float], float]:
    if from_range_min == from_range_max:
        return lambda _: to_range_min

    from_range = from_range_max - from_range_min
    to_range = to_range_max - to_range_min
    scale_factor = float(to_range) / float(from_range)

    def interp_fn(value: float) -> float:
        return int(to_range_min + (value - from_range_min) * scale_factor)

    return interp_fn


class DynamicMapping:
    """
    Maps one range to another range by linear interpolation.
    """

    def __init__(self, range_start: float, range_end: float, dmx_start: int,
                 dmx_end: int):
        super().__init__()

        self.__interpolate_to_dmx = _make_interpolater(
            range_start, range_end, dmx_start, dmx_end
        )
        self.__interpolate_from_dmx = _make_interpolater(
            dmx_start, dmx_end, range_start, range_end
        )

    def to_dmx(self, value: float) -> int:
        """
        Adapts an entity value into its corresponding DMX value.
        :param value: The entity value to be converted
        :return: The corresponding DMX value
        """
        return round(self.__interpolate_to_dmx(value))

    def from_dmx(self, value: int) -> float:
        """
        Adapts DMX value into its corresponding entity value.
        :param value: The DMX value to be converted.
        :return: The corresponding entity value
        """
        return self.__interpolate_from_dmx(value)


class DynamicEntity(DynamicMapping):
    """
    Entity which uses a DynamicMapping.
    """

    def __init__(self, entity_start: Entity, entity_end: Entity, dmx_start: int,
                 dmx_end: int):
        super().__init__(
            entity_start.value, entity_end.value,
            dmx_start, dmx_end
        )

        self.entity_start = entity_start
        self.entity_end = entity_end


class Capability:
    """
    A channel can do different things depending on which range its DMX value
    currently is in. Those ranges that can be triggered manually in many
     programs are called capabilities.
    """

    def __init__(self,
                 dmx_value_resolution: DmxValueResolution,
                 comment: str | None = None,
                 dmx_range: [int] = None,
                 menu_click: MenuClick | None = None,
                 switch_channels: dict[str, str] | None = None
                 ):
        super().__init__()

        if dmx_range is None:
            dmx_range = [0, pow(255, dmx_value_resolution.value)]

        assert len(dmx_range) == 2

        self.comment = comment
        self.dmx_range_start = dmx_range[0]
        self.dmx_range_end = dmx_range[1]

        self.menu_click = menu_click
        if self.menu_click:
            self.menu_click_value = {
                MenuClick.start.name: self.dmx_range_start,
                MenuClick.center.name: int(
                    (self.dmx_range_start + self.dmx_range_end) / 2),
                MenuClick.end.name: self.dmx_range_end,
                MenuClick.hidden.name: self.dmx_range_start
            }[menu_click.name]
        else:
            self.menu_click_value = None

        self.switch_channels = switch_channels or {}

        self.static_entities = []
        self.dynamic_entities: List[DynamicMapping] = []

    def is_dynamic_entity(self) -> bool:
        return len(self.dynamic_entities) != 0

    def is_applicable(self, dmx_value: int):
        """
        Tests whether or not the DMX value is within the range of this
        capability.
        :param dmx_value: The DMX value to be tested
        :return: True if the DMX value is within the bounds of this capability
        """
        return self.dmx_range_start <= dmx_value <= self.dmx_range_end

    def _define_from_range(self, start: float, end: float):
        self.dynamic_entities.append(
            DynamicMapping(
                start, end,
                self.dmx_range_start, self.dmx_range_end
            )
        )

    def _define_from_entity(self, entities: list[Entity] | None):
        if not entities:
            return

        size = len(entities)
        if size == 1:
            self.static_entities.append(entities[0])
        else:
            assert size == 2
            self.dynamic_entities.append(
                DynamicEntity(
                    entities[0], entities[1],
                    self.dmx_range_start, self.dmx_range_end
                )
            )

    def __str__(self):
        if self.comment:
            return self.comment
        if self.dmx_range_start and self.dmx_range_end:
            return f"[{self.dmx_range_start},{self.dmx_range_end}]"
        return "Capability"

    def __repr__(self):
        return self.__str__()

    def args_to_str(self, *args) -> str:
        """
        Helper function which turns arguments into a nice string.
        :param args: The argument(s) to be converted
        :return: A humanly readable string.
        """
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


class NoFunction(Capability):
    """
    A NoFunction capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __str__(self):
        return self.comment or "NoFunction"


class ShutterStrobe(Capability):
    """
    A ShutterStrobe capability.
    Class name and instance arguments match the fixture format exactly.
    """

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
    """
    A StrobeSpeed capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, speed: List[entity.Speed], **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self._define_from_entity(speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class StrobeDuration(Capability):
    """
    A StrobeDuration capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, duration: List[entity.Time], **kwargs):
        super().__init__(**kwargs)
        self.duration = duration
        self._define_from_entity(duration)

    def __str__(self):
        return self.args_to_str(self.duration)


class Intensity(Capability):
    """
    A Intensity capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, brightness: List[Brightness] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.brightness = brightness or [Brightness("off"),
                                         Brightness("bright")]
        self._define_from_entity(self.brightness)

    def __str__(self):
        return self.args_to_str(self.brightness)


class ColorIntensity(Capability):
    """
    A ColorIntensity capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, color: SingleColor,
                 brightness: List[Brightness] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.color = color
        self.brightness = brightness or [Brightness("off"),
                                         Brightness("bright")]
        self._define_from_entity(self.brightness)

    def __str__(self):
        return self.args_to_str(self.color, self.brightness)


class ColorPreset(Capability):
    """
    A ColorPreset capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self,
                 colors: List[List[str]] | None = None,
                 color_temperature: List[entity.ColorTemperature] | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.colors = colors
        self.color_temperature = color_temperature

        if colors and len(colors) == 2:
            # TODO this isn't ideal, how to map multiple color ranges at once?
            self._define_from_entity([
                ColorHex(0, colors[0][0]),
                ColorHex(100, colors[1][0])
            ])

        self._define_from_entity(color_temperature)

    def __str__(self):
        return self.args_to_str(self.colors, self.color_temperature)


class ColorTemperature(Capability):
    """
    A ColorTemperature capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, color_temperature: List[entity.ColorTemperature],
                 **kwargs):
        super().__init__(**kwargs)
        self.color_temperature = color_temperature
        self._define_from_entity(self.color_temperature)

    def __str__(self):
        return self.args_to_str(self.color_temperature)


class Pan(Capability):
    """
    A Pan capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, angle: List[RotationAngle], **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(angle)

    def __str__(self):
        return self.args_to_str(self.angle)


class PanContinuous(Capability):
    """
    A PanContinuous capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, speed: List[RotationSpeed], **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self._define_from_entity(speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class Tilt(Capability):
    """
    A Tilt capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, angle: List[RotationAngle], **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(angle)

    def __str__(self):
        return self.args_to_str(self.angle)


class TiltContinuous(Capability):
    """
    A TiltContinuous capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, speed: List[RotationSpeed], **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self._define_from_entity(speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class PanTiltSpeed(Capability):
    """
    A PanTiltSpeed capability.
    Class name and instance arguments match the fixture format exactly.
    """

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
    """
    A WheelSlot capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, name: str, slot_number: List[SlotNumber],
                 wheel: str = None, **kwargs):
        super().__init__(**kwargs)
        self.wheel = wheel or name
        self.slot_number = slot_number
        self._define_from_entity(slot_number)

    def __str__(self):
        return self.args_to_str(self.wheel, self.slot_number)


class WheelShake(Capability):
    """
    A WheelShake capability.
    Class name and instance arguments match the fixture format exactly.
    """

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
        return self.args_to_str(self.wheel, self.slot_number, self.shake_speed,
                                self.shake_angle, self.is_shaking)


class WheelSlotRotation(Capability):
    """
    A WheelSlotRotation capability.
    Class name and instance arguments match the fixture format exactly.
    """

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
    """
    A WheelRotation capability.
    Class name and instance arguments match the fixture format exactly.
    """

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
    """
    A Effect capability.
    Class name and instance arguments match the fixture format exactly.
    """

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
        return self.args_to_str(self.effect_name, self.effect_preset,
                                self.speed, self.duration, self.parameter,
                                "sound controlled" if self.sound_controlled else None,
                                self.sound_sensitivity
                                )


class BeamAngle(Capability):
    """
    A BeamAngle capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, angle: List[entity.BeamAngle], **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(angle)

    def __str__(self):
        return self.args_to_str(self.angle)


class BeamPosition(Capability):
    """
    A BeamPosition capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self,
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
    """
    A EffectSpeed capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, speed: List[entity.Speed], **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self._define_from_entity(speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class EffectDuration(Capability):
    """
    A EffectDuration capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, duration: List[entity.Time], **kwargs):
        super().__init__(**kwargs)
        self.duration = duration
        self._define_from_entity(duration)

    def __str__(self):
        return self.args_to_str(self.duration)


class EffectParameter(Capability):
    """
    A EffectParameter capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, parameter: List[Parameter], **kwargs):
        super().__init__(**kwargs)
        self.parameter = parameter
        self._define_from_entity(parameter)

    def __str__(self):
        return self.args_to_str(self.parameter)


class SoundSensitivity(Capability):
    """
    A SoundSensitivity capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, sound_sensitivity: List[Percent], **kwargs):
        super().__init__(**kwargs)
        self.sound_sensitivity = sound_sensitivity
        self._define_from_entity(sound_sensitivity)

    def __str__(self):
        return self.args_to_str(self.sound_sensitivity)


class Focus(Capability):
    """
    A Focus capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, distance: List[Distance], **kwargs):
        super().__init__(**kwargs)
        self.distance = distance
        self._define_from_entity(distance)

    def __str__(self):
        return self.args_to_str(self.distance)


class Zoom(Capability):
    """
    A Zoom capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, angle: List[entity.BeamAngle], **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(angle)

    def __str__(self):
        return self.args_to_str(self.angle)


class Iris(Capability):
    """
    A Iris capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, open_percent: List[IrisPercent], **kwargs):
        super().__init__(**kwargs)
        self.open_percent = open_percent
        self._define_from_entity(open_percent)

    def __str__(self):
        return self.args_to_str(self.open_percent)


class IrisEffect(Capability):
    """
    A IrisEffect capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, effect_name: str,
                 speed: List[entity.Speed] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.effect_name = effect_name
        self.speed = speed
        self._define_from_entity(speed)

    def __str__(self):
        return self.args_to_str(self.effect_name, self.speed)


class Frost(Capability):
    """
    A Frost capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, frost_intensity: List[Percent], **kwargs):
        super().__init__(**kwargs)
        self.frost_intensity = frost_intensity
        self._define_from_entity(frost_intensity)

    def __str__(self):
        return self.args_to_str(self.frost_intensity)


class FrostEffect(Capability):
    """
    A FrostEffect capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, effect_name: str,
                 speed: List[entity.Speed] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.effect_name = effect_name
        self.speed = speed
        self._define_from_entity(speed)

    def __str__(self):
        return self.args_to_str(self.effect_name, self.speed)


class Prism(Capability):
    """
    A Prism capability.
    Class name and instance arguments match the fixture format exactly.
    """

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
    """
    A PrismRotation capability.
    Class name and instance arguments match the fixture format exactly.
    """

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
    """
    A BladeInsertion capability.
    Class name and instance arguments match the fixture format exactly.
    """

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
    """
    A BladeRotation capability.
    Class name and instance arguments match the fixture format exactly.
    """

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
    """
    A BladeSystemRotation capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self,
                 angle: List[RotationAngle],
                 **kwargs):
        super().__init__(**kwargs)
        self.angle = angle
        self._define_from_entity(angle)

    def __str__(self):
        return self.args_to_str(self.angle)


class Fog(Capability):
    """
    A Fog capability.
    Class name and instance arguments match the fixture format exactly.
    """

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
    """
    A FogOutput capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self,
                 fog_output: List[entity.FogOutput],
                 **kwargs):
        super().__init__(**kwargs)
        self.fog_output = fog_output
        self._define_from_entity(fog_output)

    def __str__(self):
        return self.args_to_str(self.fog_output)


class FogType(Capability):
    """
    A FogType capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self,
                 fog_type: FogTypeOutput | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.fog_type = fog_type

    def __str__(self):
        return self.args_to_str(self.fog_type)


class Rotation(Capability):
    """
    A Rotation capability.
    Class name and instance arguments match the fixture format exactly.
    """

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
    """
    A Speed capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self,
                 speed: List[entity.Speed],
                 **kwargs):
        super().__init__(**kwargs)
        self.speed = speed
        self._define_from_entity(speed)

    def __str__(self):
        return self.args_to_str(self.speed)


class Time(Capability):
    """
    A Time capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self,
                 time: List[entity.Time],
                 **kwargs):
        super().__init__(**kwargs)
        self.time = time
        self._define_from_entity(time)

    def __str__(self):
        return self.args_to_str(self.time)


class Maintenance(Capability):
    """
    A Maintenance capability.
    Class name and instance arguments match the fixture format exactly.
    """

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
    """
    A Generic capability.
    Class name and instance arguments match the fixture format exactly.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
