import logging
from typing import Tuple, Dict

from homeassistant.components.light import ColorMode

from custom_components.dmx.entity.light import ChannelType, ChannelMapping
from custom_components.dmx.entity.light.color_converter import ColorConverter

log = logging.getLogger(__name__)


class LightState:
    def __init__(self, color_mode: ColorMode, converter: ColorConverter, channels: Dict[ChannelType, ChannelMapping]):
        self.color_mode = color_mode
        self.converter = converter
        self.channels = channels

        self.is_on = False
        self.brightness = 255
        self.cold_white = 255
        self.warm_white = 255
        self.color_temp_kelvin = 3000
        self.color_temp_dmx = 255

        self.last_brightness = 255
        self.last_cold_white = 255
        self.last_warm_white = 255
        self.last_color_temp_kelvin = 3000
        self.last_color_temp_dmx = 255
        
        self.rgb = (255, 255, 255)
        self.last_rgb = (255, 255, 255)
        
        # Flag to prevent updating last_* values during animations
        self._preserve_last_values = False

        self._channel_handlers = {}

        if ChannelType.DIMMER in channels:
            self._channel_handlers[ChannelType.DIMMER] = self._handle_dimmer_update
            
        if ChannelType.RED in channels:
            self._channel_handlers[ChannelType.RED] = lambda v: self._handle_rgb_component_update(0, v)
        if ChannelType.GREEN in channels:
            self._channel_handlers[ChannelType.GREEN] = lambda v: self._handle_rgb_component_update(1, v)
        if ChannelType.BLUE in channels:
            self._channel_handlers[ChannelType.BLUE] = lambda v: self._handle_rgb_component_update(2, v)
            
        if ChannelType.COLD_WHITE in channels:
            self._channel_handlers[ChannelType.COLD_WHITE] = self._handle_cold_white_update
        if ChannelType.WARM_WHITE in channels:
            self._channel_handlers[ChannelType.WARM_WHITE] = self._handle_warm_white_update
        if ChannelType.COLOR_TEMPERATURE in channels:
            self._channel_handlers[ChannelType.COLOR_TEMPERATURE] = self.update_color_temp_dmx

    def has_channel(self, t: ChannelType) -> bool:
        return t in self.channels

    def has_rgb(self) -> bool:
        return all(t in self.channels for t in [ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE])

    def has_cw_ww(self) -> bool:
        return all(t in self.channels for t in [ChannelType.COLD_WHITE, ChannelType.WARM_WHITE])

    def _has_dimmer(self) -> bool:
        return self.has_channel(ChannelType.DIMMER)

    def apply_channel_update(self, channel_type: ChannelType, value: int):
        if channel_type in self._channel_handlers:
            self._channel_handlers[channel_type](value)
            self._update_on_state_after_channel_update()

    def _handle_dimmer_update(self, value: int):
        self.update_brightness(value)
        self.is_on = value > 0

    def _handle_rgb_component_update(self, component_index: int, value: int):
        # This should only be called for RGB color modes
        if self.color_mode not in [ColorMode.RGB, ColorMode.RGBW, ColorMode.RGBWW]:
            log.warning(f"RGB component update called for non-RGB color mode {self.color_mode}")
            return
            
        new_rgb = list(self.rgb)
        new_rgb[component_index] = value
        self._update_rgb_based_on_color_mode(*new_rgb)

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
            self.is_on = (self.cold_white > 0 or self.warm_white > 0)
        elif self.color_mode == ColorMode.RGBWW:
            rgb = self.rgb or (0, 0, 0)
            self.is_on = any(v > 0 for v in (*rgb, self.cold_white, self.warm_white))
        elif self.color_mode == ColorMode.RGBW:
            rgb = self.rgb or (0, 0, 0)
            self.is_on = any(v > 0 for v in (*rgb, self.warm_white))
        elif self.color_mode == ColorMode.RGB:
            rgb = self.rgb or (0, 0, 0)
            self.is_on = any(v > 0 for v in rgb)
        elif self.has_channel(ChannelType.COLD_WHITE):
            self.is_on = self.cold_white > 0
        elif self.has_channel(ChannelType.WARM_WHITE):
            self.is_on = self.warm_white > 0
        else:
            self.is_on = self.brightness > 0

    def get_scaled_brightness_updates(self, new_brightness: int) -> Dict[ChannelType, int]:
        updates: Dict[ChannelType, int] = {}

        if self._has_dimmer():
            updates[ChannelType.DIMMER] = new_brightness
            return updates

        if self.color_mode == ColorMode.COLOR_TEMP:
            cw, ww = self.converter.temp_to_cw_ww(self.color_temp_kelvin, new_brightness)
            updates[ChannelType.COLD_WHITE] = cw
            updates[ChannelType.WARM_WHITE] = ww
            return updates

        channel_values = {}

        if self.color_mode in [ColorMode.RGB, ColorMode.RGBW, ColorMode.RGBWW]:
            channel_values[ChannelType.RED] = self.rgb[0]
            channel_values[ChannelType.GREEN] = self.rgb[1]
            channel_values[ChannelType.BLUE] = self.rgb[2]

        if self.color_mode == ColorMode.RGBW:
            channel_values[ChannelType.WARM_WHITE] = self.warm_white

        if self.color_mode == ColorMode.RGBWW:
            channel_values[ChannelType.COLD_WHITE] = self.cold_white
            channel_values[ChannelType.WARM_WHITE] = self.warm_white

        max_current = max(channel_values.values(), default=1)
        scale = new_brightness / max_current if max_current > 0 else 0

        for channel, value in channel_values.items():
            scaled = round(value * scale)
            updates[channel] = min(255, scaled)

        return updates

    def get_dmx_updates(self, values: Dict[ChannelType, int]) -> Dict[int, int]:
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

    def _update_rgb_based_on_color_mode(self, r: int, g: int, b: int):
        if self.color_mode == ColorMode.RGB:
            self.update_rgb(r, g, b)
        elif self.color_mode == ColorMode.RGBW:
            self.update_rgbw(r, g, b, self.warm_white)
        elif self.color_mode == ColorMode.RGBWW:
            self.update_rgbww(r, g, b, self.cold_white, self.warm_white)
        else:
            raise RuntimeError("Shouldn't be able to update RGB if color mode is not RGB, RGBW, or RGBWW.")

    def update_cw(self, cw: int):
        self._update_last_value_if_positive(cw, 'last_cold_white', 'cold_white')
        self.cold_white = cw

        if self.color_mode == ColorMode.COLOR_TEMP:
            self.update_whites(cw, self.warm_white)
        elif self.color_mode == ColorMode.RGBW:
            raise RuntimeError("By convention, in color mode RGBW, CW is not used.")
        elif self.color_mode == ColorMode.RGBWW:
            self.update_rgbww(self.rgb[0], self.rgb[1], self.rgb[2], cw, self.warm_white)
        elif self.color_mode != ColorMode.BRIGHTNESS:
            raise RuntimeError("Shouldn't be able to update CW if color mode is not COLOR_TEMP, BRIGHTNESS, or RGBWW.")

    def update_ww(self, ww: int):
        self._update_last_value_if_positive(ww, 'last_warm_white', 'warm_white')

        if self.color_mode == ColorMode.BRIGHTNESS:
            self.warm_white = ww
        elif self.color_mode == ColorMode.COLOR_TEMP:
            self.update_whites(self.cold_white, ww)
        elif self.color_mode == ColorMode.RGBW:
            self.update_rgbw(self.rgb[0], self.rgb[1], self.rgb[2], ww)
        elif self.color_mode == ColorMode.RGBWW:
            self.update_rgbww(self.rgb[0], self.rgb[1], self.rgb[2], self.cold_white, ww)
        else:
            raise RuntimeError("Shouldn't be able to update WW if color mode is not COLOR_TEMP, BRIGHTNESS, RGBW or RGBWW.")

    def _update_last_value_if_positive(self, value: int, last_attr: str, current_attr: str):
        if value > 0 and not self._preserve_last_values:
            setattr(self, last_attr, getattr(self, current_attr))

    def update_rgb(self, r: int, g: int, b: int):
        self.rgb = (r, g, b)
        if any(c > 0 for c in (r, g, b)) and not self._preserve_last_values:
            self.last_rgb = self.rgb

    def update_rgbw(self, r: int, g: int, b: int, w: int):
        self.rgb = (r, g, b)
        self.warm_white = w
        if any(c > 0 for c in (r, g, b, w)) and not self._preserve_last_values:
            self.last_rgb = self.rgb
            self.last_warm_white = w

    def update_rgbww(self, r: int, g: int, b: int, cw: int, ww: int):
        self.rgb = (r, g, b)
        self.cold_white = cw
        self.warm_white = ww
        if any(c > 0 for c in (r, g, b, ww, cw)) and not self._preserve_last_values:
            self.last_rgb = self.rgb
            self.last_cold_white = cw
            self.last_warm_white = ww

    def update_whites(self, cold: int, warm: int):
        if (cold > 0 or warm > 0) and not self._preserve_last_values:
            self.last_cold_white = cold
            self.last_warm_white = warm

        self.cold_white = cold
        self.warm_white = warm

    def update_brightness(self, value: int):
        if value is not None:
            self.brightness = value
            if value > 0 and not self._preserve_last_values:
                self.last_brightness = value

    def update_color_temp_dmx(self, dmx_value: int):
        self.color_temp_dmx = dmx_value
        if not self._preserve_last_values:
            self.last_color_temp_dmx = dmx_value
        self.color_temp_kelvin = self.converter.dmx_to_kelvin(dmx_value)
        if not self._preserve_last_values:
            self.last_color_temp_kelvin = self.color_temp_kelvin

    def update_color_temp_kelvin(self, kelvin: int):
        self.color_temp_kelvin = kelvin
        if not self._preserve_last_values:
            self.last_color_temp_kelvin = kelvin
        self.color_temp_dmx = self.converter.kelvin_to_dmx(kelvin)
        if not self._preserve_last_values:
            self.last_color_temp_dmx = self.color_temp_dmx

    def reset(self):
        self.brightness = 0
        self.cold_white = 0
        self.warm_white = 0
        self.is_on = False

    def is_all_zero(self, has_dimmer: bool) -> bool:
        if has_dimmer:
            return self.brightness == 0
        return (self.rgb == (0, 0, 0) and
                self.cold_white == 0 and
                self.warm_white == 0)

    def _update_brightness_from_channels(self):
        values = []

        if self.has_rgb() and self.rgb is not None:
            values.extend(self.rgb)

        if self.has_channel(ChannelType.COLD_WHITE):
            values.append(self.cold_white)

        if self.has_channel(ChannelType.WARM_WHITE):
            values.append(self.warm_white)

        if values:
            max_val = max(values)
            old_brightness = self.brightness
            self.brightness = max_val
            if max_val > 0 and not self._preserve_last_values:
                self.last_brightness = max_val

            if max_val == 0 and old_brightness > 0:
                self.is_on = False
            elif max_val > 0 and not self.is_on:
                self.is_on = True

    def _update_brightness_from_cw_ww(self):
        if self.color_mode == ColorMode.COLOR_TEMP and self.has_cw_ww():
            brightness, _ = self.converter.cw_ww_to_brightness_temp(
                self.cold_white, self.warm_white
            )
            self.brightness = brightness
            if brightness > 0 and not self._preserve_last_values:
                self.last_brightness = brightness

    def _update_color_temp_from_cw_ww(self):
        if self.color_mode == ColorMode.COLOR_TEMP and self.has_cw_ww():
            color_temp_kelvin = self.converter.cw_ww_to_temp(self.cold_white, self.warm_white)
            self.update_color_temp_kelvin(color_temp_kelvin)

    @property
    def rgbw_color(self) -> Tuple[int, int, int, int]:
        rgb = self.rgb or (0, 0, 0)
        return (*rgb, self.warm_white)

    @property
    def rgbww_color(self) -> Tuple[int, int, int, int, int]:
        rgb = self.rgb or (0, 0, 0)
        return (*rgb, self.cold_white, self.warm_white)

    @property
    def last_rgbw_color(self) -> Tuple[int, int, int, int]:
        last_rgb = self.last_rgb or (0, 0, 0)
        return (*last_rgb, self.last_cold_white)

    @property
    def last_rgbww_color(self) -> Tuple[int, int, int, int, int]:
        last_rgb = self.last_rgb or (0, 0, 0)
        return (*last_rgb, self.last_cold_white, self.last_warm_white)
