class ColorConverter:
    def __init__(self, min_kelvin: int = 2000, max_kelvin: int = 6500):
        self.min_kelvin = min_kelvin
        self.max_kelvin = max_kelvin

    def temp_to_cw_ww(self, temp_kelvin: int, brightness: int) -> tuple[int, int]:
        """
        Convert color temperature in kelvin and brightness to cold white and warm white values.

        For neutral white (middle temperature), both channels will be at full brightness.
        For pure warm/cold, only one channel will be active.

        Args:
            temp_kelvin: Color temperature in kelvin
            brightness: Overall brightness (0-255)

        Returns:
            Tuple of (cold_white, warm_white) values (0-255 each)
        """
        if brightness == 0:
            return 0, 0

        temp_kelvin = max(self.min_kelvin, min(self.max_kelvin, temp_kelvin))

        temp_ratio = 1.0 - (temp_kelvin - self.min_kelvin) / (self.max_kelvin - self.min_kelvin)

        if temp_ratio <= 0.5:
            cold_ratio = 1.0
            warm_ratio = temp_ratio * 2.0  # Scale 0-0.5 to 0-1
        else:
            warm_ratio = 1.0
            cold_ratio = (1.0 - temp_ratio) * 2.0  # Scale 0.5-1 to 1-0

        cold_white = round(cold_ratio * brightness)
        warm_white = round(warm_ratio * brightness)

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
            Tuple of (brightness, color_temp_kelvin)
        """
        if cold_white == 0 and warm_white == 0:
            return 0, self.min_kelvin

        brightness = max(cold_white, warm_white)
        temp_kelvin = self.cw_ww_to_temp(cold_white, warm_white)

        return brightness, temp_kelvin

    def dmx_to_kelvin(self, dmx_value: int) -> int:
        """Convert DMX value (0-255) to color temperature in kelvin."""
        ratio = dmx_value / 255.0
        return int(self.min_kelvin + (self.max_kelvin - self.min_kelvin) * ratio)

    def cw_ww_to_temp(self, cold_white: int, warm_white: int) -> int:
        """
        Convert cold white and warm white values to color temperature in kelvin.

        Args:
            cold_white: Cold white value (0-255)
            warm_white: Warm white value (0-255)

        Returns:
            Color temperature in kelvin
        """
        max_channel = max(cold_white, warm_white)
        if max_channel == 0:
            return self.min_kelvin

        cold_norm = cold_white / max_channel
        warm_norm = warm_white / max_channel

        if cold_norm == 1.0 and warm_norm < 1.0:
            temp_ratio = warm_norm * 0.5
        elif warm_norm == 1.0 and cold_norm < 1.0:
            temp_ratio = 0.5 + (1.0 - cold_norm) * 0.5
        elif cold_norm == 1.0 and warm_norm == 1.0:
            temp_ratio = 0.5
        else:
            # General case: more cold white = higher kelvin
            total = cold_white + warm_white
            temp_ratio = cold_white / total if total > 0 else 0.0

        temp_kelvin = self.max_kelvin - (self.max_kelvin - self.min_kelvin) * temp_ratio
        return int(temp_kelvin)

    def kelvin_to_dmx(self, kelvin: int) -> float:
        """Convert color temperature in kelvin to DMX value (0-255)."""
        ratio = (kelvin - self.min_kelvin) / (self.max_kelvin - self.min_kelvin)
        return ratio * 255
