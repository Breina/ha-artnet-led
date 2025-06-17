from typing import Dict, Any, Tuple

from homeassistant.components.light import ColorMode

from custom_components.artnet_led.entity.light import ChannelType
from custom_components.artnet_led.entity.light.channel_updater import ChannelUpdater
from custom_components.artnet_led.entity.light.light_state import LightState


class LightController:
    def __init__(self, state: LightState, updater: ChannelUpdater):
        self.state = state
        self.updater = updater
        self.is_updating = False

    async def turn_on(self, **kwargs):
        self.state.is_on = True
        updates = {}

        if not self._process_kwargs(kwargs, updates):
            self._restore_previous_state(updates)

        await self.__update_dmx_values(updates)

    async def turn_off(self):
        self.state.is_on = False

        preserved_state = self._capture_current_state()

        updates = {}

        if self.updater.has_channel(ChannelType.DIMMER):
            updates[ChannelType.DIMMER] = 0
            self.state.brightness = 0
        else:
            self.state.reset()
            for channel_type in self.updater.channels:
                if channel_type != ChannelType.COLOR_TEMPERATURE:
                    updates[channel_type] = 0

        await self.__update_dmx_values(updates)

        self._save_last_state(preserved_state)

    async def __update_dmx_values(self, unnormalized_updates):
        dmx_updates = {}
        for channel_type, denormalized_value in unnormalized_updates.items():
            channel_mapping = self.updater.channels[channel_type]
            [capability] = channel_mapping.channel.capabilities
            assert (len(capability.dynamic_entities) == 1)
            dynamic_entity = capability.dynamic_entities[0]

            normalized_value = dynamic_entity.normalize(denormalized_value)
            dmx_values = dynamic_entity.to_dmx_fine(normalized_value, num_channels=len(channel_mapping.dmx_indexes))

            for i in range(len(channel_mapping.dmx_indexes)):
                dmx_updates[channel_mapping.dmx_indexes[i]] = dmx_values[i]
        await self.updater.universe.update_multiple_values(dmx_updates)

    def _capture_current_state(self) -> dict:
        """Capture current state values that should be preserved"""
        return {
            'brightness': self.state.brightness if self.state.brightness > 0 else None,
            'rgb': self.state.rgb if any(c > 0 for c in self.state.rgb) else None,
            'cold_white': self.state.cold_white if self.state.cold_white > 0 else None,
            'warm_white': self.state.warm_white if self.state.warm_white > 0 else None,
            'color_temp': self.state.color_temp if self.state.color_temp > 0 else None,
            'color_temp_dmx': self.state.color_temp_dmx if self.state.color_temp_dmx > 0 else None,
        }

    def _save_last_state(self, preserved_state: dict):
        """Restore preserved state values to their last_ counterparts"""
        if preserved_state['brightness'] is not None:
            self.state.last_brightness = preserved_state['brightness']

        if preserved_state['rgb'] is not None:
            self.state.last_rgb = preserved_state['rgb']

        if preserved_state['cold_white'] is not None:
            self.state.last_cold_white = preserved_state['cold_white']

        if preserved_state['warm_white'] is not None:
            self.state.last_warm_white = preserved_state['warm_white']

        if preserved_state['color_temp'] is not None:
            self.state.last_color_temp = preserved_state['color_temp']

        if preserved_state['color_temp_dmx'] is not None:
            self.state.last_color_temp_dmx = preserved_state['color_temp_dmx']

    def _process_kwargs(self, kwargs: Dict[str, Any], updates: Dict[ChannelType, int]) -> bool:
        has_updates = False

        if "brightness" in kwargs and self.updater.has_channel(ChannelType.DIMMER):
            brightness = kwargs["brightness"]
            self.state.update_brightness(brightness)
            updates[ChannelType.DIMMER] = brightness
            has_updates = True

        if "rgb_color" in kwargs:
            self._handle_rgb_color(kwargs["rgb_color"], updates)
            has_updates = True

        if "rgbw_color" in kwargs:
            self._handle_rgbw_color(kwargs["rgbw_color"], updates)
            has_updates = True

        if "rgbww_color" in kwargs:
            self._handle_rgbww_color(kwargs["rgbww_color"], updates)
            has_updates = True

        if "color_temp" in kwargs:
            brightness = kwargs.get("brightness", self.state.brightness)
            self._handle_color_temp(kwargs["color_temp"], brightness, updates)
            has_updates = True

        if "brightness" in kwargs and not self.updater.has_channel(ChannelType.DIMMER):
            if self.state.color_mode == ColorMode.COLOR_TEMP and self.updater.has_cw_ww():
                brightness = kwargs["brightness"]
                self.state.update_brightness(brightness)
                if "color_temp" not in kwargs:
                    cold, warm = self.state.converter.temp_to_cw_ww(self.state.color_temp, brightness)
                    self.state.update_whites(cold, warm)
                    updates[ChannelType.COLD_WHITE] = cold
                    updates[ChannelType.WARM_WHITE] = warm
                has_updates = True

        return has_updates

    def _handle_rgb_color(self, rgb: Tuple[int, int, int], updates: Dict[ChannelType, int]):
        self.state.update_rgb(*rgb)
        if self.updater.has_rgb():
            updates[ChannelType.RED] = rgb[0]
            updates[ChannelType.GREEN] = rgb[1]
            updates[ChannelType.BLUE] = rgb[2]

    def _handle_rgbw_color(self, rgbw: Tuple[int, int, int, int], updates: Dict[ChannelType, int]):
        self.state.update_rgb(rgbw[0], rgbw[1], rgbw[2])
        self.state.update_white(rgbw[3], is_cold=True)

        if self.updater.has_rgb():
            updates[ChannelType.RED] = rgbw[0]
            updates[ChannelType.GREEN] = rgbw[1]
            updates[ChannelType.BLUE] = rgbw[2]

        if self.updater.has_channel(ChannelType.COLD_WHITE):
            updates[ChannelType.COLD_WHITE] = rgbw[3]

    def _handle_rgbww_color(self, rgbww: Tuple[int, int, int, int, int], updates: Dict[ChannelType, int]):
        self.state.update_rgb(rgbww[0], rgbww[1], rgbww[2])
        self.state.update_whites(rgbww[3], rgbww[4])

        if self.updater.has_rgb():
            updates[ChannelType.RED] = rgbww[0]
            updates[ChannelType.GREEN] = rgbww[1]
            updates[ChannelType.BLUE] = rgbww[2]

        if self.updater.has_channel(ChannelType.COLD_WHITE):
            updates[ChannelType.COLD_WHITE] = rgbww[3]

        if self.updater.has_channel(ChannelType.WARM_WHITE):
            updates[ChannelType.WARM_WHITE] = rgbww[4]

    def _handle_color_temp(self, temp_mired: int, brightness: int, updates: Dict[ChannelType, int]):
        self.state.update_color_temp_mired(temp_mired)

        # Update brightness when setting color temp
        if not self.updater.has_channel(ChannelType.DIMMER):
            self.state.update_brightness(brightness)

        if self.updater.has_channel(ChannelType.COLOR_TEMPERATURE):
            updates[ChannelType.COLOR_TEMPERATURE] = self.state.color_temp_dmx
        elif self.updater.has_cw_ww():
            cold, warm = self.state.converter.temp_to_cw_ww(temp_mired, brightness)
            self.state.update_whites(cold, warm)
            updates[ChannelType.COLD_WHITE] = cold
            updates[ChannelType.WARM_WHITE] = warm

    def _restore_previous_state(self, updates: Dict[ChannelType, int]):
        has_dimmer = self.updater.has_channel(ChannelType.DIMMER)

        if has_dimmer:
            updates[ChannelType.DIMMER] = self.state.last_brightness

        if self.state.color_mode in (ColorMode.RGB, ColorMode.RGBW, ColorMode.RGBWW) and self.updater.has_rgb():
            updates[ChannelType.RED] = self.state.last_rgb[0]
            updates[ChannelType.GREEN] = self.state.last_rgb[1]
            updates[ChannelType.BLUE] = self.state.last_rgb[2]

        if self.state.color_mode in (ColorMode.RGBW, ColorMode.RGBWW, ColorMode.COLOR_TEMP):
            if self.updater.has_channel(ChannelType.COLD_WHITE):
                updates[ChannelType.COLD_WHITE] = self.state.last_cold_white
            if self.updater.has_channel(ChannelType.WARM_WHITE):
                updates[ChannelType.WARM_WHITE] = self.state.last_warm_white

        if self.updater.has_channel(ChannelType.COLOR_TEMPERATURE):
            updates[ChannelType.COLOR_TEMPERATURE] = self.state.last_color_temp_dmx

        if not has_dimmer and self.state.color_mode == ColorMode.BRIGHTNESS:
            brightness = self.state.last_brightness
            if self.updater.has_channel(ChannelType.COLD_WHITE):
                updates[ChannelType.COLD_WHITE] = brightness
            elif self.updater.has_channel(ChannelType.WARM_WHITE):
                updates[ChannelType.WARM_WHITE] = brightness

    def handle_channel_update(self, channel_type: ChannelType, value: int):
        if self.is_updating:
            return False

        has_dimmer = self.updater.has_channel(ChannelType.DIMMER)

        if has_dimmer and channel_type == ChannelType.DIMMER:
            self.state.is_on = value > 0
        elif not has_dimmer and value > 0 and not self.state.is_on:
            self.state.is_on = True

        if channel_type == ChannelType.DIMMER:
            self.state.update_brightness(value)
            if value == 0:
                self.state.is_on = False
        elif channel_type == ChannelType.RED:
            self.state.update_rgb(value, self.state.rgb[1], self.state.rgb[2])
        elif channel_type == ChannelType.GREEN:
            self.state.update_rgb(self.state.rgb[0], value, self.state.rgb[2])
        elif channel_type == ChannelType.BLUE:
            self.state.update_rgb(self.state.rgb[0], self.state.rgb[1], value)
        elif channel_type == ChannelType.COLD_WHITE:
            self.state.update_white(value, is_cold=True)
            if self.state.color_mode == ColorMode.BRIGHTNESS and not has_dimmer:
                self.state.update_brightness(value)
                if value == 0:
                    self.state.is_on = False
            elif self.state.color_mode == ColorMode.COLOR_TEMP and not has_dimmer:
                old_brightness = self.state.brightness
                self._update_brightness_from_cw_ww()
                if self.state.brightness == 0 and old_brightness > 0:
                    self.state.is_on = False
                self._update_color_temp_from_cw_ww()
        elif channel_type == ChannelType.WARM_WHITE:
            self.state.update_white(value, is_cold=False)
            if self.state.color_mode == ColorMode.BRIGHTNESS and not has_dimmer:
                self.state.update_brightness(value)
                if value == 0:
                    self.state.is_on = False
            elif self.state.color_mode == ColorMode.COLOR_TEMP and not has_dimmer:
                old_brightness = self.state.brightness
                self._update_brightness_from_cw_ww()
                if self.state.brightness == 0 and old_brightness > 0:
                    self.state.is_on = False
                self._update_color_temp_from_cw_ww()
        elif channel_type == ChannelType.COLOR_TEMPERATURE:
            self.state.update_color_temp_dmx(value)

        if not has_dimmer:
            if self.state.is_all_zero(has_dimmer) and self.state.is_on:
                self.state.is_on = False

        return True

    def _update_brightness_from_cw_ww(self):
        """Calculate and update brightness based on current CW/WW values for color temp mode."""
        if self.state.color_mode == ColorMode.COLOR_TEMP and self.updater.has_cw_ww():
            brightness, _ = self.state.converter.cw_ww_to_brightness_temp(
                self.state.cold_white,
                self.state.warm_white
            )
            self.state.brightness = brightness
            if brightness > 0:
                self.state.last_brightness = brightness

    def _update_color_temp_from_cw_ww(self):
        """Calculate and update color temperature based on current CW/WW values."""
        if self.state.color_mode == ColorMode.COLOR_TEMP and self.updater.has_cw_ww():
            color_temp = self.state.converter.cw_ww_to_temp(self.state.cold_white, self.state.warm_white)
            self.state.update_color_temp_mired(color_temp)
