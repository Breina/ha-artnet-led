import logging
from typing import Tuple, Dict

from homeassistant.components.light import ColorMode

from custom_components.dmx.entity.light import ChannelType, ChannelMapping
from custom_components.dmx.entity.light.color_converter import ColorConverter

log = logging.getLogger(__name__)


class LuvLightState:
    """
    Light state that stores color values internally in L*u*v* color space.
    L* is used for brightness, while u* and v* represent chromaticity.
    """

    def __init__(self, color_mode: ColorMode, converter: ColorConverter, channels: Dict[ChannelType, ChannelMapping]):
        self.color_mode = color_mode
        self.converter = converter
        self.channels = channels

        # Core state
        self.is_on = False

        # Internal L*u*v* storage
        # L* range: 0-100 (brightness)
        # u* range: typically -134 to 220
        # v* range: typically -140 to 122
        self._luv_color = (50.0, 0.0, 0.0)  # Default: mid-brightness, no chroma
        self._last_luv_color = (50.0, 0.0, 0.0)

        # White channel values (still in 0-255 range for simplicity)
        self._cold_white = 255
        self._warm_white = 255
        self._last_cold_white = 255
        self._last_warm_white = 255

        # Color temperature (Kelvin)
        self._color_temp_kelvin = 3000
        self._color_temp_dmx = 255
        self._last_color_temp_kelvin = 3000
        self._last_color_temp_dmx = 255

        self._channel_handlers = {
            ChannelType.DIMMER: self._handle_dimmer_update,
            ChannelType.RED: lambda v: self._handle_rgb_component_update(0, v),
            ChannelType.GREEN: lambda v: self._handle_rgb_component_update(1, v),
            ChannelType.BLUE: lambda v: self._handle_rgb_component_update(2, v),
            ChannelType.COLD_WHITE: self._handle_cold_white_update,
            ChannelType.WARM_WHITE: self._handle_warm_white_update,
            ChannelType.COLOR_TEMPERATURE: self.update_color_temp_dmx,
        }

    # Utility methods
    def has_channel(self, t: ChannelType) -> bool:
        return t in self.channels

    def has_rgb(self) -> bool:
        return all(t in self.channels for t in [ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE])

    def has_cw_ww(self) -> bool:
        return all(t in self.channels for t in [ChannelType.COLD_WHITE, ChannelType.WARM_WHITE])

    def _has_dimmer(self) -> bool:
        return self.has_channel(ChannelType.DIMMER)

    # L*u*v* to RGB conversion helpers
    def _luv_to_rgb_255(self, luv: Tuple[float, float, float]) -> Tuple[int, int, int]:
        """Convert L*u*v* to RGB in [0, 255] range."""
        from custom_components.dmx.entity.light.color_calculator import ColorSpaceConverter

        rgb_float = ColorSpaceConverter.luv_to_rgb(luv)
        return tuple(max(0, min(255, round(c * 255))) for c in rgb_float)

    def _rgb_255_to_luv(self, rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
        """Convert RGB in [0, 255] range to L*u*v*."""
        from custom_components.dmx.entity.light.color_calculator import ColorSpaceConverter

        rgb_float = tuple(c / 255.0 for c in rgb)
        return ColorSpaceConverter.rgb_to_luv(rgb_float)

    # Properties that expose values in Home Assistant's expected [0, 255] range
    @property
    def brightness(self) -> int:
        """Get brightness as L* converted to [0, 255] range."""
        l_star = self._luv_color[0]
        return max(0, min(255, round(l_star * 255 / 100)))

    @brightness.setter
    def brightness(self, value: int):
        """Set brightness from [0, 255] range, converting to L*."""
        l_star = (value / 255.0) * 100
        self._luv_color = (l_star, self._luv_color[1], self._luv_color[2])

    @property
    def rgb(self) -> Tuple[int, int, int]:
        """Get RGB values in [0, 255] range from L*u*v*."""
        return self._luv_to_rgb_255(self._luv_color)

    @property
    def cold_white(self) -> int:
        return self._cold_white

    @property
    def warm_white(self) -> int:
        return self._warm_white

    @property
    def color_temp_kelvin(self) -> int:
        return self._color_temp_kelvin

    @property
    def color_temp_dmx(self) -> int:
        return self._color_temp_dmx

    # Last state properties
    @property
    def last_brightness(self) -> int:
        l_star = self._last_luv_color[0]
        return max(0, min(255, round(l_star * 255 / 100)))

    @last_brightness.setter
    def last_brightness(self, value: int):
        l_star = (value / 255.0) * 100
        self._last_luv_color = (l_star, self._last_luv_color[1], self._last_luv_color[2])

    @property
    def last_rgb(self) -> Tuple[int, int, int]:
        return self._luv_to_rgb_255(self._last_luv_color)

    @last_rgb.setter
    def last_rgb(self, rgb: Tuple[int, int, int]):
        self._last_luv_color = self._rgb_255_to_luv(rgb)

    @property
    def last_cold_white(self) -> int:
        return self._last_cold_white

    @last_cold_white.setter
    def last_cold_white(self, value: int):
        self._last_cold_white = value

    @property
    def last_warm_white(self) -> int:
        return self._last_warm_white

    @last_warm_white.setter
    def last_warm_white(self, value: int):
        self._last_warm_white = value

    @property
    def last_color_temp_kelvin(self) -> int:
        return self._last_color_temp_kelvin

    @last_color_temp_kelvin.setter
    def last_color_temp_kelvin(self, value: int):
        self._last_color_temp_kelvin = value

    @property
    def last_color_temp_dmx(self) -> int:
        return self._last_color_temp_dmx

    @last_color_temp_dmx.setter
    def last_color_temp_dmx(self, value: int):
        self._last_color_temp_dmx = value

    # L*u*v* specific properties and methods
    @property
    def luv_color(self) -> Tuple[float, float, float]:
        """Get the internal L*u*v* color representation."""
        return self._luv_color

    @property
    def last_luv_color(self) -> Tuple[float, float, float]:
        """Get the last L*u*v* color representation."""
        return self._last_luv_color

    def set_luv_color(self, luv: Tuple[float, float, float]):
        """Set the internal L*u*v* color directly."""
        self._luv_color = luv

    def set_last_luv_color(self, luv: Tuple[float, float, float]):
        """Set the last L*u*v* color directly."""
        self._last_luv_color = luv

    # Channel update handlers
    def apply_channel_update(self, channel_type: ChannelType, value: int):
        if channel_type in self._channel_handlers:
            self._channel_handlers[channel_type](value)
            self._update_on_state_after_channel_update()

    def _handle_dimmer_update(self, value: int):
        """Handle dimmer updates by modifying only L* component."""
        l_star = (value / 255.0) * 100
        self._luv_color = (l_star, self._luv_color[1], self._luv_color[2])
        if value > 0:
            self._last_luv_color = self._luv_color
        self.is_on = value > 0

    def _handle_rgb_component_update(self, component_index: int, value: int):
        """Handle individual RGB component updates."""
        current_rgb = list(self.rgb)
        current_rgb[component_index] = value
        new_luv = self._rgb_255_to_luv(tuple(current_rgb))

        self._update_luv_based_on_color_mode(new_luv)

        if not self._has_dimmer():
            self._update_brightness_from_channels()

    def _handle_cold_white_update(self, value: int):
        self.update_cw(value)
        self._handle_white_brightness_and_temp_update()

    def _handle_warm_white_update(self, value: int):
        self.update_ww(value)
        self._handle_white_brightness_and_temp_update()

    def _handle_white_brightness_and_temp_update(self):
        if self.color_mode == ColorMode.COLOR_TEMP and not self._has_dimmer():
            old_brightness = self.brightness
            self._update_brightness_from_cw_ww()
            if self.brightness == 0 and old_brightness > 0:
                self.is_on = False
            self._update_color_temp_from_cw_ww()
        elif not self._has_dimmer():
            self._update_brightness_from_channels()

    # Update methods that work with Home Assistant's [0, 255] range
    def update_brightness(self, value: int):
        """Update brightness from HA's [0, 255] range, treating it as L*."""
        l_star = (value / 255.0) * 100
        self._luv_color = (l_star, self._luv_color[1], self._luv_color[2])
        if value > 0:
            self._last_luv_color = self._luv_color
            self.is_on = True

    def update_rgb(self, r: int, g: int, b: int):
        """Update RGB from HA's [0, 255] range."""
        new_luv = self._rgb_255_to_luv((r, g, b))
        self._luv_color = new_luv
        if any(c > 0 for c in (r, g, b)):
            self._last_luv_color = new_luv

    def update_rgbw(self, r: int, g: int, b: int, w: int):
        """Update RGBW values."""
        new_luv = self._rgb_255_to_luv((r, g, b))
        self._luv_color = new_luv
        self._warm_white = w
        if any(c > 0 for c in (r, g, b, w)):
            self._last_luv_color = new_luv
            self._last_warm_white = w

    def update_rgbww(self, r: int, g: int, b: int, cw: int, ww: int):
        """Update RGBWW values."""
        new_luv = self._rgb_255_to_luv((r, g, b))
        self._luv_color = new_luv
        self._cold_white = cw
        self._warm_white = ww
        if any(c > 0 for c in (r, g, b, ww, cw)):
            self._last_luv_color = new_luv
            self._last_cold_white = cw
            self._last_warm_white = ww

    def update_cw(self, cw: int):
        self._update_last_value_if_positive(cw, '_last_cold_white', '_cold_white')
        self._cold_white = cw

        if self.color_mode == ColorMode.COLOR_TEMP:
            self.update_whites(cw, self._warm_white)
        elif self.color_mode == ColorMode.RGBWW:
            current_rgb = self.rgb
            self.update_rgbww(current_rgb[0], current_rgb[1], current_rgb[2], cw, self._warm_white)
        elif self.color_mode != ColorMode.BRIGHTNESS:
            if self.color_mode != ColorMode.RGBW:  # RGBW doesn't use CW by convention
                pass  # Handle other modes as needed

    def update_ww(self, ww: int):
        self._update_last_value_if_positive(ww, '_last_warm_white', '_warm_white')

        if self.color_mode == ColorMode.BRIGHTNESS:
            self._warm_white = ww
        elif self.color_mode == ColorMode.COLOR_TEMP:
            self.update_whites(self._cold_white, ww)
        elif self.color_mode == ColorMode.RGBW:
            current_rgb = self.rgb
            self.update_rgbw(current_rgb[0], current_rgb[1], current_rgb[2], ww)
        elif self.color_mode == ColorMode.RGBWW:
            current_rgb = self.rgb
            self.update_rgbww(current_rgb[0], current_rgb[1], current_rgb[2], self._cold_white, ww)

    def update_whites(self, cold: int, warm: int):
        if cold > 0 or warm > 0:
            self._last_cold_white = cold
            self._last_warm_white = warm

        self._cold_white = cold
        self._warm_white = warm

    def update_color_temp_dmx(self, dmx_value: int):
        self._color_temp_dmx = dmx_value
        self._last_color_temp_dmx = dmx_value
        self._color_temp_kelvin = self.converter.dmx_to_kelvin(dmx_value)
        self._last_color_temp_kelvin = self._color_temp_kelvin

    def update_color_temp_kelvin(self, kelvin: int):
        self._color_temp_kelvin = kelvin
        self._last_color_temp_kelvin = kelvin
        self._color_temp_dmx = self.converter.kelvin_to_dmx(kelvin)
        self._last_color_temp_dmx = self._color_temp_dmx

    def _update_last_value_if_positive(self, value: int, last_attr: str, current_attr: str):
        if value > 0:
            setattr(self, last_attr, getattr(self, current_attr))

    def _update_luv_based_on_color_mode(self, new_luv: Tuple[float, float, float]):
        """Update L*u*v* color based on the current color mode."""
        if self.color_mode == ColorMode.RGB:
            self._luv_color = new_luv
        elif self.color_mode == ColorMode.RGBW:
            self._luv_color = new_luv
            # Keep existing warm white
        elif self.color_mode == ColorMode.RGBWW:
            self._luv_color = new_luv
            # Keep existing cold and warm white
        else:
            raise RuntimeError("Shouldn't be able to update RGB if color mode is not RGB, RGBW, or RGBWW.")

    # Brightness calculation methods
    def _update_brightness_from_channels(self):
        """Update brightness (L*) from channel values."""
        values = []

        if self.has_rgb():
            rgb = self.rgb
            values.extend(rgb)

        if self.has_channel(ChannelType.COLD_WHITE):
            values.append(self._cold_white)

        if self.has_channel(ChannelType.WARM_WHITE):
            values.append(self._warm_white)

        if values:
            max_val = max(values)
            old_l_star = self._luv_color[0]
            new_l_star = (max_val / 255.0) * 100
            self._luv_color = (new_l_star, self._luv_color[1], self._luv_color[2])

            if max_val > 0:
                self._last_luv_color = self._luv_color

            if new_l_star == 0 and old_l_star > 0:
                self.is_on = False
            elif new_l_star > 0 and not self.is_on:
                self.is_on = True

    def _update_brightness_from_cw_ww(self):
        """Update brightness from cold/warm white values."""
        if self.color_mode == ColorMode.COLOR_TEMP and self.has_cw_ww():
            brightness_255, _ = self.converter.cw_ww_to_brightness_temp(
                self._cold_white, self._warm_white
            )
            l_star = (brightness_255 / 255.0) * 100
            self._luv_color = (l_star, self._luv_color[1], self._luv_color[2])
            if brightness_255 > 0:
                self._last_luv_color = self._luv_color

    def _update_color_temp_from_cw_ww(self):
        """Update color temperature from cold/warm white values."""
        if self.color_mode == ColorMode.COLOR_TEMP and self.has_cw_ww():
            color_temp_kelvin = self.converter.cw_ww_to_temp(self._cold_white, self._warm_white)
            self.update_color_temp_kelvin(color_temp_kelvin)

    # State management methods
    def _update_on_state_after_channel_update(self):
        if not self._has_dimmer():
            if self.is_all_zero(False):
                self.is_on = False
            else:
                self._update_on_state_without_dimmer()
        else:
            self.is_on = self.brightness > 0

    def _update_on_state_without_dimmer(self):
        if self.color_mode == ColorMode.COLOR_TEMP and self.has_cw_ww():
            self.is_on = (self._cold_white > 0 or self._warm_white > 0)
        elif self.color_mode == ColorMode.RGBWW:
            rgb = self.rgb
            self.is_on = any(v > 0 for v in (*rgb, self._cold_white, self._warm_white))
        elif self.color_mode == ColorMode.RGBW:
            rgb = self.rgb
            self.is_on = any(v > 0 for v in (*rgb, self._warm_white))
        elif self.color_mode == ColorMode.RGB:
            rgb = self.rgb
            self.is_on = any(v > 0 for v in rgb)
        elif self.has_channel(ChannelType.COLD_WHITE):
            self.is_on = self._cold_white > 0
        elif self.has_channel(ChannelType.WARM_WHITE):
            self.is_on = self._warm_white > 0
        else:
            self.is_on = self.brightness > 0

    def get_scaled_brightness_updates(self, new_brightness: int) -> Dict[ChannelType, int]:
        """Get channel updates for brightness scaling."""
        updates: Dict[ChannelType, int] = {}

        if self._has_dimmer():
            updates[ChannelType.DIMMER] = new_brightness
            return updates

        if self.color_mode == ColorMode.COLOR_TEMP:
            # Convert new brightness to L* and use with current chromaticity
            new_l_star = (new_brightness / 255.0) * 100
            current_temp_kelvin = self._color_temp_kelvin
            cw, ww = self.converter.temp_to_cw_ww(current_temp_kelvin, new_brightness)
            updates[ChannelType.COLD_WHITE] = cw
            updates[ChannelType.WARM_WHITE] = ww
            return updates

        # For RGB modes, scale current L*u*v* to new brightness
        current_l_star = self._luv_color[0]
        new_l_star = (new_brightness / 255.0) * 100

        if current_l_star > 0:
            scale_factor = new_l_star / current_l_star

            # Scale the RGB values
            current_rgb = self.rgb
            scaled_rgb = tuple(min(255, max(0, round(c * scale_factor))) for c in current_rgb)

            if self.color_mode in [ColorMode.RGB, ColorMode.RGBW, ColorMode.RGBWW]:
                updates[ChannelType.RED] = scaled_rgb[0]
                updates[ChannelType.GREEN] = scaled_rgb[1]
                updates[ChannelType.BLUE] = scaled_rgb[2]

            if self.color_mode == ColorMode.RGBW:
                scaled_ww = min(255, max(0, round(self._warm_white * scale_factor)))
                updates[ChannelType.WARM_WHITE] = scaled_ww

            if self.color_mode == ColorMode.RGBWW:
                scaled_cw = min(255, max(0, round(self._cold_white * scale_factor)))
                scaled_ww = min(255, max(0, round(self._warm_white * scale_factor)))
                updates[ChannelType.COLD_WHITE] = scaled_cw
                updates[ChannelType.WARM_WHITE] = scaled_ww

        return updates

    def get_dmx_updates(self, values: Dict[ChannelType, int]) -> Dict[int, int]:
        """Convert channel values to DMX updates."""
        updates = {}
        for channel_type, val in values.items():
            if channel_type not in self.channels:
                continue

            mapping = self.channels[channel_type]
            [entity] = mapping.channel.capabilities[0].dynamic_entities
            norm_val = entity.normalize(val)
            dmx_values = entity.to_dmx_fine(norm_val, len(mapping.dmx_indexes))

            for i, dmx_index in enumerate(mapping.dmx_indexes):
                updates[dmx_index] = dmx_values[i]

        return updates

    def reset(self):
        """Reset all values to zero/off state."""
        self.brightness = 0
        self._luv_color = (0.0, 0.0, 0.0)
        self._cold_white = 0
        self._warm_white = 0
        self.is_on = False

    def is_all_zero(self, has_dimmer: bool) -> bool:
        """Check if all relevant values are zero."""
        if has_dimmer:
            return self.brightness == 0

        rgb = self.rgb
        return (rgb == (0, 0, 0) and
                self._cold_white == 0 and
                self._warm_white == 0)

    # RGBW/RGBWW color properties
    @property
    def rgbw_color(self) -> Tuple[int, int, int, int]:
        rgb = self.rgb
        return (*rgb, self._warm_white)

    @property
    def rgbww_color(self) -> Tuple[int, int, int, int, int]:
        rgb = self.rgb
        return (*rgb, self._cold_white, self._warm_white)

    @property
    def last_rgbw_color(self) -> Tuple[int, int, int, int]:
        rgb = self.last_rgb
        return (*rgb, self._last_warm_white)

    @property
    def last_rgbww_color(self) -> Tuple[int, int, int, int, int]:
        rgb = self.last_rgb
        return (*rgb, self._last_cold_white, self._last_warm_white)