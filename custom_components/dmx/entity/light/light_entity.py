import logging
from functools import partial
from typing import Optional, List, Dict, Tuple, Any

from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util.color import color_temperature_kelvin_to_mired

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
            has_separate_dimmer: bool = False,
            min_kelvin: int = 2000,
            max_kelvin: int = 6500,
    ):
        self._matrix_key = matrix_key
        self._attr_name = f"{fixture_name} Light {matrix_key}" if matrix_key else f"{fixture_name} Light"
        if entity_id_prefix:
            self._attr_unique_id = entity_id_prefix if not matrix_key else f"{entity_id_prefix}_{matrix_key}"
            self.entity_id = f"light.{self._attr_unique_id}"
        else:
            self._attr_unique_id = f"{DOMAIN}_{str(universe.port_address)}_{'/'.join(['-'.join(map(str, cm.dmx_indexes)) for cm in channels])}_{fixture_name}"

        self._attr_device_info = device
        self._attr_color_mode = color_mode
        self._attr_supported_color_modes = {color_mode}

        if ColorMode.COLOR_TEMP in self.supported_color_modes:
            self._attr_min_color_temp_kelvin = min_kelvin
            self._attr_max_color_temp_kelvin = max_kelvin
            self._attr_min_mireds = color_temperature_kelvin_to_mired(max_kelvin)
            self._attr_max_mireds = color_temperature_kelvin_to_mired(min_kelvin)

        converter = ColorConverter(min_kelvin, max_kelvin)

        self.channel_map = {ch.channel_type: ch for ch in channels}
        self._state = LightState(color_mode, converter, self.channel_map)
        self._controller = LightController(self._state, universe)

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

    async def async_turn_on(self, **kwargs: Any):
        await self._controller.turn_on(**kwargs)

        if not self.hass:
            log.debug(f"Not updating {self.name} because it hasn't been added to hass yet.")
            return

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any):
        await self._controller.turn_off()

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
            self._state.brightness = brightness
            self._state.last_brightness = brightness

        if "rgb_color" in attrs:
            rgb = attrs["rgb_color"]
            self._state.rgb = rgb
            self._state.last_rgb = rgb

        if "color_temp" in attrs:
            color_temp = attrs["color_temp"]
            self._state.color_temp_kelvin = color_temp
            self._state.last_color_temp_kelvin = color_temp

        # For color temp mode without dimmer, restore CW/WW values if available
        if (self._state.color_mode == ColorMode.COLOR_TEMP and
                not self._has_separate_dimmer and
                "brightness" in attrs and "color_temp" in attrs):
            # Reconstruct CW/WW values from brightness and color temp
            brightness = attrs["brightness"] or 100
            color_temp = attrs["color_temp"] or (self.min_color_temp_kelvin + self.max_color_temp_kelvin) / 2
            cold, warm = self._state.converter.temp_to_cw_ww(color_temp, brightness)
            self._state.cold_white = cold
            self._state.warm_white = warm
            self._state.last_cold_white = cold
            self._state.last_warm_white = warm
