from typing import Dict, Any

from custom_components.dmx.entity.light import ChannelType
from custom_components.dmx.entity.light.light_state import LuvLightState
from custom_components.dmx.io.dmx_io import DmxUniverse


class LightController:
    def __init__(self, state: LuvLightState, universe: DmxUniverse):
        self.state = state
        self.universe = universe
        self.is_updating = False

    async def turn_on(self, **kwargs):
        self.state.is_on = True
        updates = self._collect_updates_from_kwargs(kwargs)
        if not updates:
            updates = self._restore_previous_state()
        await self._apply_updates(updates)

    async def turn_off(self):
        self.state.is_on = False
        preserved = self._capture_current_state()
        updates = {}

        if self.state.has_channel(ChannelType.DIMMER):
            self.state.update_brightness(0)
            updates[ChannelType.DIMMER] = 0
        else:
            self.state.reset()
            for channel in self.state.channels:
                if channel != ChannelType.COLOR_TEMPERATURE:
                    updates[channel] = 0

        await self._apply_updates(updates)
        self._save_last_state(preserved)

    async def _apply_updates(self, updates: Dict[ChannelType, int]):
        for ct, val in updates.items():
            self.state.apply_channel_update(ct, val)
        dmx_updates = self.state.get_dmx_updates(updates)
        await self.universe.update_multiple_values(dmx_updates)

    def _collect_updates_from_kwargs(self, kwargs: Dict[str, Any]) -> Dict[ChannelType, int]:
        updates = {}

        if "rgb_color" in kwargs and self.state.has_rgb():
            r, g, b = kwargs["rgb_color"]
            # Update the internal L*u*v* state
            self.state.update_rgb(r, g, b)
            updates.update({ChannelType.RED: r, ChannelType.GREEN: g, ChannelType.BLUE: b})

        if "rgbw_color" in kwargs:
            r, g, b, w = kwargs["rgbw_color"]
            # Update the internal L*u*v* state
            self.state.update_rgbw(r, g, b, w)
            updates.update({ChannelType.RED: r, ChannelType.GREEN: g, ChannelType.BLUE: b, ChannelType.WARM_WHITE: w})

        if "rgbww_color" in kwargs:
            r, g, b, cw, ww = kwargs["rgbww_color"]
            # Update the internal L*u*v* state
            self.state.update_rgbww(r, g, b, cw, ww)
            updates.update({ChannelType.RED: r, ChannelType.GREEN: g, ChannelType.BLUE: b, ChannelType.COLD_WHITE: cw, ChannelType.WARM_WHITE: ww})

        if "color_temp_kelvin" in kwargs:
            kelvin = kwargs["color_temp_kelvin"]
            self.state.update_color_temp_kelvin(kelvin)
            brightness = kwargs.get("brightness", self.state.brightness)

            if self.state.has_channel(ChannelType.COLOR_TEMPERATURE):
                updates[ChannelType.COLOR_TEMPERATURE] = self.state.color_temp_dmx
            elif self.state.has_cw_ww():
                cw, ww = self.state.converter.temp_to_cw_ww(kelvin, brightness)
                updates.update({ChannelType.COLD_WHITE: cw, ChannelType.WARM_WHITE: ww})

        if "brightness" in kwargs:
            brightness = kwargs["brightness"]
            # Treat brightness as L* value and update accordingly
            self.state.update_brightness(brightness)
            updates.update(self.state.get_scaled_brightness_updates(brightness))

        return updates

    def _restore_previous_state(self) -> Dict[ChannelType, int]:
        updates = {}
        if self.state.has_channel(ChannelType.DIMMER):
            updates[ChannelType.DIMMER] = self.state.last_brightness

        if self.state.has_rgb():
            r, g, b = self.state.last_rgb
            updates.update({ChannelType.RED: r, ChannelType.GREEN: g, ChannelType.BLUE: b})

        if self.state.has_channel(ChannelType.COLD_WHITE):
            updates[ChannelType.COLD_WHITE] = self.state.last_cold_white
        if self.state.has_channel(ChannelType.WARM_WHITE):
            updates[ChannelType.WARM_WHITE] = self.state.last_warm_white
        if self.state.has_channel(ChannelType.COLOR_TEMPERATURE):
            updates[ChannelType.COLOR_TEMPERATURE] = self.state.last_color_temp_dmx

        return updates

    def _capture_current_state(self) -> dict:
        return {
            'brightness': self.state.brightness,
            'luv_color': self.state.luv_color,
            'cold_white': self.state.cold_white,
            'warm_white': self.state.warm_white,
            'color_temp_kelvin': self.state.color_temp_kelvin,
            'color_temp_dmx': self.state.color_temp_dmx
        }

    def _save_last_state(self, s: dict):
        self.state.last_brightness = s['brightness']
        self.state.set_last_luv_color(s['luv_color'])
        self.state.last_cold_white = s['cold_white']
        self.state.last_warm_white = s['warm_white']
        self.state.last_color_temp_kelvin = s['color_temp_kelvin']
        self.state.last_color_temp_dmx = s['color_temp_dmx']