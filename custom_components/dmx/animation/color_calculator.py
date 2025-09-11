import math
from typing import ClassVar

from custom_components.dmx.entity.light import ChannelType


class ColorSpaceConverter:
    """Handles conversions between different color spaces."""

    # D65 white point constants
    XN, YN, ZN = 0.95047, 1.00000, 1.08883

    # sRGB transformation matrices
    RGB_TO_XYZ_MATRIX: ClassVar[tuple[tuple[float, float, float], ...]] = (
        (0.4124564, 0.3575761, 0.1804375),
        (0.2126729, 0.7151522, 0.0721750),
        (0.0193339, 0.1191920, 0.9503041),
    )

    XYZ_TO_RGB_MATRIX: ClassVar[tuple[tuple[float, float, float], ...]] = (
        (3.2404542, -1.5371385, -0.4985314),
        (-0.9692660, 1.8760108, 0.0415560),
        (0.0556434, -0.2040259, 1.0572252),
    )

    @staticmethod
    def gamma_correct(value: float) -> float:
        """Apply gamma correction for sRGB."""
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    @staticmethod
    def inverse_gamma_correct(value: float) -> float:
        """Apply inverse gamma correction for sRGB."""
        return 12.92 * value if value <= 0.0031308 else 1.055 * (value ** (1 / 2.4)) - 0.055

    @classmethod
    def rgb_to_xyz(cls, rgb: tuple[float, float, float]) -> tuple[float, float, float]:
        """Convert RGB to XYZ color space using sRGB matrix."""
        r, g, b = [cls.gamma_correct(c) for c in rgb]

        # FIX: Remove the buggy matrix multiplication code and use the correct implementation
        x = r * cls.RGB_TO_XYZ_MATRIX[0][0] + g * cls.RGB_TO_XYZ_MATRIX[0][1] + b * cls.RGB_TO_XYZ_MATRIX[0][2]
        y = r * cls.RGB_TO_XYZ_MATRIX[1][0] + g * cls.RGB_TO_XYZ_MATRIX[1][1] + b * cls.RGB_TO_XYZ_MATRIX[1][2]
        z = r * cls.RGB_TO_XYZ_MATRIX[2][0] + g * cls.RGB_TO_XYZ_MATRIX[2][1] + b * cls.RGB_TO_XYZ_MATRIX[2][2]

        return (x, y, z)

    @classmethod
    def xyz_to_rgb(cls, xyz: tuple[float, float, float]) -> tuple[float, float, float]:
        """Convert XYZ to RGB color space."""
        x, y, z = xyz

        r = x * cls.XYZ_TO_RGB_MATRIX[0][0] + y * cls.XYZ_TO_RGB_MATRIX[0][1] + z * cls.XYZ_TO_RGB_MATRIX[0][2]
        g = x * cls.XYZ_TO_RGB_MATRIX[1][0] + y * cls.XYZ_TO_RGB_MATRIX[1][1] + z * cls.XYZ_TO_RGB_MATRIX[1][2]
        b = x * cls.XYZ_TO_RGB_MATRIX[2][0] + y * cls.XYZ_TO_RGB_MATRIX[2][1] + z * cls.XYZ_TO_RGB_MATRIX[2][2]

        # Apply inverse gamma correction and clamp
        return tuple(max(0.0, min(1.0, cls.inverse_gamma_correct(c))) for c in (r, g, b))

    @classmethod
    def xyz_to_luv(cls, xyz: tuple[float, float, float]) -> tuple[float, float, float]:
        """Convert XYZ to L*u*v* color space."""
        x, y, z = xyz

        # Calculate u' and v' for the color and white point
        def get_uv_prime(x, y, z):
            denominator = x + 15 * y + 3 * z
            return (4 * x / denominator, 9 * y / denominator) if denominator != 0 else (0, 0)

        u_prime, v_prime = get_uv_prime(x, y, z)
        u_prime_n, v_prime_n = get_uv_prime(cls.XN, cls.YN, cls.ZN)

        # Calculate L*
        y_ratio = y / cls.YN
        l_star = 116 * (y_ratio ** (1 / 3)) - 16 if y_ratio > 0.008856 else 903.3 * y_ratio

        # Calculate u* and v*
        u_star = 13 * l_star * (u_prime - u_prime_n)
        v_star = 13 * l_star * (v_prime - v_prime_n)

        return (l_star, u_star, v_star)

    @classmethod
    def luv_to_xyz(cls, luv: tuple[float, float, float]) -> tuple[float, float, float]:
        """Convert L*u*v* to XYZ color space."""
        l_star, u_star, v_star = luv

        # Calculate white point u' and v'
        denominator_n = cls.XN + 15 * cls.YN + 3 * cls.ZN
        u_prime_n = 4 * cls.XN / denominator_n
        v_prime_n = 9 * cls.YN / denominator_n

        # Calculate Y
        y = cls.YN * (((l_star + 16) / 116) ** 3) if l_star > 8 else cls.YN * l_star / 903.3

        # Calculate u' and v'
        if l_star != 0:
            u_prime = u_star / (13 * l_star) + u_prime_n
            v_prime = v_star / (13 * l_star) + v_prime_n
        else:
            u_prime, v_prime = u_prime_n, v_prime_n

        # Calculate X and Z
        if v_prime != 0:
            x = y * 9 * u_prime / (4 * v_prime)
            z = y * (12 - 3 * u_prime - 20 * v_prime) / (4 * v_prime)
        else:
            x = z = 0

        return (x, y, z)

    @classmethod
    def rgb_to_luv(cls, rgb: tuple[float, float, float]) -> tuple[float, float, float]:
        """Convert RGB to L*u*v* color space."""
        return cls.xyz_to_luv(cls.rgb_to_xyz(rgb))

    @classmethod
    def luv_to_rgb(cls, luv: tuple[float, float, float]) -> tuple[float, float, float]:
        """Convert L*u*v* to RGB color space."""
        return cls.xyz_to_rgb(cls.luv_to_xyz(luv))


class TemperatureConverter:
    """Handles color temperature conversions."""

    @staticmethod
    def kelvin_to_rgb(kelvin: float) -> tuple[float, float, float]:
        """Convert color temperature in Kelvin to RGB values (0-1 range)."""
        temp = kelvin / 100.0

        # Calculate red
        r = 1.0 if temp <= 66 else max(0, min(255, 329.698727446 * ((temp - 60) ** -0.1332047592))) / 255.0

        # Calculate green
        if temp <= 66:
            g = max(0, min(255, 99.4708025861 * math.log(temp) - 161.1195681661)) / 255.0
        else:
            g = max(0, min(255, 288.1221695283 * ((temp - 60) ** -0.0755148492))) / 255.0

        # Calculate blue
        if temp >= 66:
            b = 1.0
        elif temp <= 19:
            b = 0.0
        else:
            b = max(0.0, min(255.0, 138.5177312231 * math.log(temp - 10) - 305.0447927307)) / 255.0

        return (r, g, b)

    @staticmethod
    def rgb_to_kelvin(rgb: tuple[float, float, float], min_kelvin: float, max_kelvin: float) -> float:
        """Estimate color temperature from RGB values."""
        r, _, b = rgb

        if r == 0 and b == 0:
            return (min_kelvin + max_kelvin) / 2

        # Normalize to prevent issues with very bright or dim colors
        max_component = max(r, b)
        if max_component == 0:
            return (min_kelvin + max_kelvin) / 2

        r_norm, b_norm = r / max_component, b / max_component

        # Calculate color temperature using improved heuristic
        if b_norm > 0:
            rb_ratio = r_norm / b_norm
            if rb_ratio >= 1.0:
                # Red dominant = warmer
                temp_factor = 1.0 / (1.0 + math.exp(-(rb_ratio - 1.0) * 2))
                temp = min_kelvin + temp_factor * (max_kelvin - min_kelvin) * 0.3
            else:
                # Blue dominant = cooler
                temp_factor = 1.0 / (1.0 + math.exp((rb_ratio - 1.0) * 2))
                temp = min_kelvin + (1.0 - temp_factor) * (max_kelvin - min_kelvin)
        else:
            temp = min_kelvin

        return max(min_kelvin, min(max_kelvin, temp))


class ChannelConverter:
    """Handles conversions between different channel types and RGB."""

    def __init__(self, min_kelvin: float = 2700, max_kelvin: float = 6500):
        self.min_kelvin = min_kelvin
        self.max_kelvin = max_kelvin

    def channels_to_rgb(self, channels: dict[ChannelType, float]) -> tuple[float, float, float]:
        """Convert various channel types to RGB values (0-1 range)."""
        r = channels.get(ChannelType.RED, 0) / 255.0
        g = channels.get(ChannelType.GREEN, 0) / 255.0
        b = channels.get(ChannelType.BLUE, 0) / 255.0

        # Handle white channels
        white_contribution, white_temp = self._calculate_white_contribution(channels)

        if white_contribution > 0:
            white_rgb = TemperatureConverter.kelvin_to_rgb(white_temp)
            r += white_rgb[0] * white_contribution
            g += white_rgb[1] * white_contribution
            b += white_rgb[2] * white_contribution

        # Handle dimmer (only if not using color temperature control)
        if ChannelType.DIMMER in channels and ChannelType.COLOR_TEMPERATURE not in channels:
            dimmer = channels[ChannelType.DIMMER] / 255.0
            r, g, b = r * dimmer, g * dimmer, b * dimmer

        return (min(1.0, r), min(1.0, g), min(1.0, b))

    def _calculate_white_contribution(self, channels: dict[ChannelType, float]) -> tuple[float, float]:
        """Calculate white light contribution and temperature."""
        if ChannelType.WARM_WHITE in channels and ChannelType.COLD_WHITE in channels:
            warm = channels[ChannelType.WARM_WHITE] / 255.0
            cold = channels[ChannelType.COLD_WHITE] / 255.0
            total_white = warm + cold

            if total_white > 0:
                # Weighted average of color temperatures
                white_temp = (warm * self.min_kelvin + cold * self.max_kelvin) / total_white
                return total_white, white_temp

        elif ChannelType.WARM_WHITE in channels:
            return channels[ChannelType.WARM_WHITE] / 255.0, self.min_kelvin

        elif ChannelType.COLD_WHITE in channels:
            return channels[ChannelType.COLD_WHITE] / 255.0, self.max_kelvin

        elif ChannelType.COLOR_TEMPERATURE in channels:
            dimmer = channels.get(ChannelType.DIMMER, 255) / 255.0
            temp_ratio = channels[ChannelType.COLOR_TEMPERATURE] / 255.0
            white_temp = self.min_kelvin + temp_ratio * (self.max_kelvin - self.min_kelvin)
            return dimmer, white_temp

        return 0.0, self.min_kelvin

    def rgb_to_channels(
        self,
        rgb: tuple[float, float, float],
        original_channels: set[ChannelType],
        progress: float,
        current_values: dict[ChannelType, float],
        desired_values: dict[ChannelType, float],
    ) -> dict[ChannelType, float]:
        """Convert RGB back to the original channel format."""
        r, g, b = rgb
        result = {}

        for channel in original_channels:
            result[channel] = 0

        if {ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE}.issubset(original_channels):
            result.update(
                {ChannelType.RED: round(r * 255), ChannelType.GREEN: round(g * 255), ChannelType.BLUE: round(b * 255)}
            )

            # Handle W channel in RGBW
            if ChannelType.WARM_WHITE in original_channels:
                current_w = current_values.get(ChannelType.WARM_WHITE, 0)
                desired_w = desired_values.get(ChannelType.WARM_WHITE, 0)
                result[ChannelType.WARM_WHITE] = round(current_w + (desired_w - current_w) * progress)

            if ChannelType.COLD_WHITE in original_channels:
                current_cw = current_values.get(ChannelType.COLD_WHITE, 0)
                desired_cw = desired_values.get(ChannelType.COLD_WHITE, 0)
                result[ChannelType.COLD_WHITE] = round(current_cw + (desired_cw - current_cw) * progress)

        elif {ChannelType.WARM_WHITE, ChannelType.COLD_WHITE}.issubset(original_channels):
            result.update(self._rgb_to_ww_cw(rgb))

        elif ChannelType.COLOR_TEMPERATURE in original_channels:
            result.update(self._rgb_to_color_temp(rgb))

        else:
            # Fallback: interpolate channels directly
            for channel in original_channels:
                current_val = current_values.get(channel, 0)
                desired_val = desired_values.get(channel, 0)
                result[channel] = round(current_val + (desired_val - current_val) * progress)

        return result

    def _rgb_to_ww_cw(self, rgb: tuple[float, float, float]) -> dict[ChannelType, float]:
        """Convert RGB to warm white / cold white values."""
        r, g, b = rgb
        brightness = (r + g + b) / 3

        if brightness > 0:
            temp = TemperatureConverter.rgb_to_kelvin(rgb, self.min_kelvin, self.max_kelvin)
            temp_ratio = (temp - self.min_kelvin) / (self.max_kelvin - self.min_kelvin)
            temp_ratio = max(0.0, min(1.0, temp_ratio))

            warm_ratio = 1 - temp_ratio
            cold_ratio = temp_ratio
            total_brightness = brightness * 255

            return {
                ChannelType.WARM_WHITE: round(total_brightness * warm_ratio),
                ChannelType.COLD_WHITE: round(total_brightness * cold_ratio),
            }

        return {ChannelType.WARM_WHITE: 0, ChannelType.COLD_WHITE: 0}

    def _rgb_to_color_temp(self, rgb: tuple[float, float, float]) -> dict[ChannelType, float]:
        """Convert RGB to color temperature + dimmer values."""
        r, g, b = rgb
        brightness = (r + g + b) / 3

        if brightness > 0:
            temp = TemperatureConverter.rgb_to_kelvin(rgb, self.min_kelvin, self.max_kelvin)
            temp_ratio = (temp - self.min_kelvin) / (self.max_kelvin - self.min_kelvin)
            temp_ratio = max(0.0, min(1.0, temp_ratio))

            return {ChannelType.COLOR_TEMPERATURE: round(temp_ratio * 255), ChannelType.DIMMER: round(brightness * 255)}

        return {ChannelType.COLOR_TEMPERATURE: 0, ChannelType.DIMMER: 0}


class LightTransitionAnimator:
    """
    Handles smooth transitions between different light states using direct channel interpolation
    when RGB channels remain constant, and L*u*v* color space interpolation for color changes.

    Supports various channel types including RGBW, CW/WW combinations, and color temperature controls.
    """

    def __init__(
        self,
        current_values: dict[ChannelType, float],
        desired_values: dict[ChannelType, float],
        min_kelvin: int | None = None,
        max_kelvin: int | None = None,
    ):
        """Initialize the transition animator."""
        self.min_kelvin = min_kelvin or 2700
        self.max_kelvin = max_kelvin or 6500

        # Apply epsilon handling for zero states
        self.current_values, self.desired_values = self._apply_epsilon_handling(
            current_values.copy(), desired_values.copy()
        )

        # Initialize converters
        self.channel_converter = ChannelConverter(self.min_kelvin, self.max_kelvin)

        # Convert both states to L*u*v* color space
        self.current_luv = self._channels_to_luv(self.current_values)
        self.desired_luv = self._channels_to_luv(self.desired_values)

    def _apply_epsilon_handling(
        self, current: dict[ChannelType, float], desired: dict[ChannelType, float]
    ) -> tuple[dict[ChannelType, float], dict[ChannelType, float]]:
        """Apply epsilon to prevent zero-state interpolation issues."""
        epsilon = 0.001

        def all_zero(d: dict[ChannelType, float]) -> bool:
            return all(v == 0 for v in d.values())

        # Only apply epsilon handling when one state is completely zero
        if all_zero(current) and not all_zero(desired):
            for k, v in desired.items():
                if v != 0:
                    current[k] = epsilon
        elif all_zero(desired) and not all_zero(current):
            for k, v in current.items():
                if v != 0:
                    desired[k] = epsilon

        return current, desired

    def _channels_to_luv(self, channels: dict[ChannelType, float]) -> tuple[float, float, float]:
        """Convert channel values to L*u*v* color space."""
        rgb = self.channel_converter.channels_to_rgb(channels)
        return ColorSpaceConverter.rgb_to_luv(rgb)

    def _is_pure_ww_cw_transition(self) -> bool:
        """Check if this is a pure WW/CW transition with no RGB channels."""
        original_channels = set(self.current_values.keys()) | set(self.desired_values.keys())
        return {ChannelType.WARM_WHITE, ChannelType.COLD_WHITE}.issubset(original_channels) and not any(
            ch in original_channels for ch in [ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE]
        )

    def _rgb_channels_unchanged(self) -> bool:
        """Check if RGB channels remain the same between current and desired states."""
        rgb_channels = [ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE]
        for channel in rgb_channels:
            if self.current_values.get(channel, 0) != self.desired_values.get(channel, 0):
                return False
        return True

    def interpolate(self, progress: float) -> dict[ChannelType, float]:
        """Calculate interpolated values at given progress (0.0 to 1.0)."""
        progress = max(0.0, min(1.0, progress))

        if self._is_pure_ww_cw_transition():
            return self._interpolate_ww_cw_direct(progress)
        elif self._rgb_channels_unchanged():
            # Use direct channel interpolation when RGB values don't change
            return self._interpolate_channels_direct(progress)
        else:
            # For mixed RGB + white channel transitions, interpolate separately
            return self._interpolate_mixed_channels(progress)

    def _interpolate_mixed_channels(self, progress: float) -> dict[ChannelType, float]:
        """Interpolate RGB and white channels separately to avoid color space corruption."""
        result = {}
        original_channels = set(self.current_values.keys()) | set(self.desired_values.keys())

        # Handle RGB channels with L*u*v* interpolation for better color transition
        rgb_channels = {ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE}
        has_rgb = any(ch in original_channels for ch in rgb_channels)

        if has_rgb:
            # Extract RGB-only values for color space interpolation
            current_rgb_channels = {ch: val for ch, val in self.current_values.items() if ch in rgb_channels}
            desired_rgb_channels = {ch: val for ch, val in self.desired_values.items() if ch in rgb_channels}

            # Convert to L*u*v* and interpolate
            current_rgb = self.channel_converter.channels_to_rgb(
                {**current_rgb_channels, ChannelType.WARM_WHITE: 0, ChannelType.COLD_WHITE: 0}
            )
            desired_rgb = self.channel_converter.channels_to_rgb(
                {**desired_rgb_channels, ChannelType.WARM_WHITE: 0, ChannelType.COLD_WHITE: 0}
            )

            current_luv = ColorSpaceConverter.rgb_to_luv(current_rgb)
            desired_luv = ColorSpaceConverter.rgb_to_luv(desired_rgb)

            interpolated_luv = tuple(
                current + (desired - current) * progress
                for current, desired in zip(current_luv, desired_luv, strict=False)
            )

            interpolated_rgb = ColorSpaceConverter.luv_to_rgb(interpolated_luv)

            # Convert back to RGB channel values
            result[ChannelType.RED] = round(interpolated_rgb[0] * 255)
            result[ChannelType.GREEN] = round(interpolated_rgb[1] * 255)
            result[ChannelType.BLUE] = round(interpolated_rgb[2] * 255)

        # Handle white channels with direct interpolation
        white_channels = {
            ChannelType.WARM_WHITE,
            ChannelType.COLD_WHITE,
            ChannelType.COLOR_TEMPERATURE,
            ChannelType.DIMMER,
        }
        for channel in white_channels:
            if channel in original_channels:
                current_val = self.current_values.get(channel, 0)
                desired_val = self.desired_values.get(channel, 0)
                result[channel] = round(current_val + (desired_val - current_val) * progress)

        # Handle any other channels with direct interpolation
        other_channels = original_channels - rgb_channels - white_channels
        for channel in other_channels:
            current_val = self.current_values.get(channel, 0)
            desired_val = self.desired_values.get(channel, 0)
            result[channel] = round(current_val + (desired_val - current_val) * progress)

        return result

    def _interpolate_channels_direct(self, progress: float) -> dict[ChannelType, float]:
        """Direct interpolation of channel values without color space conversion."""
        result = {}
        original_channels = set(self.current_values.keys()) | set(self.desired_values.keys())

        for channel in original_channels:
            current_val = self.current_values.get(channel, 0)
            desired_val = self.desired_values.get(channel, 0)
            result[channel] = round(current_val + (desired_val - current_val) * progress)

        return result

    def _interpolate_luv(self, progress: float) -> dict[ChannelType, float]:
        """Interpolate using L*u*v* color space."""
        # Linear interpolation in L*u*v* space
        interpolated_luv = tuple(
            current + (desired - current) * progress
            for current, desired in zip(self.current_luv, self.desired_luv, strict=False)
        )

        # Convert back to RGB then to channels
        interpolated_rgb = ColorSpaceConverter.luv_to_rgb(interpolated_luv)
        original_channels = set(self.current_values.keys()) | set(self.desired_values.keys())

        return self.channel_converter.rgb_to_channels(
            interpolated_rgb, original_channels, progress, self.current_values, self.desired_values
        )

    def _interpolate_ww_cw_direct(self, progress: float) -> dict[ChannelType, float]:
        """Direct interpolation for pure WW/CW transitions."""
        current_ww = self.current_values.get(ChannelType.WARM_WHITE, 0)
        current_cw = self.current_values.get(ChannelType.COLD_WHITE, 0)
        desired_ww = self.desired_values.get(ChannelType.WARM_WHITE, 0)
        desired_cw = self.desired_values.get(ChannelType.COLD_WHITE, 0)

        # Calculate brightness and temperature
        current_total = current_ww + current_cw
        desired_total = desired_ww + desired_cw

        def calculate_temp(ww: float, cw: float, total: float) -> float:
            if total > 0:
                return (ww * self.min_kelvin + cw * self.max_kelvin) / total
            return (self.min_kelvin + self.max_kelvin) / 2

        current_temp = calculate_temp(current_ww, current_cw, current_total)
        desired_temp = calculate_temp(desired_ww, desired_cw, desired_total)

        # Interpolate brightness and temperature
        interpolated_brightness = current_total + (desired_total - current_total) * progress
        interpolated_temp = current_temp + (desired_temp - current_temp) * progress

        # Convert back to WW/CW values
        if interpolated_brightness > 0:
            temp_ratio = (interpolated_temp - self.min_kelvin) / (self.max_kelvin - self.min_kelvin)
            temp_ratio = max(0.0, min(1.0, temp_ratio))

            warm_ratio = 1 - temp_ratio
            cold_ratio = temp_ratio

            return {
                ChannelType.WARM_WHITE: round(interpolated_brightness * warm_ratio),
                ChannelType.COLD_WHITE: round(interpolated_brightness * cold_ratio),
            }

        return {ChannelType.WARM_WHITE: 0, ChannelType.COLD_WHITE: 0}
