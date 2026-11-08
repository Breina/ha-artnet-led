import logging

from homeassistant.components.light import ColorMode

from custom_components.dmx.entity.light import ChannelMapping, ChannelType
from custom_components.dmx.entity.light.color_converter import ColorConverter

log = logging.getLogger(__name__)


class LightState:
    def __init__(self, color_mode: ColorMode, converter: ColorConverter, channels: dict[ChannelType, ChannelMapping]):
        self.color_mode = color_mode
        self.converter = converter
        self.channels = channels

        self.is_on = False
        self.brightness = 255
        self.cold_white = 255
        self.warm_white = 255
        self.color_temp_kelvin = 3000
        self.color_temp_dmx = 255.0

        self.last_brightness = 255
        self.last_cold_white = 255
        self.last_warm_white = 255
        self.last_color_temp_kelvin = 3000
        self.last_color_temp_dmx = 255.0

        self.rgb = (255, 255, 255)
        self.last_rgb = (255, 255, 255)

        # RGB next to a CCT channel, without separate cold and warm whites: the light shows either a color or
        # white at a color temperature. The channel values decide which one, so incoming DMX is covered too.
        self.switches_color_mode = (
            all(t in channels for t in [ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE])
            and ChannelType.COLOR_TEMPERATURE in channels
            and ChannelType.COLD_WHITE not in channels
        )
        self._color_mode_for_rgb = ColorMode.RGBW if ChannelType.WARM_WHITE in channels else ColorMode.RGB
        if self.switches_color_mode:
            self.rgb = (0, 0, 0)
            self.last_rgb = (0, 0, 0)

        # Flag to prevent updating last_* values during animations
        self._preserve_last_values = False

        self._channel_handlers = {}

        if ChannelType.DIMMER in channels:
            self._channel_handlers[ChannelType.DIMMER] = self._handle_dimmer_update

        if ChannelType.RED in channels:
            self._channel_handlers[ChannelType.RED] = lambda value: self._handle_rgb_component_update(0, value)
        if ChannelType.GREEN in channels:
            self._channel_handlers[ChannelType.GREEN] = lambda value: self._handle_rgb_component_update(1, value)
        if ChannelType.BLUE in channels:
            self._channel_handlers[ChannelType.BLUE] = lambda value: self._handle_rgb_component_update(2, value)

        if ChannelType.COLD_WHITE in channels:
            self._channel_handlers[ChannelType.COLD_WHITE] = self._handle_cold_white_update
        if ChannelType.WARM_WHITE in channels:
            self._channel_handlers[ChannelType.WARM_WHITE] = self._handle_warm_white_update
        if ChannelType.COLOR_TEMPERATURE in channels:
            self._channel_handlers[ChannelType.COLOR_TEMPERATURE] = lambda value: self.update_color_temp_dmx(value)

    def has_channel(self, t: ChannelType) -> bool:
        return t in self.channels

    def has_rgb(self) -> bool:
        return all(t in self.channels for t in [ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE])

    def has_cw_ww(self) -> bool:
        return all(t in self.channels for t in [ChannelType.COLD_WHITE, ChannelType.WARM_WHITE])

    def _has_dimmer(self) -> bool:
        return self.has_channel(ChannelType.DIMMER)

    def output_channels(self) -> list[ChannelType]:
        """The channels that produce light, as opposed to a dimmer or color temperature modifying it."""
        candidates = (
            ChannelType.RED,
            ChannelType.GREEN,
            ChannelType.BLUE,
            ChannelType.COLD_WHITE,
            ChannelType.WARM_WHITE,
        )
        return [channel for channel in candidates if channel in self.channels]

    def sync_color_mode(self) -> None:
        if not self.switches_color_mode:
            return

        if any(self.rgb):
            self.color_mode = self._color_mode_for_rgb
        else:
            self.color_mode = ColorMode.COLOR_TEMP
            # Back to white on purpose: restoring must not bring back a color that has been replaced.
            if not self._preserve_last_values:
                self.last_rgb = (0, 0, 0)

    def apply_channel_update(self, channel_type: ChannelType, value: int) -> None:
        if channel_type in self._channel_handlers:
            self._channel_handlers[channel_type](value)
            self._update_on_state_after_channel_update()

    def _handle_dimmer_update(self, value: int) -> None:
        self.update_brightness(value)
        self.is_on = value > 0

    def _handle_rgb_component_update(self, component_index: int, value: int) -> None:
        # This should only be called for RGB color modes
        if not self.switches_color_mode and self.color_mode not in [ColorMode.RGB, ColorMode.RGBW, ColorMode.RGBWW]:
            log.warning(f"RGB component update called for non-RGB color mode {self.color_mode}")
            return

        new_rgb = list(self.rgb)
        new_rgb[component_index] = value

        if self.switches_color_mode:
            self.update_rgb(*new_rgb)
            self.sync_color_mode()
        else:
            self._update_rgb_based_on_color_mode(*new_rgb)

        if not self._has_dimmer():
            self._update_brightness_from_channels()

    def _handle_cold_white_update(self, value: int) -> None:
        self.update_cw(value)
        self._handle_white_brightness_and_temp_update()

    def _handle_warm_white_update(self, value: int) -> None:
        self.update_ww(value)
        self._handle_white_brightness_and_temp_update()

    def _handle_white_brightness_and_temp_update(self) -> None:
        if self.color_mode == ColorMode.COLOR_TEMP and self.has_cw_ww() and not self._has_dimmer():
            old_brightness = self.brightness
            self._update_brightness_from_cw_ww()
            if self.brightness == 0 and old_brightness > 0:
                self.is_on = False
            self._update_color_temp_from_cw_ww()
        elif not self._has_dimmer():
            self._update_brightness_from_channels()

    def _update_on_state_after_channel_update(self) -> None:
        if not self._has_dimmer():
            if not self.output_channels():
                # Nothing on this fixture can darken it, so the channels say nothing about being on or off.
                return

            if self.is_all_zero(False):
                self.is_on = False
            else:
                self._update_on_state_without_dimmer()
        else:
            self.is_on = self.brightness > 0

    def _update_on_state_without_dimmer(self) -> None:
        if self.color_mode == ColorMode.COLOR_TEMP and self.has_cw_ww():
            self.is_on = self.cold_white > 0 or self.warm_white > 0
        elif self.color_mode == ColorMode.RGBWW:
            self.is_on = any(v > 0 for v in (*self.rgb, self.cold_white, self.warm_white))
        elif self.color_mode == ColorMode.RGBW:
            self.is_on = any(v > 0 for v in (*self.rgb, self.warm_white))
        elif self.color_mode == ColorMode.RGB:
            self.is_on = any(v > 0 for v in self.rgb)
        elif self.has_channel(ChannelType.COLD_WHITE):
            self.is_on = self.cold_white > 0
        elif self.has_channel(ChannelType.WARM_WHITE):
            self.is_on = self.warm_white > 0
        else:
            self.is_on = self.brightness > 0

    def get_scaled_brightness_updates(self, new_brightness: int) -> dict[ChannelType, int]:
        updates: dict[ChannelType, int] = {}

        if self._has_dimmer():
            updates[ChannelType.DIMMER] = new_brightness
            return updates

        if self.has_cw_ww() and not self.has_rgb():
            cw, ww = self.converter.temp_to_cw_ww(self.color_temp_kelvin, new_brightness)
            updates[ChannelType.COLD_WHITE] = cw
            updates[ChannelType.WARM_WHITE] = ww
            return updates

        channel_values = {channel: self.get_channel_entity_value(channel) for channel in self.output_channels()}

        # Switched off, so these are all zero. There's nothing to scale, but the last values are.
        if not any(channel_values.values()):
            channel_values = self.last_output_values()

        return self.scale_to_brightness(channel_values, new_brightness)

    def last_output_values(self) -> dict[ChannelType, int]:
        """The values of the output channels from before the light was last turned off."""
        last_values = {
            ChannelType.RED: self.last_rgb[0],
            ChannelType.GREEN: self.last_rgb[1],
            ChannelType.BLUE: self.last_rgb[2],
            ChannelType.COLD_WHITE: self.last_cold_white,
            ChannelType.WARM_WHITE: self.last_warm_white,
        }
        return {channel: last_values[channel] for channel in self.output_channels()}

    @staticmethod
    def scale_to_brightness(channel_values: dict[ChannelType, int], brightness: int) -> dict[ChannelType, int]:
        """Scale channels so that the brightest one ends up at the given brightness, keeping their ratio."""
        max_current = max(channel_values.values(), default=0)
        scale = brightness / max_current if max_current > 0 else 0
        return {channel: min(255, round(value * scale)) for channel, value in channel_values.items()}

    @staticmethod
    def dim(channel_values: dict[ChannelType, int], brightness: int) -> dict[ChannelType, int]:
        """Apply a brightness to channels the way a dimmer would."""
        return {channel: round(value * brightness / 255) for channel, value in channel_values.items()}

    def get_channel_entity_value(self, channel_type: ChannelType) -> int:
        """Return the current entity-space value for a channel type from the light state."""
        if channel_type == ChannelType.DIMMER:
            return self.brightness
        if channel_type == ChannelType.RED:
            return self.rgb[0]
        if channel_type == ChannelType.GREEN:
            return self.rgb[1]
        if channel_type == ChannelType.BLUE:
            return self.rgb[2]
        if channel_type == ChannelType.COLD_WHITE:
            return self.cold_white
        if channel_type == ChannelType.WARM_WHITE:
            return self.warm_white
        if channel_type == ChannelType.COLOR_TEMPERATURE:
            return round(self.color_temp_dmx)
        return 0

    def get_dmx_updates(self, values: dict[ChannelType, int | float]) -> dict[int, int]:
        updates = {}
        for channel_type, val in values.items():
            if channel_type not in self.channels:
                continue

            mapping = self.channels[channel_type]

            if mapping.output_correction is not None:
                val = mapping.output_correction.apply(float(val) / 255.0) * 255.0

            capabilities = mapping.channel.capabilities
            first_capability = capabilities[0] if isinstance(capabilities, list) else capabilities
            [entity] = first_capability.dynamic_entities
            norm_val = entity.normalize(val)
            dmx_values = entity.to_dmx_fine(norm_val, len(mapping.dmx_indexes))

            for i, dmx_index in enumerate(mapping.dmx_indexes):
                updates[dmx_index] = dmx_values[i]

        return updates

    def _update_rgb_based_on_color_mode(self, r: int, g: int, b: int) -> None:
        if self.color_mode == ColorMode.RGB:
            self.update_rgb(r, g, b)
        elif self.color_mode == ColorMode.RGBW:
            self.update_rgbw(r, g, b, self.warm_white)
        elif self.color_mode == ColorMode.RGBWW:
            self.update_rgbww(r, g, b, self.cold_white, self.warm_white)
        else:
            raise RuntimeError("Shouldn't be able to update RGB if color mode is not RGB, RGBW, or RGBWW.")

    def update_cw(self, cw: int) -> None:
        self._update_last_value_if_positive(cw, "last_cold_white")
        self.cold_white = cw

        if self.color_mode == ColorMode.COLOR_TEMP:
            self.update_whites(cw, self.warm_white)
        elif self.color_mode == ColorMode.RGBW:
            raise RuntimeError("By convention, in color mode RGBW, CW is not used.")
        elif self.color_mode == ColorMode.RGBWW:
            self.update_rgbww(self.rgb[0], self.rgb[1], self.rgb[2], cw, self.warm_white)
        elif self.color_mode != ColorMode.BRIGHTNESS:
            raise RuntimeError("Shouldn't be able to update CW if color mode is not COLOR_TEMP, BRIGHTNESS, or RGBWW.")

    def update_ww(self, ww: int) -> None:
        self._update_last_value_if_positive(ww, "last_warm_white")

        if self.color_mode == ColorMode.BRIGHTNESS:
            self.warm_white = ww
        elif self.color_mode == ColorMode.COLOR_TEMP:
            self.update_whites(self.cold_white, ww)
        elif self.color_mode == ColorMode.RGBW:
            self.update_rgbw(self.rgb[0], self.rgb[1], self.rgb[2], ww)
        elif self.color_mode == ColorMode.RGBWW:
            self.update_rgbww(self.rgb[0], self.rgb[1], self.rgb[2], self.cold_white, ww)
        else:
            raise RuntimeError(
                "Shouldn't be able to update WW if color mode is not COLOR_TEMP, BRIGHTNESS, RGBW or RGBWW."
            )

    def _update_last_value_if_positive(self, value: int, last_attr: str) -> None:
        if value > 0 and not self._preserve_last_values:
            setattr(self, last_attr, value)

    def update_rgb(self, r: int, g: int, b: int) -> None:
        self.rgb = (r, g, b)
        if any(c > 0 for c in (r, g, b)) and not self._preserve_last_values:
            self.last_rgb = self.rgb

    def update_rgbw(self, r: int, g: int, b: int, w: int) -> None:
        self.rgb = (r, g, b)
        self.warm_white = w
        if any(c > 0 for c in (r, g, b, w)) and not self._preserve_last_values:
            self.last_rgb = self.rgb
            self.last_warm_white = w

    def update_rgbww(self, r: int, g: int, b: int, cw: int, ww: int) -> None:
        self.rgb = (r, g, b)
        self.cold_white = cw
        self.warm_white = ww
        if any(c > 0 for c in (r, g, b, ww, cw)) and not self._preserve_last_values:
            self.last_rgb = self.rgb
            self.last_cold_white = cw
            self.last_warm_white = ww

    def update_whites(self, cold: int, warm: int) -> None:
        if (cold > 0 or warm > 0) and not self._preserve_last_values:
            self.last_cold_white = cold
            self.last_warm_white = warm

        self.cold_white = cold
        self.warm_white = warm

    def update_brightness(self, value: int) -> None:
        if value is not None:
            self.brightness = value
            if value > 0 and not self._preserve_last_values:
                self.last_brightness = value

    def update_color_temp_dmx(self, dmx_value: int) -> None:
        self.color_temp_dmx = dmx_value
        if not self._preserve_last_values:
            self.last_color_temp_dmx = dmx_value
        self.color_temp_kelvin = self.converter.dmx_to_kelvin(dmx_value)
        if not self._preserve_last_values:
            self.last_color_temp_kelvin = self.color_temp_kelvin

    def update_color_temp_kelvin(self, kelvin: int) -> None:
        self.color_temp_kelvin = kelvin
        if not self._preserve_last_values:
            self.last_color_temp_kelvin = kelvin
        self.color_temp_dmx = self.converter.kelvin_to_dmx(kelvin)
        if not self._preserve_last_values:
            self.last_color_temp_dmx = self.color_temp_dmx

    def reset(self) -> None:
        if self.output_channels():
            self.brightness = 0
        self.cold_white = 0
        self.warm_white = 0
        self.is_on = False

    def is_all_zero(self, has_dimmer: bool) -> bool:
        if has_dimmer:
            return self.brightness == 0
        return self.rgb == (0, 0, 0) and self.cold_white == 0 and self.warm_white == 0

    def _update_brightness_from_channels(self) -> None:
        values: list[int] = []

        if self.has_rgb():
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

    def _update_brightness_from_cw_ww(self) -> None:
        if self.color_mode == ColorMode.COLOR_TEMP and self.has_cw_ww():
            brightness, _ = self.converter.cw_ww_to_brightness_temp(self.cold_white, self.warm_white)
            self.brightness = brightness
            if brightness > 0 and not self._preserve_last_values:
                self.last_brightness = brightness

    def _update_color_temp_from_cw_ww(self) -> None:
        if self.color_mode == ColorMode.COLOR_TEMP and self.has_cw_ww():
            color_temp_kelvin = self.converter.cw_ww_to_temp(self.cold_white, self.warm_white)
            self.update_color_temp_kelvin(color_temp_kelvin)

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        """
        The color as Home Assistant has it in RGB mode, which comes on top of the brightness. Without a dimmer, the
        brightness is already in the color channels, so it's taken out of the color to not have it counted twice.
        """
        peak = max(self.rgb)
        if self._has_dimmer() or self.color_mode != ColorMode.RGB or not peak:
            return self.rgb

        r, g, b = self.rgb
        return round(r * 255 / peak), round(g * 255 / peak), round(b * 255 / peak)

    @property
    def rgbw_color(self) -> tuple[int, int, int, int]:
        return (*self.rgb, self.warm_white)

    @property
    def rgbww_color(self) -> tuple[int, int, int, int, int]:
        return (*self.rgb, self.cold_white, self.warm_white)

    @property
    def last_rgbw_color(self) -> tuple[int, int, int, int]:
        return (*self.last_rgb, self.last_cold_white)

    @property
    def last_rgbww_color(self) -> tuple[int, int, int, int, int]:
        return (*self.last_rgb, self.last_cold_white, self.last_warm_white)
