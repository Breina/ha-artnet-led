import asyncio
import math
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import homeassistant.helpers.device_registry

from custom_components.dmx.correction import AVAILABLE_CURVES, OutputCorrection, parse_output_correction
from custom_components.dmx.entity.light.light_entity import DmxLightEntity
from custom_components.dmx.fixture import delegator, parser
from tests.dmx_test_framework import MockDmxUniverse, MockHomeAssistant, assert_dmx_range, get_entity_by_name

device_info_mock = MagicMock()
homeassistant.helpers.device_registry.DeviceInfo = device_info_mock


class TestOutputCorrectionMath(unittest.TestCase):
    """Unit tests for OutputCorrection.apply() and .invert() math."""

    def test_zero_always_returns_zero(self):
        corr = OutputCorrection(curve_name="linear", min_value=0.5, max_value=1.0)
        self.assertEqual(0.0, corr.apply(0.0))

    def test_linear_is_identity_without_min_max(self):
        corr = OutputCorrection(curve_name="linear")
        self.assertAlmostEqual(0.5, corr.apply(0.5))
        self.assertAlmostEqual(1.0, corr.apply(1.0))

    def test_quadratic_at_midpoint(self):
        corr = OutputCorrection(curve_name="quadratic")
        self.assertAlmostEqual(0.25, corr.apply(0.5), places=6)

    def test_cubic_at_midpoint(self):
        corr = OutputCorrection(curve_name="cubic")
        self.assertAlmostEqual(0.125, corr.apply(0.5), places=6)

    def test_sine_boundary_values(self):
        corr = OutputCorrection(curve_name="sine")
        self.assertAlmostEqual(0.0, corr.apply(0.0), places=6)
        self.assertAlmostEqual(1.0, corr.apply(1.0), places=5)

    def test_min_floor_shifts_output_up(self):
        corr = OutputCorrection(curve_name="linear", min_value=0.2, max_value=1.0)
        self.assertAlmostEqual(1.0, corr.apply(1.0), places=6)
        self.assertGreaterEqual(corr.apply(0.001), 0.2)

    def test_max_ceiling_caps_output(self):
        corr = OutputCorrection(curve_name="linear", min_value=0.0, max_value=0.9)
        self.assertAlmostEqual(0.9, corr.apply(1.0), places=6)
        self.assertAlmostEqual(0.45, corr.apply(0.5), places=6)

    def test_min_and_max_combined(self):
        corr = OutputCorrection(curve_name="linear", min_value=0.1, max_value=0.8)
        self.assertAlmostEqual(0.1, corr.apply(0.001), delta=0.01)
        self.assertAlmostEqual(0.8, corr.apply(1.0), places=6)
        self.assertAlmostEqual(0.45, corr.apply(0.5), places=6)

    # --- invert() ---

    def test_invert_zero_stays_zero(self):
        for name in AVAILABLE_CURVES:
            with self.subTest(curve=name):
                corr = OutputCorrection(curve_name=name)
                self.assertEqual(0.0, corr.invert(0.0))

    def test_invert_round_trip(self):
        """apply(invert(y)) ≈ y and invert(apply(t)) ≈ t for all curves."""
        for name in AVAILABLE_CURVES:
            for t in (0.1, 0.3, 0.5, 0.7, 0.9, 1.0):
                with self.subTest(curve=name, t=t):
                    corr = OutputCorrection(curve_name=name)
                    self.assertAlmostEqual(t, corr.invert(corr.apply(t)), places=5)
                    y = corr.apply(t)
                    self.assertAlmostEqual(y, corr.apply(corr.invert(y)), places=5)

    def test_invert_quadratic_at_quarter(self):
        corr = OutputCorrection(curve_name="quadratic")
        self.assertAlmostEqual(0.5, corr.invert(0.25), places=6)

    def test_invert_with_min_max_round_trip(self):
        corr = OutputCorrection(curve_name="quadratic", min_value=0.1, max_value=0.8)
        for t in (0.2, 0.5, 0.8, 1.0):
            with self.subTest(t=t):
                self.assertAlmostEqual(t, corr.invert(corr.apply(t)), places=5)

    def test_invert_below_floor_returns_nonzero(self):
        corr = OutputCorrection(curve_name="linear", min_value=0.2, max_value=1.0)
        # A non-zero value below min still returns a small positive (light is physically on)
        result = corr.invert(0.1)
        self.assertGreater(result, 0.0)


class TestParseOutputCorrection(unittest.TestCase):
    """Unit tests for parse_output_correction."""

    def test_none_returns_none(self):
        self.assertIsNone(parse_output_correction(None))

    def test_string_shorthand(self):
        corr = parse_output_correction("quadratic")
        self.assertIsNotNone(corr)
        self.assertAlmostEqual(0.25, corr.apply(0.5), places=6)

    def test_dict_with_curve_only(self):
        corr = parse_output_correction({"curve": "cubic"})
        self.assertAlmostEqual(0.125, corr.apply(0.5), places=6)

    def test_dict_with_all_fields(self):
        corr = parse_output_correction({"curve": "linear", "min": 0.1, "max": 0.9})
        self.assertAlmostEqual(0.9, corr.apply(1.0), places=6)
        self.assertGreaterEqual(corr.apply(0.001), 0.1)

    def test_dict_defaults_to_linear(self):
        corr = parse_output_correction({"min": 0.0, "max": 1.0})
        self.assertAlmostEqual(0.5, corr.apply(0.5), places=6)


class TestOutputCorrectionDmxOutput(unittest.TestCase):
    """Integration tests: correction applied through the full entity pipeline."""

    def setUp(self):
        self.hass = MockHomeAssistant()
        self.write_ha_state_patcher = patch("homeassistant.helpers.entity.Entity.async_write_ha_state")
        self.mock_write_ha_state = self.write_ha_state_patcher.start()
        self.schedule_update_patcher = patch("homeassistant.helpers.entity.Entity.async_schedule_update_ha_state")
        self.mock_schedule_update = self.schedule_update_patcher.start()

        fixture_path = Path(__file__).parent / "fixtures" / "rgbw-fader.json"
        self.fixture = parser.parse(str(fixture_path))
        self.universe = MockDmxUniverse()

    def tearDown(self):
        self.write_ha_state_patcher.stop()
        self.schedule_update_patcher.stop()

    def _make_light(self, output_correction=None) -> DmxLightEntity:
        channels = self.fixture.select_mode("8bit")
        entities = delegator.create_entities(
            "RGBW fader", 1, channels, None, self.universe, output_correction=output_correction
        )
        return get_entity_by_name(entities, "RGBW fader Light")

    def test_no_correction_is_linear(self):
        light = self._make_light()
        asyncio.run(light.async_turn_on(rgbw_color=(255, 0, 0, 0)))
        asyncio.run(light.async_turn_on(brightness=128))
        assert_dmx_range(self.universe, 1, [128, 0, 0, 0])

    def test_quadratic_correction_applied_to_dmx(self):
        correction = OutputCorrection(curve_name="quadratic")
        light = self._make_light(output_correction=correction)
        asyncio.run(light.async_turn_on(rgbw_color=(255, 0, 0, 0)))
        asyncio.run(light.async_turn_on(brightness=128))
        # DMX wire gets the corrected value
        expected_dmx = round((128 / 255) ** 2 * 255)
        self.assertAlmostEqual(expected_dmx, self.universe.get_channel_value(1), delta=1)

    def test_ha_state_not_clamped_by_correction(self):
        """HA brightness must remain the intended value; only the DMX wire is corrected."""
        correction = OutputCorrection(curve_name="quadratic")
        light = self._make_light(output_correction=correction)
        asyncio.run(light.async_turn_on(rgbw_color=(255, 0, 0, 0)))
        asyncio.run(light.async_turn_on(brightness=128))
        # HA state must reflect the intended value, not the corrected DMX value
        self.assertEqual(128, light.brightness)

    def test_external_dmx_inverse_corrected_in_ha_state(self):
        """When an external Art-Net controller sends a corrected DMX value, HA must
        show the inverse-corrected (intended) brightness."""
        correction = OutputCorrection(curve_name="quadratic")
        light = self._make_light(output_correction=correction)
        asyncio.run(light.async_turn_on(rgbw_color=(255, 0, 0, 0)))
        # Simulate external controller sending DMX=64 (≈ quadratic-corrected 50%)
        asyncio.run(self.universe.update_multiple_values({1: 64}, source="external"))
        expected_ha = round(math.sqrt(64 / 255) * 255)
        self.assertAlmostEqual(expected_ha, light.brightness, delta=2)

    def test_off_sends_zero_regardless_of_min(self):
        correction = OutputCorrection(curve_name="linear", min_value=0.5, max_value=1.0)
        light = self._make_light(output_correction=correction)
        asyncio.run(light.async_turn_on(rgbw_color=(255, 0, 0, 0)))
        asyncio.run(light.async_turn_off())
        assert_dmx_range(self.universe, 1, [0, 0, 0, 0])

    def test_min_floor_on_low_brightness(self):
        min_frac = 0.2
        correction = OutputCorrection(curve_name="linear", min_value=min_frac, max_value=1.0)
        light = self._make_light(output_correction=correction)
        asyncio.run(light.async_turn_on(rgbw_color=(255, 0, 0, 0), brightness=1))
        red_dmx = self.universe.get_channel_value(1)
        self.assertGreaterEqual(red_dmx, math.floor(min_frac * 255))

    def test_ha_state_at_full_brightness_with_max_ceiling(self):
        max_frac = 0.8
        correction = OutputCorrection(curve_name="linear", min_value=0.0, max_value=max_frac)
        light = self._make_light(output_correction=correction)
        asyncio.run(light.async_turn_on(rgbw_color=(255, 0, 0, 0), brightness=255))
        # DMX is capped at max_frac
        red_dmx = self.universe.get_channel_value(1)
        self.assertAlmostEqual(round(max_frac * 255), red_dmx, delta=1)
        # HA state still shows full brightness (255)
        self.assertEqual(255, light.brightness)

    def test_correction_not_applied_to_zero_channels(self):
        correction = OutputCorrection(curve_name="linear", min_value=0.5, max_value=1.0)
        light = self._make_light(output_correction=correction)
        asyncio.run(light.async_turn_on(rgbw_color=(255, 0, 0, 0), brightness=128))
        # Green, blue, white are 0 in HA state → must remain 0 in DMX (not lifted to min)
        self.assertEqual(0, self.universe.get_channel_value(2))  # green
        self.assertEqual(0, self.universe.get_channel_value(3))  # blue
        self.assertEqual(0, self.universe.get_channel_value(4))  # white


class TestColorTemperatureNotCorrected(unittest.TestCase):
    """Correction must NOT be set on colour-temperature channel mappings (Kelvin, not intensity)."""

    def setUp(self):
        self.hass = MockHomeAssistant()
        self.write_ha_state_patcher = patch("homeassistant.helpers.entity.Entity.async_write_ha_state")
        self.mock_write_ha_state = self.write_ha_state_patcher.start()
        self.schedule_update_patcher = patch("homeassistant.helpers.entity.Entity.async_schedule_update_ha_state")
        self.mock_schedule_update = self.schedule_update_patcher.start()

        fixture_path = Path(__file__).parent / "fixtures" / "color-temperature-fader.json"
        self.fixture = parser.parse(str(fixture_path))
        self.universe = MockDmxUniverse()

    def tearDown(self):
        self.write_ha_state_patcher.stop()
        self.schedule_update_patcher.stop()

    def test_color_temp_channel_has_no_correction_on_mapping(self):
        from custom_components.dmx.entity.light import ChannelType
        from custom_components.dmx.entity.light.light_entity import DmxLightEntity

        correction = OutputCorrection(curve_name="quadratic")
        channels = self.fixture.select_mode(next(iter(self.fixture.modes)))
        entities = delegator.create_entities(
            "CT fixture", 1, channels, None, self.universe, output_correction=correction
        )

        light: DmxLightEntity = get_entity_by_name(entities, "CT fixture Light")

        # The COLOR_TEMPERATURE channel mapping must carry no correction
        ct_mapping = light._state.channels.get(ChannelType.COLOR_TEMPERATURE)
        self.assertIsNotNone(ct_mapping, "Expected a COLOR_TEMPERATURE channel mapping")
        self.assertIsNone(ct_mapping.output_correction)

        # Intensity channels (e.g. DIMMER, WW, CW) must carry the correction
        intensity_types = {ChannelType.DIMMER, ChannelType.WARM_WHITE, ChannelType.COLD_WHITE}
        for ct in intensity_types:
            if ct in light._state.channels:
                self.assertIsNotNone(
                    light._state.channels[ct].output_correction,
                    f"Expected correction on {ct}",
                )
