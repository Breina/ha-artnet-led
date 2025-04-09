import asyncio
from dataclasses import dataclass
from enum import Enum, auto
from functools import partial
from typing import List, Dict, Tuple

import homeassistant.util.color as color_util
from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.dmx import DOMAIN
from custom_components.dmx.fixture.channel import Channel
from custom_components.dmx.io.dmx_io import Universe


class LightChannel(Enum):
    RED = auto()
    GREEN = auto()
    BLUE = auto()
    COLD_WHITE = auto()
    WARM_WHITE = auto()
    COLOR_TEMPERATURE = auto()
    DIMMER = auto()


@dataclass
class AccumulatedLightChannel:
    dmx_channel_indexes: List[int]
    channel: Channel
    universe: Universe
    light_channel: LightChannel


class ClaudeLightEntity(LightEntity, RestoreEntity):
    """DMX/ArtNet light entity that supports various channel configurations."""

    def __init__(
            self,
            matrix_key: str,
            color_mode: ColorMode,
            channels: List[AccumulatedLightChannel],
            device: DeviceInfo,
            has_separate_dimmer: bool = False,
            min_kelvin: int = 2000,
            max_kelvin: int = 6500,
    ):
        """Initialize the light entity."""
        self._matrix_key = matrix_key
        self._attr_name = f"Light {matrix_key}"

        self._attr_device_info = device
        self._attr_unique_id = f"{DOMAIN}_light_{matrix_key}"

        self._channels = channels
        self._has_separate_dimmer = has_separate_dimmer
        self._min_kelvin = min_kelvin
        self._max_kelvin = max_kelvin

        # State attributes
        self._state = False
        self._brightness = 255
        self._rgb_color = (255, 255, 255)
        self._rgbw_color = (255, 255, 255, 255)
        self._rgbww_color = (255, 255, 255, 255, 255)
        self._color_temp = 500  # Mired scale
        self._cold_white = 255
        self._warm_white = 255
        self._color_temp_value = 255  # Direct color temp channel value

        # Last active state (to remember settings when turned off)
        self._last_brightness = 255
        self._last_rgb_color = (255, 255, 255)
        self._last_rgbw_color = (255, 255, 255, 255)
        self._last_rgbww_color = (255, 255, 255, 255, 255)
        self._last_color_temp = 500
        self._last_cold_white = 255
        self._last_warm_white = 255
        self._last_color_temp_value = 255

        # Initialize default values from channels' capabilities
        self._initialize_default_values()

        # Map channels by type for easy access
        self._channel_map: Dict[LightChannel, AccumulatedLightChannel] = {
            channel.light_channel: channel for channel in channels
        }

        # Set up color modes
        self._attr_color_mode = color_mode
        self._attr_supported_color_modes = {color_mode}

        # Min/max color temp in mired
        if ColorMode.COLOR_TEMP in self.supported_color_modes:
            self._attr_min_mireds = color_util.color_temperature_kelvin_to_mired(max_kelvin)
            self._attr_max_mireds = color_util.color_temperature_kelvin_to_mired(min_kelvin)

        # Set up channel handlers for different modes
        self._setup_turn_on_handlers()

        # Register channel listeners
        self._is_updating = False
        self._register_channel_listeners()

    def _initialize_default_values(self):
        """Initialize default values for channels based on their capabilities."""
        for channel_data in self._channels:
            channel = channel_data.channel
            light_channel = channel_data.light_channel

            # Check if there's a capability with menu_click
            if channel.capabilities and len(channel.capabilities) > 0:
                capability = channel.capabilities[0]

                # Set the default value based on menu_click
                if capability.menu_click:
                    default_value = capability.menu_click_value
                else:
                    default_value = 0

                # Update the corresponding state attribute based on channel type
                self._set_initial_channel_value(light_channel, default_value)

    def _set_initial_channel_value(self, light_channel: LightChannel, value: int):
        """Set the initial value for a channel based on its type."""
        if light_channel == LightChannel.RED:
            self._rgb_color = (value, self._rgb_color[1], self._rgb_color[2])
            self._rgbw_color = (value, self._rgbw_color[1], self._rgbw_color[2], self._rgbw_color[3])
            self._rgbww_color = (value, self._rgbww_color[1], self._rgbww_color[2],
                                 self._rgbww_color[3], self._rgbww_color[4])
        elif light_channel == LightChannel.GREEN:
            self._rgb_color = (self._rgb_color[0], value, self._rgb_color[2])
            self._rgbw_color = (self._rgbw_color[0], value, self._rgbw_color[2], self._rgbw_color[3])
            self._rgbww_color = (self._rgbww_color[0], value, self._rgbww_color[2],
                                 self._rgbww_color[3], self._rgbww_color[4])
        elif light_channel == LightChannel.BLUE:
            self._rgb_color = (self._rgb_color[0], self._rgb_color[1], value)
            self._rgbw_color = (self._rgbw_color[0], self._rgbw_color[1], value, self._rgbw_color[3])
            self._rgbww_color = (self._rgbww_color[0], self._rgbww_color[1], value,
                                 self._rgbww_color[3], self._rgbww_color[4])
        elif light_channel == LightChannel.COLD_WHITE:
            self._cold_white = value
            self._rgbw_color = (self._rgbw_color[0], self._rgbw_color[1], self._rgbw_color[2], value)
            self._rgbww_color = (self._rgbww_color[0], self._rgbww_color[1], self._rgbww_color[2],
                                 value, self._rgbww_color[4])
        elif light_channel == LightChannel.WARM_WHITE:
            self._warm_white = value
            self._rgbww_color = (self._rgbww_color[0], self._rgbww_color[1], self._rgbww_color[2],
                                 self._rgbww_color[3], value)
        elif light_channel == LightChannel.COLOR_TEMPERATURE:
            self._color_temp_value = value
            # Convert DMX value to mired color temperature
            if hasattr(self, "min_mireds") and hasattr(self, "max_mireds"):
                ratio = value / 255
                self._color_temp = self.min_mireds + ratio * (self.max_mireds - self.min_mireds)
        elif light_channel == LightChannel.DIMMER:
            self._brightness = value
            # If value > 0, also set state to True
            if value > 0:
                self._state = True

    def _setup_turn_on_handlers(self):
        """Pre-configure optimized handlers for different turn_on scenarios."""
        self._turn_on_handlers = {}

        # Turn on handler (basic on/off)
        self._turn_on_handlers["turn_on"] = partial(self._handle_turn_on)

        # Brightness handler
        if self._has_separate_dimmer:
            self._turn_on_handlers["brightness"] = partial(
                self._handle_dimmer_brightness,
                self._channel_map[LightChannel.DIMMER]
            )
        elif LightChannel.COLD_WHITE in self._channel_map and self.color_mode == ColorMode.BRIGHTNESS:
            self._turn_on_handlers["brightness"] = partial(
                self._handle_white_brightness,
                self._channel_map[LightChannel.COLD_WHITE]
            )
        elif LightChannel.WARM_WHITE in self._channel_map and self.color_mode == ColorMode.BRIGHTNESS:
            self._turn_on_handlers["brightness"] = partial(
                self._handle_white_brightness,
                self._channel_map[LightChannel.WARM_WHITE]
            )

        # RGB handlers
        if self.color_mode in (ColorMode.RGB, ColorMode.RGBW, ColorMode.RGBWW):
            if all(ch in self._channel_map for ch in [LightChannel.RED, LightChannel.GREEN, LightChannel.BLUE]):
                self._turn_on_handlers["rgb"] = partial(
                    self._handle_rgb,
                    self._channel_map[LightChannel.RED],
                    self._channel_map[LightChannel.GREEN],
                    self._channel_map[LightChannel.BLUE]
                )

        # RGBW/RGBWW additional handlers
        if self.color_mode in (ColorMode.RGBW, ColorMode.RGBWW):
            if LightChannel.COLD_WHITE in self._channel_map:
                self._turn_on_handlers["white"] = partial(
                    self._handle_white,
                    self._channel_map[LightChannel.COLD_WHITE]
                )

        # Color temperature handlers
        if self.color_mode in (ColorMode.COLOR_TEMP, ColorMode.RGBWW):
            if LightChannel.COLOR_TEMPERATURE in self._channel_map:
                self._turn_on_handlers["color_temp_channel"] = partial(
                    self._handle_color_temp_channel,
                    self._channel_map[LightChannel.COLOR_TEMPERATURE]
                )
            elif all(ch in self._channel_map for ch in [LightChannel.COLD_WHITE, LightChannel.WARM_WHITE]):
                self._turn_on_handlers["color_temp_cw"] = partial(
                    self._handle_color_temp_cw,
                    self._channel_map[LightChannel.COLD_WHITE],
                    self._channel_map[LightChannel.WARM_WHITE]
                )

    def _register_channel_listeners(self):
        """Register listeners for all channels."""
        for channel_type, channel_data in self._channel_map.items():
            for dmx_index in channel_data.dmx_channel_indexes:
                channel_data.universe.register_channel_listener(
                    dmx_index,
                    partial(self._handle_channel_update, channel_type)
                )

    @callback
    def _handle_channel_update(self, channel_type: LightChannel, dmx_index: int, value: int):
        """Handle updates from the DMX universe for a specific channel."""
        if self._has_separate_dimmer:
            if channel_type == LightChannel.DIMMER:
                self._state = not value == 0
        elif value > 0 and not self._state:
            self._state = True

        # Map different channel types to appropriate state properties
        if channel_type == LightChannel.DIMMER:
            self._brightness = value
            if value > 0:
                self._last_brightness = value
        elif channel_type == LightChannel.RED:
            self._rgb_color = (value, self._rgb_color[1], self._rgb_color[2])
            if value > 0 or self._rgb_color[1] > 0 or self._rgb_color[2] > 0:
                self._last_rgb_color = self._rgb_color

            if hasattr(self, "_rgbw_color"):
                self._rgbw_color = (value, self._rgbw_color[1], self._rgbw_color[2], self._rgbw_color[3])
                if value > 0 or self._rgbw_color[1] > 0 or self._rgbw_color[2] > 0 or self._rgbw_color[3] > 0:
                    self._last_rgbw_color = self._rgbw_color

            if hasattr(self, "_rgbww_color"):
                self._rgbww_color = (value, self._rgbww_color[1], self._rgbww_color[2],
                                     self._rgbww_color[3], self._rgbww_color[4])
                if any(c > 0 for c in self._rgbww_color):
                    self._last_rgbww_color = self._rgbww_color
        elif channel_type == LightChannel.GREEN:
            self._rgb_color = (self._rgb_color[0], value, self._rgb_color[2])
            if self._rgb_color[0] > 0 or value > 0 or self._rgb_color[2] > 0:
                self._last_rgb_color = self._rgb_color

            if hasattr(self, "_rgbw_color"):
                self._rgbw_color = (self._rgbw_color[0], value, self._rgbw_color[2], self._rgbw_color[3])
                if any(c > 0 for c in self._rgbw_color):
                    self._last_rgbw_color = self._rgbw_color

            if hasattr(self, "_rgbww_color"):
                self._rgbww_color = (self._rgbww_color[0], value, self._rgbww_color[2],
                                     self._rgbww_color[3], self._rgbww_color[4])
                if any(c > 0 for c in self._rgbww_color):
                    self._last_rgbww_color = self._rgbww_color
        elif channel_type == LightChannel.BLUE:
            self._rgb_color = (self._rgb_color[0], self._rgb_color[1], value)
            if self._rgb_color[0] > 0 or self._rgb_color[1] > 0 or value > 0:
                self._last_rgb_color = self._rgb_color

            if hasattr(self, "_rgbw_color"):
                self._rgbw_color = (self._rgbw_color[0], self._rgbw_color[1], value, self._rgbw_color[3])
                if any(c > 0 for c in self._rgbw_color):
                    self._last_rgbw_color = self._rgbw_color

            if hasattr(self, "_rgbww_color"):
                self._rgbww_color = (self._rgbww_color[0], self._rgbww_color[1], value,
                                     self._rgbww_color[3], self._rgbww_color[4])
                if any(c > 0 for c in self._rgbww_color):
                    self._last_rgbww_color = self._rgbww_color
        elif channel_type == LightChannel.COLD_WHITE:
            self._cold_white = value
            if value > 0:
                self._last_cold_white = value

            if self.color_mode == ColorMode.RGBW:
                self._rgbw_color = (self._rgbw_color[0], self._rgbw_color[1], self._rgbw_color[2], value)
                if any(c > 0 for c in self._rgbw_color):
                    self._last_rgbw_color = self._rgbw_color

            elif self.color_mode == ColorMode.RGBWW:
                self._rgbww_color = (self._rgbww_color[0], self._rgbww_color[1], self._rgbww_color[2],
                                     value, self._rgbww_color[4])
                if any(c > 0 for c in self._rgbww_color):
                    self._last_rgbww_color = self._rgbww_color

            elif self.color_mode == ColorMode.BRIGHTNESS and not self._has_separate_dimmer:
                self._brightness = value
                if value > 0:
                    self._last_brightness = value
        elif channel_type == LightChannel.WARM_WHITE:
            self._warm_white = value
            if value > 0:
                self._last_warm_white = value

            if self.color_mode == ColorMode.RGBW:
                self._rgbw_color = (self._rgbw_color[0], self._rgbw_color[1], self._rgbw_color[2], value)
                if any(c > 0 for c in self._rgbw_color):
                    self._last_rgbw_color = self._rgbw_color

            elif self.color_mode == ColorMode.RGBWW:
                self._rgbww_color = (self._rgbww_color[0], self._rgbww_color[1], self._rgbww_color[2],
                                     self._rgbww_color[3], value)
                if any(c > 0 for c in self._rgbww_color):
                    self._last_rgbww_color = self._rgbww_color

            elif self.color_mode == ColorMode.BRIGHTNESS and not self._has_separate_dimmer:
                self._brightness = value
                if value > 0:
                    self._last_brightness = value
        elif channel_type == LightChannel.COLOR_TEMPERATURE:
            self._color_temp_value = value
            if value > 0:
                self._last_color_temp_value = value

            # Convert DMX value to mired color temperature
            ratio = value / 255
            self._color_temp = self.min_mireds + ratio * (self.max_mireds - self.min_mireds)
            if value > 0:
                self._last_color_temp = self._color_temp

        # Check if all channels are 0 to determine if light is off
        if not self._has_separate_dimmer:
            all_zero = True
            for ch_type, ch_data in self._channel_map.items():
                # Skip checking color temp channel for determining on/off state
                if ch_type == LightChannel.COLOR_TEMPERATURE:
                    continue

                for dmx_idx in ch_data.dmx_channel_indexes:
                    # We need to actually check the current DMX value, which we don't have direct access to
                    # This is an approximation based on our tracked state
                    if (ch_type == LightChannel.RED and self._rgb_color[0] > 0) or \
                            (ch_type == LightChannel.GREEN and self._rgb_color[1] > 0) or \
                            (ch_type == LightChannel.BLUE and self._rgb_color[2] > 0) or \
                            (ch_type == LightChannel.COLD_WHITE and self._cold_white > 0) or \
                            (ch_type == LightChannel.WARM_WHITE and self._warm_white > 0) or \
                            (ch_type == LightChannel.DIMMER and self._brightness > 0):
                        all_zero = False
                        break

                if not all_zero:
                    break

            if all_zero and self._state:
                self._state = False

        # Notify Home Assistant of the state change
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._state

    @property
    def brightness(self) -> int:
        """Return the brightness of this light."""
        return self._brightness

    @property
    def rgb_color(self) -> Tuple[int, int, int]:
        """Return the RGB color value [int, int, int]."""
        return self._rgb_color

    @property
    def rgbw_color(self) -> Tuple[int, int, int, int]:
        """Return the RGBW color value [int, int, int, int]."""
        if hasattr(self, "_rgbw_color"):
            return self._rgbw_color
        return None

    @property
    def rgbww_color(self) -> Tuple[int, int, int, int, int]:
        """Return the RGBWW color value [int, int, int, int, int]."""
        if hasattr(self, "_rgbww_color"):
            return self._rgbww_color
        return None

    @property
    def color_temp(self) -> int:
        """Return the color temperature in mireds."""
        return self._color_temp

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on."""
        self._state = True

        # Process specific attributes if provided
        has_specific_attributes = False

        if "brightness" in kwargs and "brightness" in self._turn_on_handlers:
            await self._turn_on_handlers["brightness"](kwargs["brightness"])
            has_specific_attributes = True

        if "rgb_color" in kwargs and "rgb" in self._turn_on_handlers:
            await self._turn_on_handlers["rgb"](kwargs["rgb_color"])
            has_specific_attributes = True

        if "rgbw_color" in kwargs:
            rgb = kwargs["rgbw_color"][:3]
            white = kwargs["rgbw_color"][3]

            if "rgb" in self._turn_on_handlers:
                await self._turn_on_handlers["rgb"](rgb)

            if "white" in self._turn_on_handlers:
                await self._turn_on_handlers["white"](white)

            has_specific_attributes = True

        if "rgbww_color" in kwargs:
            rgb = kwargs["rgbww_color"][:3]
            cold_white = kwargs["rgbww_color"][3]
            warm_white = kwargs["rgbww_color"][4]

            if "rgb" in self._turn_on_handlers:
                await self._turn_on_handlers["rgb"](rgb)

            if LightChannel.COLD_WHITE in self._channel_map:
                await self._update_channel_value(self._channel_map[LightChannel.COLD_WHITE], cold_white)

            if LightChannel.WARM_WHITE in self._channel_map:
                await self._update_channel_value(self._channel_map[LightChannel.WARM_WHITE], warm_white)

            has_specific_attributes = True

        if "color_temp" in kwargs:
            if "color_temp_channel" in self._turn_on_handlers:
                await self._turn_on_handlers["color_temp_channel"](kwargs["color_temp"])
            elif "color_temp_cw" in self._turn_on_handlers:
                await self._turn_on_handlers["color_temp_cw"](kwargs["color_temp"])

            has_specific_attributes = True

        # If no specific features were requested, restore previous state
        if not has_specific_attributes:
            # If we have a dimmer, prioritize just restoring the dimmer value
            if self._has_separate_dimmer and LightChannel.DIMMER in self._channel_map:
                # Use the last active brightness value
                brightness = self._last_brightness
                await self._update_channel_value(
                    self._channel_map[LightChannel.DIMMER],
                    brightness
                )
            else:
                # No dimmer - restore full previous state
                await self._restore_previous_state()

        # Update state
        self.async_write_ha_state()

    async def _restore_previous_state(self):
        """Restore the light's previous state using last active values."""
        tasks = []

        # Handle RGB channels
        if self.color_mode in (ColorMode.RGB, ColorMode.RGBW, ColorMode.RGBWW):
            if all(ch in self._channel_map for ch in [LightChannel.RED, LightChannel.GREEN, LightChannel.BLUE]):
                tasks.append(self._update_channel_value(self._channel_map[LightChannel.RED], self._last_rgb_color[0]))
                tasks.append(self._update_channel_value(self._channel_map[LightChannel.GREEN], self._last_rgb_color[1]))
                tasks.append(self._update_channel_value(self._channel_map[LightChannel.BLUE], self._last_rgb_color[2]))

        # Handle white channels
        if self.color_mode in (ColorMode.RGBW, ColorMode.RGBWW, ColorMode.COLOR_TEMP):
            if LightChannel.COLD_WHITE in self._channel_map:
                tasks.append(self._update_channel_value(self._channel_map[LightChannel.COLD_WHITE], self._last_cold_white))

            if LightChannel.WARM_WHITE in self._channel_map:
                tasks.append(self._update_channel_value(self._channel_map[LightChannel.WARM_WHITE], self._last_warm_white))

        # Handle color temperature channel
        if LightChannel.COLOR_TEMPERATURE in self._channel_map:
            tasks.append(self._update_channel_value(
                self._channel_map[LightChannel.COLOR_TEMPERATURE],
                self._last_color_temp_value
            ))

        # Handle brightness mode
        if self.color_mode == ColorMode.BRIGHTNESS:
            if LightChannel.COLD_WHITE in self._channel_map:
                tasks.append(self._update_channel_value(self._channel_map[LightChannel.COLD_WHITE], self._last_brightness))
            elif LightChannel.WARM_WHITE in self._channel_map:
                tasks.append(self._update_channel_value(self._channel_map[LightChannel.WARM_WHITE], self._last_brightness))

        # Handle dimmer if present
        if self._has_separate_dimmer and LightChannel.DIMMER in self._channel_map:
            tasks.append(self._update_channel_value(self._channel_map[LightChannel.DIMMER], self._last_brightness))

        if tasks:
            await asyncio.gather(*tasks)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        self._state = False

        # If we have a separate dimmer channel, only set that to 0
        if self._has_separate_dimmer and LightChannel.DIMMER in self._channel_map:
            dimmer_channel = self._channel_map[LightChannel.DIMMER]
            for dmx_index in dimmer_channel.dmx_channel_indexes:
                await dimmer_channel.universe.update_value(dmx_index, 0)

            # Set brightness to 0 in state
            self._brightness = 0
        else:
            # No dimmer channel, so set all channels to 0
            self._is_updating = True
            try:
                for ch_data in self._channels:
                    for dmx_index in ch_data.dmx_channel_indexes:
                        await ch_data.universe.update_value(dmx_index, 0)
            finally:
                self._is_updating = False

            # Set all state values to 0
            self._brightness = 0
            self._rgb_color = (0, 0, 0)
            self._cold_white = 0
            self._warm_white = 0
            if hasattr(self, "_rgbw_color"):
                self._rgbw_color = (0, 0, 0, 0)
            if hasattr(self, "_rgbww_color"):
                self._rgbww_color = (0, 0, 0, 0, 0)

        # Update state
        self.async_write_ha_state()

    # Update state
    async def _handle_turn_on(self):
        """Handle basic turn on with previous state."""
        tasks = []

        # Restore previous state or use defaults
        if self._has_separate_dimmer and LightChannel.DIMMER in self._channel_map:
            # Use the stored brightness value, but ensure it's not 0 (which would keep the light off)
            brightness = self._brightness if self._brightness > 0 else 255
            tasks.append(self._update_channel_value(
                self._channel_map[LightChannel.DIMMER],
                brightness
            ))

            # With a separate dimmer, we may not need to change any other channels
            # as they should have retained their values when turning off
        else:
            # No separate dimmer - need to restore all channel values

            if self.color_mode in (ColorMode.RGB, ColorMode.RGBW, ColorMode.RGBWW):
                if all(ch in self._channel_map for ch in [LightChannel.RED, LightChannel.GREEN, LightChannel.BLUE]):
                    # Use stored RGB values
                    tasks.append(self._update_channel_value(self._channel_map[LightChannel.RED], self._rgb_color[0]))
                    tasks.append(self._update_channel_value(self._channel_map[LightChannel.GREEN], self._rgb_color[1]))
                    tasks.append(self._update_channel_value(self._channel_map[LightChannel.BLUE], self._rgb_color[2]))

            if self.color_mode in (ColorMode.RGBW, ColorMode.RGBWW, ColorMode.COLOR_TEMP):
                if LightChannel.COLD_WHITE in self._channel_map:
                    tasks.append(self._update_channel_value(self._channel_map[LightChannel.COLD_WHITE], self._cold_white))

                if LightChannel.WARM_WHITE in self._channel_map:
                    tasks.append(self._update_channel_value(self._channel_map[LightChannel.WARM_WHITE], self._warm_white))

            if LightChannel.COLOR_TEMPERATURE in self._channel_map:
                tasks.append(self._update_channel_value(
                    self._channel_map[LightChannel.COLOR_TEMPERATURE],
                    self._color_temp_value
                ))

            if self.color_mode == ColorMode.BRIGHTNESS:
                if LightChannel.COLD_WHITE in self._channel_map:
                    brightness = self._brightness if self._brightness > 0 else 255
                    tasks.append(self._update_channel_value(self._channel_map[LightChannel.COLD_WHITE], brightness))

                elif LightChannel.WARM_WHITE in self._channel_map:
                    brightness = self._brightness if self._brightness > 0 else 255
                    tasks.append(self._update_channel_value(self._channel_map[LightChannel.WARM_WHITE], brightness))

        # For completeness, also set other channels if using a separate dimmer
        # This ensures all channels return to their previous state
        if self._has_separate_dimmer:
            if self.color_mode in (ColorMode.RGB, ColorMode.RGBW, ColorMode.RGBWW):
                if all(ch in self._channel_map for ch in [LightChannel.RED, LightChannel.GREEN, LightChannel.BLUE]):
                    # We don't need to set these again - they should have retained their values
                    # But include them in case they need to be restored from a fresh start
                    tasks.append(self._update_channel_value(self._channel_map[LightChannel.RED], self._rgb_color[0]))
                    tasks.append(self._update_channel_value(self._channel_map[LightChannel.GREEN], self._rgb_color[1]))
                    tasks.append(self._update_channel_value(self._channel_map[LightChannel.BLUE], self._rgb_color[2]))

            if self.color_mode in (ColorMode.RGBW, ColorMode.RGBWW, ColorMode.COLOR_TEMP):
                if LightChannel.COLD_WHITE in self._channel_map:
                    tasks.append(self._update_channel_value(self._channel_map[LightChannel.COLD_WHITE], self._cold_white))

                if LightChannel.WARM_WHITE in self._channel_map:
                    tasks.append(self._update_channel_value(self._channel_map[LightChannel.WARM_WHITE], self._warm_white))

            if LightChannel.COLOR_TEMPERATURE in self._channel_map:
                tasks.append(self._update_channel_value(
                    self._channel_map[LightChannel.COLOR_TEMPERATURE],
                    self._color_temp_value
                ))

        if tasks:
            await asyncio.gather(*tasks)

    async def _handle_dimmer_brightness(self, channel_data: AccumulatedLightChannel, brightness: int):
        """Handle brightness using a dedicated dimmer channel."""
        self._brightness = brightness
        await self._update_channel_value(channel_data, brightness)

    async def _handle_white_brightness(self, channel_data: AccumulatedLightChannel, brightness: int):
        """Handle brightness using white channel when no dedicated dimmer exists."""
        self._brightness = brightness
        await self._update_channel_value(channel_data, brightness)

    async def _handle_rgb(self, red_channel: AccumulatedLightChannel,
                          green_channel: AccumulatedLightChannel,
                          blue_channel: AccumulatedLightChannel,
                          rgb: Tuple[int, int, int]):
        """Handle RGB color updates."""
        self._rgb_color = rgb

        # Update RGBW/RGBWW properties if applicable
        if hasattr(self, "_rgbw_color"):
            self._rgbw_color = (rgb[0], rgb[1], rgb[2], self._rgbw_color[3])

        if hasattr(self, "_rgbww_color"):
            self._rgbww_color = (rgb[0], rgb[1], rgb[2], self._rgbww_color[3], self._rgbww_color[4])

        # Update DMX channels
        await asyncio.gather(
            self._update_channel_value(red_channel, rgb[0]),
            self._update_channel_value(green_channel, rgb[1]),
            self._update_channel_value(blue_channel, rgb[2])
        )

    async def _handle_white(self, white_channel: AccumulatedLightChannel, white_value: int):
        """Handle white channel updates for RGBW mode."""
        if self.color_mode == ColorMode.RGBW:
            self._rgbw_color = (self._rgbw_color[0], self._rgbw_color[1], self._rgbw_color[2], white_value)

        await self._update_channel_value(white_channel, white_value)

    async def _handle_color_temp_channel(self, temp_channel: AccumulatedLightChannel, temp_mired: int):
        """Handle color temperature via a dedicated color temp channel."""
        self._color_temp = temp_mired

        # Convert mired to DMX value (0-255)
        ratio = (temp_mired - self.min_mireds) / (self.max_mireds - self.min_mireds)
        dmx_value = int(ratio * 255)
        self._color_temp_value = dmx_value

        await self._update_channel_value(temp_channel, dmx_value)

    async def _handle_color_temp_cw(self, cold_channel: AccumulatedLightChannel,
                                    warm_channel: AccumulatedLightChannel,
                                    temp_mired: int):
        """Handle color temperature using cold/warm white channels."""
        self._color_temp = temp_mired

        # Calculate cold/warm mix based on color temperature
        # Map mired value to ratio between warm (max_mireds) and cold (min_mireds)
        ratio = (temp_mired - self.min_mireds) / (self.max_mireds - self.min_mireds)
        warm_value = int(ratio * 255)
        cold_value = int((1 - ratio) * 255)

        self._cold_white = cold_value
        self._warm_white = warm_value

        if self.color_mode == ColorMode.RGBWW:
            self._rgbww_color = (
                self._rgbww_color[0],
                self._rgbww_color[1],
                self._rgbww_color[2],
                cold_value,
                warm_value
            )

        await asyncio.gather(
            self._update_channel_value(cold_channel, cold_value),
            self._update_channel_value(warm_channel, warm_value)
        )

    async def _update_channel_value(self, channel_data: AccumulatedLightChannel, value: int):
        """Update the value of a DMX channel."""
        # Ensure the value is in the valid DMX range (0-255)
        dmx_value = min(255, max(0, value))

        # Update all associated DMX channels (some light channels may use multiple DMX channels)
        for dmx_index in channel_data.dmx_channel_indexes:
            await channel_data.universe.update_value(dmx_index, dmx_value)