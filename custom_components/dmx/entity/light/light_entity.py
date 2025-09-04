import logging
from functools import partial
from typing import Optional, List, Dict, Tuple, Any

from homeassistant.components.light import LightEntity, ColorMode, LightEntityFeature, ATTR_TRANSITION
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.dmx.const import DOMAIN
from custom_components.dmx.entity.light import ChannelMapping, ChannelType
from custom_components.dmx.entity.light.color_converter import ColorConverter
from custom_components.dmx.entity.light.light_controller import LightController
from custom_components.dmx.entity.light.light_state import LightState
from custom_components.dmx.io.dmx_io import DmxUniverse

log = logging.getLogger(__name__)


class DmxLightEntity(LightEntity, RestoreEntity):
    def __init__(
            self,
            fixture_name: str,
            entity_id_prefix: str | None,
            matrix_key: Optional[str],
            color_mode: ColorMode,
            channels: List[ChannelMapping],
            device: DeviceInfo,
            universe: DmxUniverse,
            fixture_fingerprint: str,
            has_separate_dimmer: bool = False,
            min_kelvin: int = 2000,
            max_kelvin: int = 6500,
    ):
        self._matrix_key = matrix_key
        self._attr_name = f"{fixture_name} Light {matrix_key}" if matrix_key else f"{fixture_name} Light"
        if entity_id_prefix:
            base_id = entity_id_prefix if not matrix_key else f"{entity_id_prefix}_{matrix_key}"
            self._attr_unique_id = f"{base_id}_{fixture_fingerprint}"
            self.entity_id = f"light.{self._attr_unique_id}"
        else:
            self._attr_unique_id = f"{DOMAIN}_{str(universe.port_address)}_{fixture_name}_{fixture_fingerprint}"
            if matrix_key:
                self._attr_unique_id = f"{self._attr_unique_id}_{matrix_key}"

        self._attr_device_info = device
        self._attr_color_mode = color_mode
        self._attr_supported_color_modes = {color_mode}
        self._attr_supported_features = LightEntityFeature.TRANSITION

        if ColorMode.COLOR_TEMP in self.supported_color_modes:
            self._attr_min_color_temp_kelvin = min_kelvin
            self._attr_max_color_temp_kelvin = max_kelvin

        converter = ColorConverter(min_kelvin, max_kelvin)

        self.channel_map = {ch.channel_type: ch for ch in channels}
        self._state = LightState(color_mode, converter, self.channel_map)

        animation_engine = getattr(universe, 'animation_engine', None)
        self._controller = LightController(self._state, universe, channels, animation_engine)

        self._has_separate_dimmer = has_separate_dimmer
        self._universe = universe

        self._register_channel_listeners(self.channel_map)

    def _register_channel_listeners(self, channel_map: Dict[ChannelType, ChannelMapping]):
        for channel_type, channel_data in channel_map.items():
            for dmx_index in channel_data.dmx_indexes:
                self._universe.register_channel_listener(
                    dmx_index,
                    partial(self._handle_channel_update, channel_type)
                )

    @callback
    def _handle_channel_update(self, channel_type: ChannelType, source: str | None):
        self._attr_attribution = source

        channel_mapping = self.channel_map[channel_type]
        [capability] = channel_mapping.channel.capabilities
        assert (len(capability.dynamic_entities) == 1)
        dynamic_entity = capability.dynamic_entities[0]

        dmx_values = [self._universe.get_channel_value(idx) for idx in channel_mapping.dmx_indexes]

        normalized_value = dynamic_entity.from_dmx_fine(dmx_values)
        value = dynamic_entity.unnormalize(normalized_value)

        if not self.hass:
            log.debug(f"Not updating {self.name} because it hasn't been added to hass yet.")
            return

        self._state.apply_channel_update(channel_type, round(value))
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
    def color_temp_kelvin(self) -> int | None:
        return self._state.color_temp_kelvin

    @property
    def min_color_temp_kelvin(self) -> int:
        value = getattr(self, '_attr_min_color_temp_kelvin', None)
        return value if value is not None else 2000

    @property 
    def max_color_temp_kelvin(self) -> int:
        value = getattr(self, '_attr_max_color_temp_kelvin', None)
        return value if value is not None else 6500

    async def async_turn_on(self, **kwargs: Any):
        await self._controller.turn_on(**kwargs)

        if not self.hass:
            log.debug(f"Not updating {self.name} because it hasn't been added to hass yet.")
            return

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any):
        transition = kwargs.get(ATTR_TRANSITION)
        await self._controller.turn_off(transition)

        if not self.hass:
            log.debug(f"Not updating {self.name} because it hasn't been added to hass yet.")
            return

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
            if brightness is not None:
                self._state.brightness = brightness
                self._state.last_brightness = brightness

        if "rgb_color" in attrs:
            rgb = attrs["rgb_color"]
            self._state.rgb = rgb
            self._state.last_rgb = rgb

        if "color_temp_kelvin" in attrs:
            color_temp_kelvin = attrs["color_temp_kelvin"]
            if color_temp_kelvin is not None:
                self._state.color_temp_kelvin = color_temp_kelvin
                self._state.last_color_temp_kelvin = color_temp_kelvin

        # For color temp mode without dimmer, restore CW/WW values if available
        if (self._state.color_mode == ColorMode.COLOR_TEMP and
                not self._has_separate_dimmer and
                "brightness" in attrs and ("color_temp_kelvin" in attrs or "color_temp" in attrs)):
            # Reconstruct CW/WW values from brightness and color temp
            brightness = attrs["brightness"] or 100
            
            if "color_temp_kelvin" in attrs and attrs["color_temp_kelvin"] is not None:
                color_temp_kelvin = attrs["color_temp_kelvin"]
            else:
                color_temp_kelvin = (self.min_color_temp_kelvin + self.max_color_temp_kelvin) / 2
                
            cold, warm = self._state.converter.temp_to_cw_ww(color_temp_kelvin, brightness)
            self._state.cold_white = cold
            self._state.warm_white = warm
            self._state.last_cold_white = cold
            self._state.last_warm_white = warm
