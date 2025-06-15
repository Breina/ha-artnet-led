from typing import Tuple

from homeassistant.components.light import ColorMode

from custom_components.artnet_led.entity.light.color_converter import ColorConverter

import logging

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

    def update_rgb(self, r: int, g: int, b: int):
        self.rgb = (r, g, b)
        if any(c > 0 for c in (r, g, b)):
            self.last_rgb = self.rgb

    def update_white(self, value: int, is_cold: bool):
        if is_cold:
            self.cold_white = value
            if value > 0 or self.last_warm_white > 0:
                self.last_cold_white = value
        else:
            self.warm_white = value
            if value > 0 or self.last_cold_white > 0:
                self.last_warm_white = value

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
        if dmx_value > 0:
            self.last_color_temp_dmx = dmx_value
            self.color_temp = self.converter.dmx_to_mired(dmx_value)
            self.last_color_temp = self.color_temp

    def update_color_temp_mired(self, mireds: int):
        self.color_temp = mireds
        if mireds > 0:
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
