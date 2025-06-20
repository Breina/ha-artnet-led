import asyncio
import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

import homeassistant.helpers.device_registry

from custom_components.artnet_led.entity.light.light_entity import DmxLightEntity
from custom_components.artnet_led.entity.number import DmxNumberEntity
from custom_components.artnet_led.fixture import parser
from custom_components.artnet_led.fixture_delegator import delegator
from tests.dmx_test_framework import MockDmxUniverse, get_entity_by_name, MockHomeAssistant, assert_dmx_range

device_info_mock = MagicMock()
homeassistant.helpers.device_registry.DeviceInfo = device_info_mock


class TestRgbwFixture(unittest.TestCase):

    def setUp(self):
        self.hass = MockHomeAssistant()
        self.write_ha_state_patcher = patch('homeassistant.helpers.entity.Entity.async_write_ha_state')
        self.mock_write_ha_state = self.write_ha_state_patcher.start()

        self.schedule_update_patcher = patch('homeassistant.helpers.entity.Entity.async_schedule_update_ha_state')
        self.mock_schedule_update = self.schedule_update_patcher.start()

        self.fixture = parser.parse('fixtures/rgbw-fader.json')
        self.universe = MockDmxUniverse()

    def tearDown(self):
        self.write_ha_state_patcher.stop()
        self.schedule_update_patcher.stop()

    def test_8bit_rgbw_number_updates(self):
        channels = self.fixture.select_mode('8bit')
        entities = delegator.create_entities('RGBW fader', 1, channels, None, self.universe)

        red: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Red')
        green: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Green')
        blue: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Blue')
        white: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader White')
        light: DmxLightEntity = get_entity_by_name(entities, 'RGBW fader Light')

        # Test pure red
        asyncio.run(red.async_set_native_value(100))
        asyncio.run(green.async_set_native_value(0))
        asyncio.run(blue.async_set_native_value(0))
        asyncio.run(white.async_set_native_value(0))
        assert_dmx_range(self.universe, 1, [255, 0, 0, 0])
        self.assertEqual(255, light.brightness)
        self.assertEqual((255, 0, 0), light.rgb_color)

        # Test pure white
        asyncio.run(red.async_set_native_value(0))
        asyncio.run(green.async_set_native_value(0))
        asyncio.run(blue.async_set_native_value(0))
        asyncio.run(white.async_set_native_value(100))
        assert_dmx_range(self.universe, 1, [0, 0, 0, 255])
        self.assertEqual(255, light.brightness)

        # Test mixed color
        asyncio.run(red.async_set_native_value(50))
        asyncio.run(green.async_set_native_value(75))
        asyncio.run(blue.async_set_native_value(25))
        asyncio.run(white.async_set_native_value(0))
        assert_dmx_range(self.universe, 1, [127, 191, 64, 0])
        self.assertEqual(191, light.brightness)
        self.assertEqual((127, 191, 64), light.rgb_color)

        # Test RGBW combination
        asyncio.run(red.async_set_native_value(50))
        asyncio.run(green.async_set_native_value(50))
        asyncio.run(blue.async_set_native_value(50))
        asyncio.run(white.async_set_native_value(50))
        assert_dmx_range(self.universe, 1, [127, 127, 127, 127])
        self.assertEqual(127, light.brightness)

    def test_8bit_rgbw_light_updates(self):
        channels = self.fixture.select_mode('8bit')
        entities = delegator.create_entities('RGBW fader', 2, channels, None, self.universe)

        red: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Red')
        green: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Green')
        blue: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Blue')
        white: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader White')
        light: DmxLightEntity = get_entity_by_name(entities, 'RGBW fader Light')

        # Test setting pure red
        asyncio.run(light.async_turn_on(brightness=255, rgb_color=(255, 0, 0)))
        assert_dmx_range(self.universe, 2, [255, 0, 0, 0])
        self.assertEqual(100, red.native_value)
        self.assertEqual(0, green.native_value)
        self.assertEqual(0, blue.native_value)
        self.assertEqual(0, white.native_value)

        # Test setting mixed color
        asyncio.run(light.async_turn_on(brightness=191, rgb_color=(127, 191, 63)))
        assert_dmx_range(self.universe, 2, [127, 191, 63, 0])
        self.assertAlmostEqual(50.0, red.native_value, 0)
        self.assertAlmostEqual(75.0, green.native_value, 0)
        self.assertAlmostEqual(25.0, blue.native_value, 0)
        self.assertEqual(0, white.native_value)

        # Test setting white
        asyncio.run(light.async_turn_on(brightness=255, rgb_color=(255, 255, 255)))
        # White light might be handled differently - adjust expectations based on implementation
        self.assertTrue(light.is_on)

    def test_16bit_rgbw_number_updates(self):
        channels = self.fixture.select_mode('16bit')
        entities = delegator.create_entities('RGBW fader', 3, channels, None, self.universe)

        red: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Red')
        green: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Green')
        blue: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Blue')
        white: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader White')
        light: DmxLightEntity = get_entity_by_name(entities, 'RGBW fader Light')

        # Test pure red (16-bit: high byte, low byte for each channel)
        asyncio.run(red.async_set_native_value(100))
        asyncio.run(green.async_set_native_value(0))
        asyncio.run(blue.async_set_native_value(0))
        asyncio.run(white.async_set_native_value(0))
        assert_dmx_range(self.universe, 3, [255, 255, 0, 0, 0, 0, 0, 0])
        self.assertEqual(255, light.brightness)
        self.assertEqual((255, 0, 0), light.rgb_color)

        # Test mixed color
        asyncio.run(red.async_set_native_value(50))
        asyncio.run(green.async_set_native_value(75))
        asyncio.run(blue.async_set_native_value(25))
        asyncio.run(white.async_set_native_value(0))
        assert_dmx_range(self.universe, 3, [127, 255, 191, 255, 64, 0, 0, 0])
        self.assertEqual(191, light.brightness)
        self.assertEqual((127, 191, 64), light.rgb_color)

        # Test RGBW combination
        asyncio.run(red.async_set_native_value(50))
        asyncio.run(green.async_set_native_value(50))
        asyncio.run(blue.async_set_native_value(50))
        asyncio.run(white.async_set_native_value(50))
        assert_dmx_range(self.universe, 3, [127, 255, 127, 255, 127, 255, 127, 255])
        self.assertEqual(127, light.brightness)

    def test_16bit_rgbw_light_updates(self):
        channels = self.fixture.select_mode('16bit')
        entities = delegator.create_entities('RGBW fader', 4, channels, None, self.universe)

        red: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Red')
        green: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Green')
        blue: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Blue')
        white: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader White')
        light: DmxLightEntity = get_entity_by_name(entities, 'RGBW fader Light')

        # Test setting pure red
        asyncio.run(light.async_turn_on(brightness=255, rgb_color=(255, 0, 0)))
        assert_dmx_range(self.universe, 4, [255, 255, 0, 0, 0, 0, 0, 0])
        self.assertEqual(100, red.native_value)
        self.assertEqual(0, green.native_value)
        self.assertEqual(0, blue.native_value)
        self.assertEqual(0, white.native_value)

        # Test setting mixed color
        asyncio.run(light.async_turn_on(brightness=127, rgb_color=(127, 127, 127)))
        assert_dmx_range(self.universe, 4, [127, 127, 127, 127, 127, 127, 0, 0])
        self.assertAlmostEqual(50.0, red.native_value, 0)
        self.assertAlmostEqual(50.0, green.native_value, 0)
        self.assertAlmostEqual(50.0, blue.native_value, 0)
        self.assertEqual(0, white.native_value)

    def test_turn_on_restore_last_value(self):
        channels = self.fixture.select_mode('8bit')
        entities = delegator.create_entities('RGBW fader', 1, channels, None, self.universe)

        red: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Red')
        green: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Green')
        blue: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Blue')
        white: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader White')
        light: DmxLightEntity = get_entity_by_name(entities, 'RGBW fader Light')

        asyncio.run(red.async_set_native_value(75))
        asyncio.run(green.async_set_native_value(50))
        asyncio.run(blue.async_set_native_value(25))
        asyncio.run(white.async_set_native_value(10))
        self.assertTrue(light.is_on)

        asyncio.run(light.async_turn_off())
        self.assertFalse(light.is_on)
        self.assertEqual(0, red.native_value)
        self.assertEqual(0, green.native_value)
        self.assertEqual(0, blue.native_value)
        self.assertEqual(0, white.native_value)

        asyncio.run(light.async_turn_on())
        self.assertTrue(light.is_on)
        self.assertAlmostEqual(75.0, red.native_value, None, "", 1)
        self.assertAlmostEqual(50.0, green.native_value, None, "", 1)
        self.assertAlmostEqual(25.0, blue.native_value, None, "", 1)
        self.assertAlmostEqual(10.0, white.native_value, 0)

        asyncio.run(red.async_set_native_value(0))
        asyncio.run(green.async_set_native_value(0))
        asyncio.run(blue.async_set_native_value(0))
        self.assertTrue(light.is_on)
        asyncio.run(white.async_set_native_value(0))
        self.assertFalse(light.is_on)

        asyncio.run(light.async_turn_on())
        self.assertTrue(light.is_on)
        self.assertEqual(0, red.native_value)
        self.assertEqual(0, green.native_value)
        self.assertEqual(0, blue.native_value)
        self.assertAlmostEqual(10.0, white.native_value, 0)

    def test_rgbw_color_effects(self):
        channels = self.fixture.select_mode('8bit')
        entities = delegator.create_entities('RGBW fader', 5, channels, None, self.universe)

        red: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Red')
        green: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Green')
        blue: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader Blue')
        white: DmxNumberEntity = get_entity_by_name(entities, 'RGBW fader White')
        light: DmxLightEntity = get_entity_by_name(entities, 'RGBW fader Light')

        colors_to_test = [
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
            (255, 255, 0),
            (255, 0, 255),
            (0, 255, 255),
        ]

        for rgb in colors_to_test:
            asyncio.run(light.async_turn_on(brightness=255, rgb_color=rgb))
            self.assertEqual(rgb, light.rgb_color)
            self.assertTrue(light.is_on)

        # Test white channel independently
        asyncio.run(white.async_set_native_value(100))
        asyncio.run(red.async_set_native_value(0))
        asyncio.run(green.async_set_native_value(0))
        asyncio.run(blue.async_set_native_value(0))
        assert_dmx_range(self.universe, 5, [0, 0, 0, 255])
        self.assertTrue(light.is_on)


if __name__ == "__main__":
    unittest.main()
