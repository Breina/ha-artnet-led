from functools import partial
from typing import Optional, List, Dict, Tuple, Any

from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util.color import color_temperature_kelvin_to_mired

from custom_components.artnet_led import DOMAIN
from custom_components.artnet_led.io.dmx_io import DmxUniverse
from custom_components.artnet_led.entity.light import ChannelMapping, ChannelType
from custom_components.artnet_led.entity.light.channel_updater import ChannelUpdater
from custom_components.artnet_led.entity.light.color_converter import ColorConverter
from custom_components.artnet_led.entity.light.light_controller import LightController
from custom_components.artnet_led.entity.light.light_state import LightState


class DmxLightEntity(LightEntity, RestoreEntity):
    def __init__(
            self,
            name: str,
            matrix_key: Optional[str],
            color_mode: ColorMode,
            channels: List[ChannelMapping],
            device: DeviceInfo,
            universe: DmxUniverse,
            has_separate_dimmer: bool = False,
            min_kelvin: int = 2000,
            max_kelvin: int = 6500,
    ):
        self._matrix_key = matrix_key
        self._attr_name = f"{name} Light {matrix_key}" if matrix_key else f"{name} Light"
        self._attr_device_info = device
        self._attr_unique_id = f"{DOMAIN}_light_{name}_{matrix_key}"
        self._attr_color_mode = color_mode
        self._attr_supported_color_modes = {color_mode}

        if ColorMode.COLOR_TEMP in self.supported_color_modes:
            self._attr_min_color_temp_kelvin = min_kelvin
            self._attr_max_color_temp_kelvin = max_kelvin
            self._attr_min_mireds = color_temperature_kelvin_to_mired(max_kelvin)
            self._attr_max_mireds = color_temperature_kelvin_to_mired(min_kelvin)

        converter = ColorConverter(min_kelvin, max_kelvin)
        self._state = LightState(color_mode, converter)

        channel_map = {ch.channel_type: ch for ch in channels}
        updater = ChannelUpdater(channel_map, universe)

        self._controller = LightController(self._state, updater)
        self._has_separate_dimmer = has_separate_dimmer
        self._universe = universe

        self._register_channel_listeners(channel_map)

    def _register_channel_listeners(self, channel_map: Dict[ChannelType, ChannelMapping]):
        for channel_type, channel_data in channel_map.items():
            for dmx_index in channel_data.dmx_indexes:
                self._universe.register_channel_listener(
                    dmx_index,
                    partial(self._handle_channel_update, channel_type)
                )

    @callback
    def _handle_channel_update(self, channel_type: ChannelType, dmx_index: int, value: int):
        if self._controller.handle_channel_update(channel_type, value):
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._state.is_on

    @property
    def brightness(self) -> int:
        return self._state.brightness

    @property
    def rgb_color(self) -> Tuple[int, int, int]:
        return self._state.rgb

    @property
    def rgbw_color(self) -> Optional[Tuple[int, int, int, int]]:
        return self._state.rgbw_color if self._state.color_mode in (ColorMode.RGBW, ColorMode.RGBWW) else None

    @property
    def rgbww_color(self) -> Optional[Tuple[int, int, int, int, int]]:
        return self._state.rgbww_color if self._state.color_mode == ColorMode.RGBWW else None

    @property
    def color_temp(self) -> int:
        return self._state.color_temp

    async def async_turn_on(self, **kwargs: Any):
        await self._controller.turn_on(**kwargs)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any):
        await self._controller.turn_off()
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if not last_state:
            return

        self._state.is_on = last_state.state == "on"
        attrs = last_state.attributes

        if "brightness" in attrs:
            brightness = attrs["brightness"]
            self._state.brightness = brightness
            self._state.last_brightness = brightness

        if "rgb_color" in attrs:
            rgb = attrs["rgb_color"]
            self._state.rgb = rgb
            self._state.last_rgb = rgb

        if "color_temp" in attrs:
            color_temp = attrs["color_temp"]
            self._state.color_temp = color_temp
            self._state.last_color_temp = color_temp

        # For color temp mode without dimmer, restore CW/WW values if available
        if (self._state.color_mode == ColorMode.COLOR_TEMP and
                not self._has_separate_dimmer and
                "brightness" in attrs and "color_temp" in attrs):
            # Reconstruct CW/WW values from brightness and color temp
            brightness = attrs["brightness"]
            color_temp = attrs["color_temp"]
            cold, warm = self._state.converter.temp_to_cw_ww(color_temp, brightness)
            self._state.cold_white = cold
            self._state.warm_white = warm
            self._state.last_cold_white = cold
            self._state.last_warm_white = warm
