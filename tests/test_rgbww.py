import asyncio
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import homeassistant.helpers.device_registry

from custom_components.dmx.entity.light.light_entity import DmxLightEntity
from custom_components.dmx.entity.number import DmxNumberEntity
from custom_components.dmx.fixture import delegator, parser
from tests.dmx_test_framework import MockDmxUniverse, MockHomeAssistant, assert_dmx_range, get_entity_by_name

device_info_mock = MagicMock()
homeassistant.helpers.device_registry.DeviceInfo = device_info_mock


class TestRgbwwFixture(unittest.TestCase):

    def setUp(self):
        self.hass = MockHomeAssistant()
        self.write_ha_state_patcher = patch("homeassistant.helpers.entity.Entity.async_write_ha_state")
        self.mock_write_ha_state = self.write_ha_state_patcher.start()

        self.schedule_update_patcher = patch("homeassistant.helpers.entity.Entity.async_schedule_update_ha_state")
        self.mock_schedule_update = self.schedule_update_patcher.start()

        fixture_path = Path(__file__).parent / "fixtures" / "rgbww-fader.json"
        self.fixture = parser.parse(str(fixture_path))
        self.universe = MockDmxUniverse()

    def tearDown(self):
        self.write_ha_state_patcher.stop()
        self.schedule_update_patcher.stop()

    def test_8bit_rgbww_number_updates(self):
        channels = self.fixture.select_mode("8bit")
        entities = delegator.create_entities("RGBWW fader", 1, channels, None, self.universe)

        red: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Red")
        green: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Green")
        blue: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Blue")
        warm_white: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Warm White")
        cold_white: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Cold White")
        light: DmxLightEntity = get_entity_by_name(entities, "RGBWW fader Light")

        # Test pure red
        asyncio.run(red.async_set_native_value(100))
        asyncio.run(green.async_set_native_value(0))
        asyncio.run(blue.async_set_native_value(0))
        asyncio.run(warm_white.async_set_native_value(0))
        asyncio.run(cold_white.async_set_native_value(0))
        assert_dmx_range(self.universe, 1, [255, 0, 0, 0, 0])
        self.assertEqual(255, light.brightness)
        self.assertEqual((255, 0, 0), light.rgb_color)

        # Test pure warm white
        asyncio.run(red.async_set_native_value(0))
        asyncio.run(green.async_set_native_value(0))
        asyncio.run(blue.async_set_native_value(0))
        asyncio.run(warm_white.async_set_native_value(100))
        asyncio.run(cold_white.async_set_native_value(0))
        assert_dmx_range(self.universe, 1, [0, 0, 0, 255, 0])
        self.assertEqual(255, light.brightness)

        # Test pure cold white
        asyncio.run(red.async_set_native_value(0))
        asyncio.run(green.async_set_native_value(0))
        asyncio.run(blue.async_set_native_value(0))
        asyncio.run(warm_white.async_set_native_value(0))
        asyncio.run(cold_white.async_set_native_value(100))
        assert_dmx_range(self.universe, 1, [0, 0, 0, 0, 255])
        self.assertEqual(255, light.brightness)

        # Test mixed RGB color
        asyncio.run(red.async_set_native_value(50))
        asyncio.run(green.async_set_native_value(75))
        asyncio.run(blue.async_set_native_value(25))
        asyncio.run(warm_white.async_set_native_value(0))
        asyncio.run(cold_white.async_set_native_value(0))
        assert_dmx_range(self.universe, 1, [127, 191, 64, 0, 0])
        self.assertEqual(191, light.brightness)
        self.assertEqual((127, 191, 64), light.rgb_color)

        # Test mixed white channels (neutral white)
        asyncio.run(red.async_set_native_value(0))
        asyncio.run(green.async_set_native_value(0))
        asyncio.run(blue.async_set_native_value(0))
        asyncio.run(warm_white.async_set_native_value(50))
        asyncio.run(cold_white.async_set_native_value(50))
        assert_dmx_range(self.universe, 1, [0, 0, 0, 127, 127])
        self.assertEqual(127, light.brightness)

        # Test RGBWW combination
        asyncio.run(red.async_set_native_value(40))
        asyncio.run(green.async_set_native_value(40))
        asyncio.run(blue.async_set_native_value(40))
        asyncio.run(warm_white.async_set_native_value(30))
        asyncio.run(cold_white.async_set_native_value(30))
        assert_dmx_range(self.universe, 1, [102, 102, 102, 76, 76])
        self.assertEqual(102, light.brightness)

    def test_8bit_rgbww_light_updates(self):
        channels = self.fixture.select_mode("8bit")
        entities = delegator.create_entities("RGBWW fader", 2, channels, None, self.universe)

        red: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Red")
        green: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Green")
        blue: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Blue")
        warm_white: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Warm White")
        cold_white: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Cold White")
        light: DmxLightEntity = get_entity_by_name(entities, "RGBWW fader Light")

        # Test setting pure red
        asyncio.run(light.async_turn_on(rgbww_color=(255, 0, 0, 0, 0)))
        assert_dmx_range(self.universe, 2, [255, 0, 0, 0, 0])
        self.assertEqual(100, red.native_value)
        self.assertEqual(0, green.native_value)
        self.assertEqual(0, blue.native_value)
        self.assertEqual(0, warm_white.native_value)
        self.assertEqual(0, cold_white.native_value)

        # Test setting mixed RGB color
        asyncio.run(light.async_turn_on(rgbww_color=(127, 191, 63, 0, 0)))
        assert_dmx_range(self.universe, 2, [127, 191, 63, 0, 0])
        self.assertAlmostEqual(50.0, red.native_value, 0)
        self.assertAlmostEqual(75.0, green.native_value, 0)
        self.assertAlmostEqual(25.0, blue.native_value, 0)
        self.assertEqual(0, warm_white.native_value)
        self.assertEqual(0, cold_white.native_value)

        # Test setting warm white
        asyncio.run(light.async_turn_on(rgbww_color=(0, 0, 0, 0, 255)))
        assert_dmx_range(self.universe, 2, [0, 0, 0, 255, 0])  # = [127, 191, 63, 255, 0]
        self.assertEqual(0, red.native_value)
        self.assertEqual(0, green.native_value)
        self.assertEqual(0, blue.native_value)
        self.assertEqual(100, warm_white.native_value)
        self.assertEqual(0, cold_white.native_value)

        # Test setting cold white
        asyncio.run(light.async_turn_on(rgbww_color=(0, 0, 0, 255, 0)))
        assert_dmx_range(self.universe, 2, [0, 0, 0, 0, 255])
        self.assertEqual(0, red.native_value)
        self.assertEqual(0, green.native_value)
        self.assertEqual(0, blue.native_value)
        self.assertEqual(0, warm_white.native_value)
        self.assertEqual(100, cold_white.native_value)

        # Test setting neutral white (mixed warm/cold)
        asyncio.run(light.async_turn_on(rgbww_color=(0, 0, 0, 127, 127)))
        assert_dmx_range(self.universe, 2, [0, 0, 0, 127, 127])
        self.assertEqual(0, red.native_value)
        self.assertEqual(0, green.native_value)
        self.assertEqual(0, blue.native_value)
        self.assertAlmostEqual(50.0, warm_white.native_value, 0)
        self.assertAlmostEqual(50.0, cold_white.native_value, 0)

    def test_turn_on_restore_last_value(self):
        channels = self.fixture.select_mode("8bit")
        entities = delegator.create_entities("RGBWW fader", 1, channels, None, self.universe)

        red: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Red")
        green: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Green")
        blue: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Blue")
        warm_white: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Warm White")
        cold_white: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Cold White")
        light: DmxLightEntity = get_entity_by_name(entities, "RGBWW fader Light")

        # Set initial values
        asyncio.run(red.async_set_native_value(75))
        asyncio.run(green.async_set_native_value(50))
        asyncio.run(blue.async_set_native_value(25))
        asyncio.run(warm_white.async_set_native_value(60))
        asyncio.run(cold_white.async_set_native_value(40))
        self.assertTrue(light.is_on)

        # Turn off
        asyncio.run(light.async_turn_off())
        self.assertFalse(light.is_on)
        self.assertEqual(0, red.native_value)
        self.assertEqual(0, green.native_value)
        self.assertEqual(0, blue.native_value)
        self.assertEqual(0, warm_white.native_value)
        self.assertEqual(0, cold_white.native_value)

        # Turn on - should restore last values
        asyncio.run(light.async_turn_on())
        self.assertTrue(light.is_on)
        self.assertAlmostEqual(75.0, red.native_value, None, "", 1)
        self.assertAlmostEqual(50.0, green.native_value, None, "", 1)
        self.assertAlmostEqual(25.0, blue.native_value, None, "", 1)
        self.assertAlmostEqual(60.0, warm_white.native_value, None, "", 1)
        self.assertAlmostEqual(40.0, cold_white.native_value, None, "", 1)

        # Turn off all RGB, should still be on due to white channels
        asyncio.run(red.async_set_native_value(0))
        asyncio.run(green.async_set_native_value(0))
        asyncio.run(blue.async_set_native_value(0))
        self.assertTrue(light.is_on)

        # Turn off warm white, should still be on due to cold white
        asyncio.run(warm_white.async_set_native_value(0))
        self.assertTrue(light.is_on)

        # Turn off cold white, now should be off
        asyncio.run(cold_white.async_set_native_value(0))
        self.assertFalse(light.is_on)

        # Turn on again - should restore last non-zero values
        asyncio.run(light.async_turn_on())
        self.assertTrue(light.is_on)
        self.assertEqual(0, red.native_value)
        self.assertEqual(0, green.native_value)
        self.assertEqual(0, blue.native_value)
        self.assertEqual(0, warm_white.native_value)
        self.assertAlmostEqual(40.0, cold_white.native_value, 0)

    def test_rgbww_color_effects(self):
        channels = self.fixture.select_mode("8bit")
        entities = delegator.create_entities("RGBWW fader", 5, channels, None, self.universe)

        red: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Red")
        green: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Green")
        blue: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Blue")
        warm_white: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Warm White")
        cold_white: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Cold White")
        light: DmxLightEntity = get_entity_by_name(entities, "RGBWW fader Light")

        # Test various RGB colors
        colors_to_test = [
            (255, 0, 0),  # Red
            (0, 255, 0),  # Green
            (0, 0, 255),  # Blue
            (255, 255, 0),  # Yellow
            (255, 0, 255),  # Magenta
            (0, 255, 255),  # Cyan
            (255, 128, 64),  # Orange
        ]

        for rgb in colors_to_test:
            asyncio.run(light.async_turn_on(rgbww_color=(rgb[0], rgb[1], rgb[2], 0, 0)))
            self.assertEqual(rgb, light.rgb_color)
            self.assertTrue(light.is_on)

        asyncio.run(warm_white.async_set_native_value(80))
        asyncio.run(cold_white.async_set_native_value(0))
        asyncio.run(red.async_set_native_value(0))
        asyncio.run(green.async_set_native_value(0))
        asyncio.run(blue.async_set_native_value(0))
        assert_dmx_range(self.universe, 5, [0, 0, 0, 204, 0])
        self.assertTrue(light.is_on)

        asyncio.run(warm_white.async_set_native_value(0))
        asyncio.run(cold_white.async_set_native_value(60))
        assert_dmx_range(self.universe, 5, [0, 0, 0, 0, 153])
        self.assertTrue(light.is_on)

    def test_rgbww_mixed_scenarios(self):
        channels = self.fixture.select_mode("8bit")
        entities = delegator.create_entities("RGBWW fader", 6, channels, None, self.universe)

        red: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Red")
        green: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Green")
        blue: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Blue")
        warm_white: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Warm White")
        cold_white: DmxNumberEntity = get_entity_by_name(entities, "RGBWW fader Cold White")
        light: DmxLightEntity = get_entity_by_name(entities, "RGBWW fader Light")

        # Test RGB + warm white combination
        asyncio.run(red.async_set_native_value(50))
        asyncio.run(green.async_set_native_value(30))
        asyncio.run(blue.async_set_native_value(20))
        asyncio.run(warm_white.async_set_native_value(40))
        asyncio.run(cold_white.async_set_native_value(0))
        assert_dmx_range(self.universe, 6, [127, 76, 51, 102, 0])
        self.assertTrue(light.is_on)

        # Test RGB + cold white combination
        asyncio.run(red.async_set_native_value(30))
        asyncio.run(green.async_set_native_value(50))
        asyncio.run(blue.async_set_native_value(70))
        asyncio.run(warm_white.async_set_native_value(0))
        asyncio.run(cold_white.async_set_native_value(35))
        assert_dmx_range(self.universe, 6, [76, 127, 178, 0, 89])
        self.assertTrue(light.is_on)

        # Test all channels at moderate levels
        asyncio.run(red.async_set_native_value(25))
        asyncio.run(green.async_set_native_value(25))
        asyncio.run(blue.async_set_native_value(25))
        asyncio.run(warm_white.async_set_native_value(25))
        asyncio.run(cold_white.async_set_native_value(25))
        assert_dmx_range(self.universe, 6, [64, 64, 64, 64, 64])
        self.assertTrue(light.is_on)
        self.assertEqual(64, light.brightness)


if __name__ == "__main__":
    unittest.main()
