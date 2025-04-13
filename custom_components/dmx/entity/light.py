from dataclasses import dataclass
from enum import Enum, auto
from functools import partial
from typing import Dict, List, Optional, Tuple, Any

import homeassistant.util.color as color_util
from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.dmx import DOMAIN
from custom_components.dmx.fixture.channel import Channel
from custom_components.dmx.io.dmx_io import DmxUniverse


class LightChannel(Enum):
    """Types of DMX light channels."""
    RED = auto()
    GREEN = auto()
    BLUE = auto()
    COLD_WHITE = auto()
    WARM_WHITE = auto()
    COLOR_TEMPERATURE = auto()
    DIMMER = auto()


@dataclass
class DMXLightChannel:
    """Representation of a DMX light channel."""
    dmx_channel_indexes: List[int]
    channel: Channel
    light_channel: LightChannel


class DMXLightState:
    """Class to manage the state of a DMX light."""

    def __init__(self, color_mode: ColorMode, min_kelvin: int = 2000, max_kelvin: int = 6500):
        """Initialize light state."""
        # Current state
        self.is_on = False
        self.brightness = 255
        self.rgb_color = (255, 255, 255)
        self.cold_white = 255
        self.warm_white = 255
        self.color_temp = 500  # Mired scale
        self.color_temp_value = 255  # Direct DMX value

        # Last active state
        self.last_brightness = 255
        self.last_rgb_color = (255, 255, 255)
        self.last_cold_white = 255
        self.last_warm_white = 255
        self.last_color_temp = 500
        self.last_color_temp_value = 255

        # Extended state for specific color modes
        if color_mode in (ColorMode.RGBW, ColorMode.RGBWW):
            self.rgbw_color = (255, 255, 255, 255)
            self.last_rgbw_color = (255, 255, 255, 255)

        if color_mode == ColorMode.RGBWW:
            self.rgbww_color = (255, 255, 255, 255, 255)
            self.last_rgbww_color = (255, 255, 255, 255, 255)

        # Color temperature limits
        self.min_mireds = color_util.color_temperature_kelvin_to_mired(max_kelvin)
        self.max_mireds = color_util.color_temperature_kelvin_to_mired(min_kelvin)

    def update_rgb(self, r: int, g: int, b: int) -> None:
        """Update RGB components of the state."""
        self.rgb_color = (r, g, b)
        if all(c > 0 for c in (r, g, b)):
            self.last_rgb_color = self.rgb_color

        if hasattr(self, "rgbw_color"):
            self.rgbw_color = (r, g, b, self.rgbw_color[3])
            if any(c > 0 for c in self.rgbw_color):
                self.last_rgbw_color = self.rgbw_color

        if hasattr(self, "rgbww_color"):
            self.rgbww_color = (r, g, b, self.rgbww_color[3], self.rgbww_color[4])
            if any(c > 0 for c in self.rgbww_color):
                self.last_rgbww_color = self.rgbww_color

    def update_white(self, white_value: int, is_cold: bool = True) -> None:
        """Update white component of the state."""
        if is_cold:
            self.cold_white = white_value
            if white_value > 0:
                self.last_cold_white = white_value

            if hasattr(self, "rgbw_color"):
                self.rgbw_color = (self.rgbw_color[0], self.rgbw_color[1], self.rgbw_color[2], white_value)
                if any(c > 0 for c in self.rgbw_color):
                    self.last_rgbw_color = self.rgbw_color

            if hasattr(self, "rgbww_color"):
                self.rgbww_color = (self.rgbww_color[0], self.rgbww_color[1], self.rgbww_color[2],
                                    white_value, self.rgbww_color[4])
                if any(c > 0 for c in self.rgbww_color):
                    self.last_rgbww_color = self.rgbww_color
        else:
            self.warm_white = white_value
            if white_value > 0:
                self.last_warm_white = white_value

            if hasattr(self, "rgbww_color"):
                self.rgbww_color = (self.rgbww_color[0], self.rgbww_color[1], self.rgbww_color[2],
                                    self.rgbww_color[3], white_value)
                if any(c > 0 for c in self.rgbww_color):
                    self.last_rgbww_color = self.rgbww_color

    def update_brightness(self, brightness: int) -> None:
        """Update brightness value of the state."""
        self.brightness = brightness
        if brightness > 0:
            self.last_brightness = brightness
            self.is_on = True

    def update_color_temp(self, value: int, is_dmx_value: bool = True) -> None:
        """Update color temperature value."""
        if is_dmx_value:
            self.color_temp_value = value
            if value > 0:
                self.last_color_temp_value = value

            # Convert DMX value to mired
            ratio = value / 255
            self.color_temp = self.min_mireds + ratio * (self.max_mireds - self.min_mireds)
            if value > 0:
                self.last_color_temp = self.color_temp
        else:
            # Direct mired value
            self.color_temp = value
            if value > 0:
                self.last_color_temp = value

    def reset_all_channels(self) -> None:
        """Reset all channel values to zero."""
        self.brightness = 0
        self.rgb_color = (0, 0, 0)
        self.cold_white = 0
        self.warm_white = 0

        if hasattr(self, "rgbw_color"):
            self.rgbw_color = (0, 0, 0, 0)

        if hasattr(self, "rgbww_color"):
            self.rgbww_color = (0, 0, 0, 0, 0)


class DMXLightController:
    """Controller for DMX light operations."""

    def __init__(self, channels: List[DMXLightChannel], state: DMXLightState, color_mode: ColorMode, universe: DmxUniverse):
        """Initialize the DMX light controller."""
        self.channels = channels
        self.state = state
        self.color_mode = color_mode
        self.universe = universe  # Store a single universe reference

        # Map channels by type for easy access
        self.channel_map: Dict[LightChannel, DMXLightChannel] = {
            channel.light_channel: channel for channel in channels
        }

        # Flag to prevent feedback loops during updates
        self.is_updating = False

    async def _update_channel_value(self, channel_data: DMXLightChannel, value: int) -> None:
        """Send a DMX value update to the universe."""
        dmx_value = min(255, max(0, value))  # Ensure value is in DMX range

        for dmx_index in channel_data.dmx_channel_indexes:
            await self.universe.update_value(dmx_index, dmx_value)

    async def update_rgb_channels(self, rgb: Tuple[int, int, int]) -> None:
        """Update RGB channels with new values."""
        if not all(ch in self.channel_map for ch in
                   [LightChannel.RED, LightChannel.GREEN, LightChannel.BLUE]):
            return

        self.state.update_rgb(rgb[0], rgb[1], rgb[2])

        # Collect all channel updates
        updates = {}
        if LightChannel.RED in self.channel_map:
            for idx in self.channel_map[LightChannel.RED].dmx_channel_indexes:
                updates[idx] = rgb[0]
        if LightChannel.GREEN in self.channel_map:
            for idx in self.channel_map[LightChannel.GREEN].dmx_channel_indexes:
                updates[idx] = rgb[1]
        if LightChannel.BLUE in self.channel_map:
            for idx in self.channel_map[LightChannel.BLUE].dmx_channel_indexes:
                updates[idx] = rgb[2]

        # Send all updates at once
        if updates:
            await self.universe.update_multiple_values(updates)

    async def update_white_channel(self, value: int, is_cold: bool = True) -> None:
        """Update white channel (cold or warm) with new value."""
        channel_type = LightChannel.COLD_WHITE if is_cold else LightChannel.WARM_WHITE

        if channel_type not in self.channel_map:
            return

        self.state.update_white(value, is_cold)

        # Collect channel updates
        updates = {}
        for idx in self.channel_map[channel_type].dmx_channel_indexes:
            updates[idx] = value

        # Send updates
        if updates:
            await self.universe.update_multiple_values(updates)

    async def update_color_temp(self, temp_mired: int) -> None:
        """Update color temperature using appropriate channels."""
        self.state.update_color_temp(temp_mired, is_dmx_value=False)
        updates = {}

        if LightChannel.COLOR_TEMPERATURE in self.channel_map:
            # Convert mired to DMX value
            ratio = (temp_mired - self.state.min_mireds) / (self.state.max_mireds - self.state.min_mireds)
            dmx_value = int(ratio * 255)
            self.state.color_temp_value = dmx_value

            for idx in self.channel_map[LightChannel.COLOR_TEMPERATURE].dmx_channel_indexes:
                updates[idx] = dmx_value

        elif all(ch in self.channel_map for ch in [LightChannel.COLD_WHITE, LightChannel.WARM_WHITE]):
            # Calculate cold/warm mix based on temperature
            ratio = (temp_mired - self.state.min_mireds) / (self.state.max_mireds - self.state.min_mireds)
            warm_value = int(ratio * 255)
            cold_value = int((1 - ratio) * 255)

            self.state.update_white(cold_value, is_cold=True)
            self.state.update_white(warm_value, is_cold=False)

            for idx in self.channel_map[LightChannel.COLD_WHITE].dmx_channel_indexes:
                updates[idx] = cold_value
            for idx in self.channel_map[LightChannel.WARM_WHITE].dmx_channel_indexes:
                updates[idx] = warm_value

        # Send updates
        if updates:
            await self.universe.update_multiple_values(updates)

    async def update_brightness(self, brightness: int) -> None:
        """Update brightness using the appropriate channel."""
        self.state.update_brightness(brightness)
        updates = {}

        if LightChannel.DIMMER in self.channel_map:
            for idx in self.channel_map[LightChannel.DIMMER].dmx_channel_indexes:
                updates[idx] = brightness
        elif LightChannel.COLD_WHITE in self.channel_map and self.color_mode == ColorMode.BRIGHTNESS:
            for idx in self.channel_map[LightChannel.COLD_WHITE].dmx_channel_indexes:
                updates[idx] = brightness
        elif LightChannel.WARM_WHITE in self.channel_map and self.color_mode == ColorMode.BRIGHTNESS:
            for idx in self.channel_map[LightChannel.WARM_WHITE].dmx_channel_indexes:
                updates[idx] = brightness

        # Send updates
        if updates:
            await self.universe.update_multiple_values(updates)

    async def turn_on(self, **kwargs) -> None:
        """Turn on the light with specified parameters."""
        self.state.is_on = True
        updates = {}  # Will collect all updates to send in one batch

        # Process different attributes based on what's provided in kwargs
        has_specific_attrs = False

        if "brightness" in kwargs and LightChannel.DIMMER in self.channel_map:
            brightness = kwargs["brightness"]
            self.state.update_brightness(brightness)
            for idx in self.channel_map[LightChannel.DIMMER].dmx_channel_indexes:
                updates[idx] = brightness
            has_specific_attrs = True

        if "rgb_color" in kwargs:
            rgb = kwargs["rgb_color"]
            self.state.update_rgb(rgb[0], rgb[1], rgb[2])

            if LightChannel.RED in self.channel_map:
                for idx in self.channel_map[LightChannel.RED].dmx_channel_indexes:
                    updates[idx] = rgb[0]
            if LightChannel.GREEN in self.channel_map:
                for idx in self.channel_map[LightChannel.GREEN].dmx_channel_indexes:
                    updates[idx] = rgb[1]
            if LightChannel.BLUE in self.channel_map:
                for idx in self.channel_map[LightChannel.BLUE].dmx_channel_indexes:
                    updates[idx] = rgb[2]

            has_specific_attrs = True

        if "rgbw_color" in kwargs:
            rgbw = kwargs["rgbw_color"]
            self.state.update_rgb(rgbw[0], rgbw[1], rgbw[2])
            self.state.update_white(rgbw[3], is_cold=True)

            if LightChannel.RED in self.channel_map:
                for idx in self.channel_map[LightChannel.RED].dmx_channel_indexes:
                    updates[idx] = rgbw[0]
            if LightChannel.GREEN in self.channel_map:
                for idx in self.channel_map[LightChannel.GREEN].dmx_channel_indexes:
                    updates[idx] = rgbw[1]
            if LightChannel.BLUE in self.channel_map:
                for idx in self.channel_map[LightChannel.BLUE].dmx_channel_indexes:
                    updates[idx] = rgbw[2]
            if LightChannel.COLD_WHITE in self.channel_map:
                for idx in self.channel_map[LightChannel.COLD_WHITE].dmx_channel_indexes:
                    updates[idx] = rgbw[3]

            has_specific_attrs = True

        if "rgbww_color" in kwargs:
            rgbww = kwargs["rgbww_color"]
            self.state.update_rgb(rgbww[0], rgbww[1], rgbww[2])
            self.state.update_white(rgbww[3], is_cold=True)
            self.state.update_white(rgbww[4], is_cold=False)

            if LightChannel.RED in self.channel_map:
                for idx in self.channel_map[LightChannel.RED].dmx_channel_indexes:
                    updates[idx] = rgbww[0]
            if LightChannel.GREEN in self.channel_map:
                for idx in self.channel_map[LightChannel.GREEN].dmx_channel_indexes:
                    updates[idx] = rgbww[1]
            if LightChannel.BLUE in self.channel_map:
                for idx in self.channel_map[LightChannel.BLUE].dmx_channel_indexes:
                    updates[idx] = rgbww[2]
            if LightChannel.COLD_WHITE in self.channel_map:
                for idx in self.channel_map[LightChannel.COLD_WHITE].dmx_channel_indexes:
                    updates[idx] = rgbww[3]
            if LightChannel.WARM_WHITE in self.channel_map:
                for idx in self.channel_map[LightChannel.WARM_WHITE].dmx_channel_indexes:
                    updates[idx] = rgbww[4]

            has_specific_attrs = True

        if "color_temp" in kwargs:
            temp_mired = kwargs["color_temp"]
            self.state.update_color_temp(temp_mired, is_dmx_value=False)

            if LightChannel.COLOR_TEMPERATURE in self.channel_map:
                # Convert mired to DMX value
                ratio = (temp_mired - self.state.min_mireds) / (self.state.max_mireds - self.state.min_mireds)
                dmx_value = int(ratio * 255)
                self.state.color_temp_value = dmx_value

                for idx in self.channel_map[LightChannel.COLOR_TEMPERATURE].dmx_channel_indexes:
                    updates[idx] = dmx_value
            elif all(ch in self.channel_map for ch in [LightChannel.COLD_WHITE, LightChannel.WARM_WHITE]):
                # Calculate cold/warm mix based on temperature
                ratio = (temp_mired - self.state.min_mireds) / (self.state.max_mireds - self.state.min_mireds)
                warm_value = int(ratio * 255)
                cold_value = int((1 - ratio) * 255)

                self.state.update_white(cold_value, is_cold=True)
                self.state.update_white(warm_value, is_cold=False)

                for idx in self.channel_map[LightChannel.COLD_WHITE].dmx_channel_indexes:
                    updates[idx] = cold_value
                for idx in self.channel_map[LightChannel.WARM_WHITE].dmx_channel_indexes:
                    updates[idx] = warm_value

            has_specific_attrs = True

        # If no specific attributes, restore previous state
        if not has_specific_attrs:
            await self._restore_previous_state_batch(updates)
        elif updates:
            # Send all updates in one batch
            await self.universe.update_multiple_values(updates)

    async def turn_off(self) -> None:
        """Turn off the light."""
        self.state.is_on = False
        updates = {}  # Will collect all updates to send in one batch

        # If there's a separate dimmer, just turn that off
        if LightChannel.DIMMER in self.channel_map:
            dimmer_channel = self.channel_map[LightChannel.DIMMER]
            for dmx_index in dimmer_channel.dmx_channel_indexes:
                updates[dmx_index] = 0
            self.state.brightness = 0
        else:
            # Otherwise turn off all channels
            self.is_updating = True
            try:
                for ch_data in self.channels:
                    for dmx_index in ch_data.dmx_channel_indexes:
                        updates[dmx_index] = 0
                self.state.reset_all_channels()
            finally:
                self.is_updating = False

        # Send all updates in one batch
        if updates:
            await self.universe.update_multiple_values(updates)

    async def _restore_previous_state_batch(self, updates: Dict[int, int]) -> None:
        """Restore the light's previous state with batched updates."""
        has_dimmer = LightChannel.DIMMER in self.channel_map

        # If we have a dimmer, use that for brightness control
        if has_dimmer:
            brightness = self.state.last_brightness or 255
            for idx in self.channel_map[LightChannel.DIMMER].dmx_channel_indexes:
                updates[idx] = brightness

        # Handle RGB channels
        if self.color_mode in (ColorMode.RGB, ColorMode.RGBW, ColorMode.RGBWW):
            if all(ch in self.channel_map for ch in [LightChannel.RED, LightChannel.GREEN, LightChannel.BLUE]):
                rgb = self.state.last_rgb_color
                for idx in self.channel_map[LightChannel.RED].dmx_channel_indexes:
                    updates[idx] = rgb[0]
                for idx in self.channel_map[LightChannel.GREEN].dmx_channel_indexes:
                    updates[idx] = rgb[1]
                for idx in self.channel_map[LightChannel.BLUE].dmx_channel_indexes:
                    updates[idx] = rgb[2]

        # Handle white channels
        if self.color_mode in (ColorMode.RGBW, ColorMode.RGBWW, ColorMode.COLOR_TEMP):
            if LightChannel.COLD_WHITE in self.channel_map:
                for idx in self.channel_map[LightChannel.COLD_WHITE].dmx_channel_indexes:
                    updates[idx] = self.state.last_cold_white

            if LightChannel.WARM_WHITE in self.channel_map:
                for idx in self.channel_map[LightChannel.WARM_WHITE].dmx_channel_indexes:
                    updates[idx] = self.state.last_warm_white

        # Handle color temperature channel
        if LightChannel.COLOR_TEMPERATURE in self.channel_map:
            for idx in self.channel_map[LightChannel.COLOR_TEMPERATURE].dmx_channel_indexes:
                updates[idx] = self.state.last_color_temp_value

        # Handle brightness for non-dimmer configurations
        if not has_dimmer and self.color_mode == ColorMode.BRIGHTNESS:
            brightness = self.state.last_brightness or 255
            if LightChannel.COLD_WHITE in self.channel_map:
                for idx in self.channel_map[LightChannel.COLD_WHITE].dmx_channel_indexes:
                    updates[idx] = brightness
            elif LightChannel.WARM_WHITE in self.channel_map:
                for idx in self.channel_map[LightChannel.WARM_WHITE].dmx_channel_indexes:
                    updates[idx] = brightness

        # Send all updates in a single batch if this function is called directly
        if updates:
            await self.universe.update_multiple_values(updates)


class DMXLightEntity(LightEntity, RestoreEntity):
    """DMX/ArtNet light entity that supports various channel configurations."""

    def __init__(
            self,
            matrix_key: Optional[str],
            color_mode: ColorMode,
            channels: List[DMXLightChannel],
            device: DeviceInfo,
            universe: DmxUniverse,
            has_separate_dimmer: bool = False,
            min_kelvin: int = 2000,
            max_kelvin: int = 6500,
    ):
        """Initialize the light entity."""
        # Entity attributes
        self._matrix_key = matrix_key
        self._attr_name = f"Light {matrix_key}" if matrix_key else "Light"
        self._attr_device_info = device
        self._attr_unique_id = f"{DOMAIN}_light_{matrix_key}"

        # Color mode configuration
        self._attr_color_mode = color_mode
        self._attr_supported_color_modes = {color_mode}

        # Color temperature configuration
        if ColorMode.COLOR_TEMP in self.supported_color_modes:
            self._attr_min_mireds = color_util.color_temperature_kelvin_to_mired(max_kelvin)
            self._attr_max_mireds = color_util.color_temperature_kelvin_to_mired(min_kelvin)

        self._state = DMXLightState(color_mode, min_kelvin, max_kelvin)
        self._universe = universe
        self._controller = DMXLightController(channels, self._state, color_mode, universe)
        self._has_separate_dimmer = has_separate_dimmer

        self._register_channel_listeners()

    def _register_channel_listeners(self) -> None:
        """Set up listeners for all DMX channels."""
        for channel_type, channel_data in self._controller.channel_map.items():
            for dmx_index in channel_data.dmx_channel_indexes:
                self._universe.register_channel_listener(
                    dmx_index,
                    partial(self._handle_channel_update, channel_type)
                )

    @callback
    def _handle_channel_update(self, channel_type: LightChannel, dmx_index: int, value: int) -> None:
        """Handle updates from the DMX universe."""
        if self._controller.is_updating:
            return

        # First handle dimmer to determine on/off state if applicable
        if self._has_separate_dimmer:
            if channel_type == LightChannel.DIMMER:
                self._state.is_on = value > 0
        elif value > 0 and not self._state.is_on:
            self._state.is_on = True

        # Route the update to the appropriate state handler
        if channel_type == LightChannel.DIMMER:
            self._state.update_brightness(value)
        elif channel_type == LightChannel.RED:
            self._state.update_rgb(value, self._state.rgb_color[1], self._state.rgb_color[2])
        elif channel_type == LightChannel.GREEN:
            self._state.update_rgb(self._state.rgb_color[0], value, self._state.rgb_color[2])
        elif channel_type == LightChannel.BLUE:
            self._state.update_rgb(self._state.rgb_color[0], self._state.rgb_color[1], value)
        elif channel_type == LightChannel.COLD_WHITE:
            self._state.update_white(value, is_cold=True)
            # For single channel white lights
            if self.color_mode == ColorMode.BRIGHTNESS and not self._has_separate_dimmer:
                self._state.update_brightness(value)
        elif channel_type == LightChannel.WARM_WHITE:
            self._state.update_white(value, is_cold=False)
            # For single channel white lights
            if self.color_mode == ColorMode.BRIGHTNESS and not self._has_separate_dimmer:
                self._state.update_brightness(value)
        elif channel_type == LightChannel.COLOR_TEMPERATURE:
            self._state.update_color_temp(value)

        # If we don't have a separate dimmer, check if all channels are zero to determine off state
        if not self._has_separate_dimmer:
            # Skip COLOR_TEMPERATURE channel for determining on/off
            all_zero = self._check_if_all_channels_zero()
            if all_zero and self._state.is_on:
                self._state.is_on = False

        # Notify Home Assistant of the state change
        self.async_write_ha_state()

    def _check_if_all_channels_zero(self) -> bool:
        """Check if all relevant channels are at zero."""
        for ch_type in self._controller.channel_map.keys():
            # Skip color temperature channel when determining on/off state
            if ch_type == LightChannel.COLOR_TEMPERATURE:
                continue

            # Check state values based on channel type
            if (ch_type == LightChannel.RED and self._state.rgb_color[0] > 0) or \
                    (ch_type == LightChannel.GREEN and self._state.rgb_color[1] > 0) or \
                    (ch_type == LightChannel.BLUE and self._state.rgb_color[2] > 0) or \
                    (ch_type == LightChannel.COLD_WHITE and self._state.cold_white > 0) or \
                    (ch_type == LightChannel.WARM_WHITE and self._state.warm_white > 0) or \
                    (ch_type == LightChannel.DIMMER and self._state.brightness > 0):
                return False

        return True

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._state.is_on

    @property
    def brightness(self) -> int:
        """Return the brightness of this light."""
        return self._state.brightness

    @property
    def rgb_color(self) -> Tuple[int, int, int]:
        """Return the RGB color value [int, int, int]."""
        return self._state.rgb_color

    @property
    def rgbw_color(self) -> Optional[Tuple[int, int, int, int]]:
        """Return the RGBW color value [int, int, int, int]."""
        return getattr(self._state, "rgbw_color", None)

    @property
    def rgbww_color(self) -> Optional[Tuple[int, int, int, int, int]]:
        """Return the RGBWW color value [int, int, int, int, int]."""
        return getattr(self._state, "rgbww_color", None)

    @property
    def color_temp(self) -> int:
        """Return the color temperature in mireds."""
        return self._state.color_temp

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        await self._controller.turn_on(**kwargs)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._controller.turn_off()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Handle entity being added to Home Assistant."""
        await super().async_added_to_hass()

        # Restore state if available
        last_state = await self.async_get_last_state()
        if last_state:
            self._state.is_on = last_state.state == "on"
            if last_state.attributes.get("brightness"):
                self._state.brightness = last_state.attributes["brightness"]
