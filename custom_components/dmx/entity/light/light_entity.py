import logging
from collections.abc import Mapping
from functools import partial
from typing import Any

from homeassistant.components.light import ATTR_TRANSITION, ColorMode, LightEntity, LightEntityFeature
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify

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
        matrix_key: str | None,
        color_mode: ColorMode,
        channels: list[ChannelMapping],
        device: DeviceInfo,
        universe: DmxUniverse,
        fixture_fingerprint: str,
        has_separate_dimmer: bool = False,
        min_kelvin: int = 2000,
        max_kelvin: int = 6500,
        supported_color_modes: set[ColorMode] | None = None,
    ) -> None:
        self._matrix_key = matrix_key
        # No " Light" suffix: the entity_id HA derives from this name has to match the
        # old artnet_led integration's light.{slugify(name)} so migrated configs keep
        # their entity_ids (and their automations, scenes and groups) working.
        self._attr_name = f"{fixture_name} {matrix_key}" if matrix_key else fixture_name
        if entity_id_prefix:
            slug_prefix = slugify(entity_id_prefix)
            slug_matrix = slugify(matrix_key) if matrix_key else None
            base_id = slug_prefix if not slug_matrix else f"{slug_prefix}_{slug_matrix}"
            self._attr_unique_id = f"{base_id}_{fixture_fingerprint}"
            # The fingerprint identifies the fixture mode and belongs in unique_id only.
            # entity_id_prefix exists to give a predictable, user-facing entity_id, so the
            # hash must not leak into it -- a migrated config relies on this to reproduce
            # the entity_ids the old artnet_led integration generated.
            self.entity_id = f"light.{base_id}"
        else:
            self._attr_unique_id = f"{DOMAIN}_{universe.port_address!s}_{fixture_name}_{fixture_fingerprint}"
            if matrix_key:
                self._attr_unique_id = f"{self._attr_unique_id}_{matrix_key}"

        self._attr_device_info = device
        self._attr_supported_color_modes = supported_color_modes or {color_mode}
        self._attr_supported_features = LightEntityFeature(LightEntityFeature.TRANSITION)

        if self.supported_color_modes and ColorMode.COLOR_TEMP in self.supported_color_modes:
            self._attr_min_color_temp_kelvin = min_kelvin
            self._attr_max_color_temp_kelvin = max_kelvin

        converter = ColorConverter(min_kelvin, max_kelvin)

        self.channel_map = {ch.channel_type: ch for ch in channels}
        self._state = LightState(color_mode, converter, self.channel_map)

        animation_engine = getattr(universe, "animation_engine", None)
        self._controller = LightController(self._state, universe, channels, animation_engine)

        self._has_separate_dimmer = has_separate_dimmer
        self._universe = universe

        self._register_channel_listeners(self.channel_map)

    def _register_channel_listeners(self, channel_map: dict[ChannelType, ChannelMapping]) -> None:
        for channel_type, channel_data in channel_map.items():
            for dmx_index in channel_data.dmx_indexes:
                self._universe.register_channel_listener(dmx_index, partial(self._handle_channel_update, channel_type))

    @callback
    def _handle_channel_update(self, channel_type: ChannelType, source: str | None) -> None:
        self._attr_attribution = source

        channel_mapping = self.channel_map[channel_type]
        capabilities = channel_mapping.channel.capabilities
        capability = capabilities[0] if isinstance(capabilities, list) else capabilities
        assert len(capability.dynamic_entities) == 1
        dynamic_entity = capability.dynamic_entities[0]

        dmx_values = [self._universe.get_channel_value(idx) for idx in channel_mapping.dmx_indexes]

        normalized_value = dynamic_entity.from_dmx_fine(dmx_values)
        value = dynamic_entity.unnormalize(normalized_value)

        if channel_mapping.output_correction is not None:
            value = channel_mapping.output_correction.invert(value / 255.0) * 255.0

        if not self.hass:
            log.debug(f"Not updating {self.name} because it hasn't been added to hass yet.")
            return

        self._state.apply_channel_update(channel_type, round(value))
        self.async_write_ha_state()

    @property
    def color_mode(self) -> ColorMode:
        return self._state.color_mode

    @property
    def is_on(self) -> bool:
        return self._state.is_on

    @property
    def brightness(self) -> int | None:
        return self._state.brightness

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        return self._state.rgb_color

    @property
    def rgbw_color(self) -> tuple[int, int, int, int] | None:
        return self._state.rgbw_color if self._state.color_mode in (ColorMode.RGBW, ColorMode.RGBWW) else None

    @property
    def rgbww_color(self) -> tuple[int, int, int, int, int] | None:
        return self._state.rgbww_color if self._state.color_mode == ColorMode.RGBWW else None

    @property
    def color_temp_kelvin(self) -> int | None:
        return self._state.color_temp_kelvin

    @property
    def min_color_temp_kelvin(self) -> int:
        value = getattr(self, "_attr_min_color_temp_kelvin", None)
        return value if value is not None else 2000

    @property
    def max_color_temp_kelvin(self) -> int:
        value = getattr(self, "_attr_max_color_temp_kelvin", None)
        return value if value is not None else 6500

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._controller.turn_on(**kwargs)

        if not self.hass:
            log.debug(f"Not updating {self.name} because it hasn't been added to hass yet.")
            return

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        transition = kwargs.get(ATTR_TRANSITION)
        await self._controller.turn_off(transition)

        if not self.hass:
            log.debug(f"Not updating {self.name} because it hasn't been added to hass yet.")
            return

        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
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

        self._restore_color(attrs)

        if "color_temp_kelvin" in attrs:
            color_temp_kelvin = attrs["color_temp_kelvin"]
            if color_temp_kelvin is not None:
                self._state.update_color_temp_kelvin(color_temp_kelvin)

        # For color temp mode without dimmer, restore CW/WW values if available
        if (
            self._state.color_mode == ColorMode.COLOR_TEMP
            and self._state.has_cw_ww()
            and not self._has_separate_dimmer
            and "brightness" in attrs
            and ("color_temp_kelvin" in attrs or "color_temp" in attrs)
        ):
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

        # A single white channel without dimmer is the brightness, unless it's part of the RGBW color restored above.
        elif (
            self._state.has_channel(ChannelType.WARM_WHITE)
            and not self._state.has_cw_ww()
            and not self._has_separate_dimmer
            and attrs.get("color_mode") in (ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP)
            and attrs.get("brightness")
        ):
            self._state.warm_white = attrs["brightness"]
            self._state.last_warm_white = attrs["brightness"]

    def _restore_color(self, attrs: Mapping[str, Any]) -> None:
        # Only the attributes of the mode the light was in are real: Home Assistant derives the others from it,
        # e.g. rgb_color while showing white at a color temperature, or while RGBW(W) has its whites on.
        color_mode = attrs.get("color_mode")

        if self._state.has_rgb() and color_mode == ColorMode.RGBWW and attrs.get("rgbww_color") is not None:
            r, g, b, cold, warm = attrs["rgbww_color"]
            self._state.rgb = self._state.last_rgb = (r, g, b)
            self._state.cold_white = self._state.last_cold_white = cold
            self._state.warm_white = self._state.last_warm_white = warm

        elif self._state.has_rgb() and color_mode == ColorMode.RGBW and attrs.get("rgbw_color") is not None:
            r, g, b, white = attrs["rgbw_color"]
            self._state.rgb = self._state.last_rgb = (r, g, b)
            self._state.warm_white = self._state.last_warm_white = white

        elif self._state.has_rgb() and color_mode == ColorMode.RGB and attrs.get("rgb_color") is not None:
            r, g, b = attrs["rgb_color"]
            if not self._state.has_channel(ChannelType.DIMMER) and self._state.brightness:
                # The color comes on top of the brightness. Scaling rather than dimming also brings back a color
                # saved before that, which had the brightness in it already.
                color = {ChannelType.RED: r, ChannelType.GREEN: g, ChannelType.BLUE: b}
                color = self._state.scale_to_brightness(color, self._state.brightness)
                r, g, b = color[ChannelType.RED], color[ChannelType.GREEN], color[ChannelType.BLUE]
            self._state.rgb = self._state.last_rgb = (r, g, b)

        self._state.sync_color_mode()
