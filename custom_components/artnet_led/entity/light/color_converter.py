class ColorConverter:
    def __init__(self, min_kelvin: int = 2000, max_kelvin: int = 6500):
        self.min_kelvin = min_kelvin
        self.max_kelvin = max_kelvin
        self.min_mired = 1000000 // max_kelvin  # ~154 mired for 6500K
        self.max_mired = 1000000 // min_kelvin  # 500 mired for 2000K

    def temp_to_cw_ww(self, temp_mired: int, brightness: int) -> tuple[int, int]:
        """
        Convert color temperature in mireds and brightness to cold white and warm white values.

        Args:
            temp_mired: Color temperature in mireds
            brightness: Overall brightness (0-255)

        Returns:
            Tuple of (cold_white, warm_white) values (0-255 each)
        """

        temp_mired = max(self.min_mired, min(self.max_mired, temp_mired))

        temp_ratio = (temp_mired - self.min_mired) / (self.max_mired - self.min_mired)

        cold_ratio = 1.0 - temp_ratio
        warm_ratio = temp_ratio

        # Use rounding instead of truncation to minimize precision loss
        cold_white = round(cold_ratio * brightness)
        warm_white = round(warm_ratio * brightness)

        # Ensure the sum equals the original brightness to avoid rounding errors
        total = cold_white + warm_white
        if total != brightness and brightness > 0:
            # Adjust the larger value to compensate for rounding errors
            if cold_white >= warm_white:
                cold_white += brightness - total
            else:
                warm_white += brightness - total

        # Ensure values stay within valid range
        cold_white = max(0, min(255, cold_white))
        warm_white = max(0, min(255, warm_white))

        return cold_white, warm_white

    def cw_ww_to_brightness_temp(self, cold_white: int, warm_white: int) -> tuple[int, int]:
        """
        Convert cold white and warm white values to brightness and color temperature.

        Args:
            cold_white: Cold white value (0-255)
            warm_white: Warm white value (0-255)

        Returns:
            Tuple of (brightness, color_temp_mired)
        """
        if cold_white == 0 and warm_white == 0:
            return 0, self.min_mired

        # Calculate brightness as the sum of the two channels
        # This is the inverse of how temp_to_cw_ww distributes brightness
        brightness = cold_white + warm_white

        # Calculate color temperature from the ratio
        temp_mired = self.cw_ww_to_temp(cold_white, warm_white)

        return brightness, temp_mired

    def dmx_to_mired(self, dmx_value: int) -> int:
        """Convert DMX value (0-255) to color temperature in mireds."""
        ratio = dmx_value / 255.0
        return int(self.min_mired + (self.max_mired - self.min_mired) * ratio)

    def cw_ww_to_temp(self, cold_white: int, warm_white: int) -> int:
        """
        Convert cold white and warm white values to color temperature in mireds.

        Args:
            cold_white: Cold white value (0-255)
            warm_white: Warm white value (0-255)

        Returns:
            Color temperature in mireds
        """
        if cold_white == 0 and warm_white == 0:
            return self.min_mired

        total = cold_white + warm_white
        if total == 0:
            return self.min_mired

        warm_ratio = warm_white / total

        temp_mired = self.min_mired + (self.max_mired - self.min_mired) * warm_ratio
        return int(temp_mired)

    def mired_to_dmx(self, mireds: int) -> int:
        """Convert color temperature in mireds to DMX value (0-255)."""
        ratio = (mireds - self.min_mired) / (self.max_mired - self.min_mired)
        return int(ratio * 255)