class ColorConverter:
    def __init__(self, min_kelvin: int = 2000, max_kelvin: int = 6500):
        self.min_kelvin = min_kelvin
        self.max_kelvin = max_kelvin
        self.min_mired = 1000000 // max_kelvin  # ~154 mired for 6500K
        self.max_mired = 1000000 // min_kelvin  # 500 mired for 2000K

    def temp_to_cw_ww(self, temp_mired: int, brightness: int) -> tuple[int, int]:
        """
        Convert color temperature in mireds and brightness to cold white and warm white values.

        For neutral white (middle temperature), both channels will be at full brightness.
        For pure warm/cold, only one channel will be active.

        Args:
            temp_mired: Color temperature in mireds
            brightness: Overall brightness (0-255)

        Returns:
            Tuple of (cold_white, warm_white) values (0-255 each)
        """
        if brightness == 0:
            return 0, 0

        temp_mired = max(self.min_mired, min(self.max_mired, temp_mired))

        temp_ratio = (temp_mired - self.min_mired) / (self.max_mired - self.min_mired)

        if temp_ratio <= 0.5:
            cold_ratio = 1.0
            warm_ratio = temp_ratio * 2.0  # Scale 0-0.5 to 0-1
        else:
            warm_ratio = 1.0
            cold_ratio = (1.0 - temp_ratio) * 2.0  # Scale 0.5-1 to 1-0

        cold_white = round(cold_ratio * brightness)
        warm_white = round(warm_ratio * brightness)

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

        brightness = max(cold_white, warm_white)

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

        max_channel = max(cold_white, warm_white)
        if max_channel == 0:
            return self.min_mired

        cold_norm = cold_white / max_channel
        warm_norm = warm_white / max_channel

        if cold_norm == 1.0 and warm_norm < 1.0:
            temp_ratio = warm_norm * 0.5
        elif warm_norm == 1.0 and cold_norm < 1.0:
            temp_ratio = 0.5 + (1.0 - cold_norm) * 0.5
        elif cold_norm == 1.0 and warm_norm == 1.0:
            temp_ratio = 0.5
        else:
            total = cold_white + warm_white
            temp_ratio = warm_white / total if total > 0 else 0.0

        temp_mired = self.min_mired + (self.max_mired - self.min_mired) * temp_ratio
        return int(temp_mired)

    def mired_to_dmx(self, mireds: int) -> int:
        """Convert color temperature in mireds to DMX value (0-255)."""
        ratio = (mireds - self.min_mired) / (self.max_mired - self.min_mired)
        return int(ratio * 255)