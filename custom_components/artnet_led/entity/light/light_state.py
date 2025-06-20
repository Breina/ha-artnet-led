import logging
from typing import Tuple

from homeassistant.components.light import ColorMode

from custom_components.artnet_led.entity.light.color_converter import ColorConverter

log = logging.getLogger(__name__)


class LightState:
    def __init__(self, color_mode: ColorMode, converter: ColorConverter):
        self.color_mode = color_mode
        self.converter = converter

        self.is_on = False
        self.brightness = 255
        self.rgb = (255, 255, 255)
        self.cold_white = 255
        self.warm_white = 255
        self.color_temp = 500
        self.color_temp_dmx = 255

        self.last_brightness = 255
        self.last_rgb = (255, 255, 255)
        self.last_cold_white = 255
        self.last_warm_white = 255
        self.last_color_temp = 500
        self.last_color_temp_dmx = 255

    def update_r(self, r: int):
        if self.color_mode == ColorMode.RGB:
            self.update_rgb(r, self.rgb[1], self.rgb[2])
        elif self.color_mode == ColorMode.RGBW:
            self.update_rgbw(r, self.rgb[1], self.rgb[2], self.warm_white)
        elif self.color_mode == ColorMode.RGBWW:
            self.update_rgbww(r, self.rgb[1], self.rgb[2], self.cold_white, self.warm_white)
        else:
            raise RuntimeError("Shouldn't be able to update R if color mode is not RGB, RGBW, or RGBWW.")

    def update_g(self, g: int):
        if self.color_mode == ColorMode.RGB:
            self.update_rgb(self.rgb[0], g, self.rgb[2])
        elif self.color_mode == ColorMode.RGBW:
            self.update_rgbw(self.rgb[0], g, self.rgb[2], self.warm_white)
        elif self.color_mode == ColorMode.RGBWW:
            self.update_rgbww(self.rgb[0], g, self.rgb[2], self.cold_white, self.warm_white)
        else:
            raise RuntimeError("Shouldn't be able to update G if color mode is not RGB, RGBW, or RGBWW.")

    def update_b(self, b: int):
        if self.color_mode == ColorMode.RGB:
            self.update_rgb(self.rgb[0], self.rgb[1], b)
        elif self.color_mode == ColorMode.RGBW:
            self.update_rgbw(self.rgb[0], self.rgb[1], b, self.warm_white)
        elif self.color_mode == ColorMode.RGBWW:
            self.update_rgbww(self.rgb[0], self.rgb[1], b, self.cold_white, self.warm_white)
        else:
            raise RuntimeError("Shouldn't be able to update B if color mode is not RGB, RGBW, or RGBWW.")

    def update_cw(self, cw: int):
        if self.color_mode == ColorMode.BRIGHTNESS:
            if cw > 0:
                self.last_cold_white = self.cold_white
            self.cold_white = cw
        if self.color_mode == ColorMode.COLOR_TEMP:
            self.update_whites(cw, self.warm_white)
        elif self.color_mode == ColorMode.RGBW:
            raise RuntimeError("By convention, in color mode RGBW, CW is not used.")
        elif self.color_mode == ColorMode.RGBWW:
            self.update_rgbww(self.rgb[0], self.rgb[1], self.rgb[2], cw, self.warm_white)
        else:
            raise RuntimeError("Shouldn't be able to update CW if color mode is not COLOR_TEMP, or RGBWW.")

    def update_ww(self, ww: int):
        if self.color_mode == ColorMode.BRIGHTNESS:
            if ww > 0:
                self.last_warm_white = self.warm_white
            self.warm_white = ww
        elif self.color_mode == ColorMode.COLOR_TEMP:
            self.update_whites(self.cold_white, ww)
        elif self.color_mode == ColorMode.RGBW:
            self.update_rgbw(self.rgb[0], self.rgb[1], self.rgb[2], ww)
        elif self.color_mode == ColorMode.RGBWW:
            self.update_rgbww(self.rgb[0], self.rgb[1], self.rgb[2], self.cold_white, ww)
        else:
            raise RuntimeError("Shouldn't be able to update CW if color mode is not COLOR_TEMP, RGBW or RGBWW.")

    def update_rgb(self, r: int, g: int, b: int):
        self.rgb = (r, g, b)
        if any(c > 0 for c in (r, g, b)):
            self.last_rgb = self.rgb

    def update_rgbw(self, r: int, g: int, b: int, w: int):
        self.rgb = (r, g, b)
        self.warm_white = w
        if any(c > 0 for c in (r, g, b, w)):
            self.last_rgb = self.rgb
            self.last_warm_white = w

    def update_rgbww(self, r: int, g: int, b: int, cw: int, ww: int):
        self.rgb = (r, g, b)
        self.cold_white = cw
        self.warm_white = ww
        if any(c > 0 for c in (r, g, b, ww, cw)):
            self.last_rgb = self.rgb
            self.last_cold_white = cw
            self.last_warm_white = ww

    def update_whites(self, cold: int, warm: int):
        if cold > 0 or warm > 0:
            self.last_cold_white = cold
            self.last_warm_white = warm

        self.cold_white = cold
        self.warm_white = warm

    def update_brightness(self, value: int):
        self.brightness = value
        if value > 0:
            self.last_brightness = value
            self.is_on = True

    def update_color_temp_dmx(self, dmx_value: int):
        self.color_temp_dmx = dmx_value
        self.last_color_temp_dmx = dmx_value
        self.color_temp = self.converter.dmx_to_mired(dmx_value)
        self.last_color_temp = self.color_temp

    def update_color_temp_mired(self, mireds: int):
        self.color_temp = mireds
        self.last_color_temp = mireds
        self.color_temp_dmx = self.converter.mired_to_dmx(mireds)
        self.last_color_temp_dmx = self.color_temp_dmx

    def reset(self):
        self.brightness = 0
        self.rgb = (0, 0, 0)
        self.cold_white = 0
        self.warm_white = 0
        self.is_on = False

    def is_all_zero(self, has_dimmer: bool) -> bool:
        if has_dimmer:
            return self.brightness == 0
        return (self.rgb == (0, 0, 0) and
                self.cold_white == 0 and
                self.warm_white == 0)

    @property
    def rgbw_color(self) -> Tuple[int, int, int, int]:
        return (*self.rgb, self.cold_white)

    @property
    def rgbww_color(self) -> Tuple[int, int, int, int, int]:
        return (*self.rgb, self.cold_white, self.warm_white)

    @property
    def last_rgbw_color(self) -> Tuple[int, int, int, int]:
        return (*self.last_rgb, self.last_cold_white)

    @property
    def last_rgbww_color(self) -> Tuple[int, int, int, int, int]:
        return (*self.last_rgb, self.last_cold_white, self.last_warm_white)
