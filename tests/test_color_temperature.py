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


class TestColorTemperatureFader(unittest.TestCase):

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

    def test_color_temperature_metadata(self):
        channels = self.fixture.select_mode("8bit")
        entities = delegator.create_entities("Color Temp fader", 1, channels, None, self.universe)

        color_temp: DmxNumberEntity = get_entity_by_name(entities, "Color Temp fader Color Temperature")
        light: DmxLightEntity = get_entity_by_name(entities, "Color Temp fader Light")

        self.assertEqual(color_temp.min_value, 6500)
        self.assertEqual(color_temp.max_value, 8500)
        self.assertEqual(light.min_color_temp_kelvin, 6500)
        self.assertEqual(light.max_color_temp_kelvin, 8500)

    def test_8bit_dimmer_color_temp_number_updates(self):
        channels = self.fixture.select_mode("8bit")
        entities = delegator.create_entities("Color Temp fader", 1, channels, None, self.universe)

        dimmer: DmxNumberEntity = get_entity_by_name(entities, "Color Temp fader Intensity")
        color_temp: DmxNumberEntity = get_entity_by_name(entities, "Color Temp fader Color Temperature")
        light: DmxLightEntity = get_entity_by_name(entities, "Color Temp fader Light")

        asyncio.run(dimmer.async_set_native_value(100))
        asyncio.run(color_temp.async_set_native_value(color_temp.max_value))
        assert_dmx_range(self.universe, 1, [255, 255])
        self.assertEqual(255, light.brightness)
        self.assertEqual(light.max_color_temp_kelvin, light.color_temp_kelvin)

        asyncio.run(dimmer.async_set_native_value(50))
        asyncio.run(color_temp.async_set_native_value((color_temp.max_value + color_temp.min_value) / 2))
        assert_dmx_range(self.universe, 1, [127, 128])
        self.assertEqual(light.brightness, 127)
        self.assertAlmostEqual(
            (light.min_color_temp_kelvin + light.max_color_temp_kelvin) / 2, light.color_temp_kelvin, None, "", 5
        )

        asyncio.run(dimmer.async_set_native_value(100))
        asyncio.run(color_temp.async_set_native_value(color_temp.min_value))
        assert_dmx_range(self.universe, 1, [255, 0])
        self.assertEqual(light.brightness, 255)
        self.assertEqual(light.min_color_temp_kelvin, light.color_temp_kelvin)

    def test_8bit_dimmer_color_temp_light_updates(self):
        channels = self.fixture.select_mode("8bit")
        entities = delegator.create_entities("Color Temp fader", 1, channels, None, self.universe)

        dimmer: DmxNumberEntity = get_entity_by_name(entities, "Color Temp fader Intensity")
        color_temp: DmxNumberEntity = get_entity_by_name(entities, "Color Temp fader Color Temperature")
        light: DmxLightEntity = get_entity_by_name(entities, "Color Temp fader Light")

        asyncio.run(light.async_turn_on(brightness=69, color_temp_kelvin=light.min_color_temp_kelvin))
        assert_dmx_range(self.universe, 1, [69, 0])
        self.assertAlmostEqual(69.0 / 2.55, dimmer.native_value, 0, 2)
        self.assertEqual(color_temp.min_value, color_temp.native_value)

        mid_kelvin = (light.max_color_temp_kelvin + light.min_color_temp_kelvin) / 2
        asyncio.run(light.async_turn_on(brightness=255, color_temp_kelvin=mid_kelvin))
        assert_dmx_range(self.universe, 1, [255, 128])
        self.assertEqual(100, dimmer.native_value)
        self.assertAlmostEqual((color_temp.max_value + color_temp.min_value) / 2, color_temp.native_value, None, "", 5)

        asyncio.run(light.async_turn_on(brightness=128))
        assert_dmx_range(self.universe, 1, [128, 128])
        self.assertAlmostEqual(50.0, dimmer.native_value, 0)
        self.assertAlmostEqual((color_temp.max_value + color_temp.min_value) / 2, color_temp.native_value, None, "", 5)

        asyncio.run(light.async_turn_on(brightness=255, color_temp_kelvin=light.max_color_temp_kelvin))
        assert_dmx_range(self.universe, 1, [255, 255])
        self.assertEqual(100, dimmer.native_value)
        self.assertEqual(color_temp.max_value, color_temp.native_value)

    def test_16bit_dimmer_color_temp_number_updates(self):
        channels = self.fixture.select_mode("16bit")
        entities = delegator.create_entities("Color Temp fader", 1, channels, None, self.universe)

        dimmer: DmxNumberEntity = get_entity_by_name(entities, "Color Temp fader Intensity")
        color_temp: DmxNumberEntity = get_entity_by_name(entities, "Color Temp fader Color Temperature")
        light: DmxLightEntity = get_entity_by_name(entities, "Color Temp fader Light")

        asyncio.run(dimmer.async_set_native_value(100))
        asyncio.run(color_temp.async_set_native_value(color_temp.max_value))
        assert_dmx_range(self.universe, 1, [255, 255, 255, 255])
        self.assertEqual(255, light.brightness)
        self.assertEqual(light.max_color_temp_kelvin, light.color_temp_kelvin)

        asyncio.run(dimmer.async_set_native_value(50))
        asyncio.run(color_temp.async_set_native_value((color_temp.max_value + color_temp.min_value) / 2))
        assert_dmx_range(self.universe, 1, [127, 255, 128, 0])
        self.assertEqual(127, light.brightness)
        self.assertAlmostEqual(
            (light.max_color_temp_kelvin + light.min_color_temp_kelvin) / 2, light.color_temp_kelvin, None, "", 5
        )

        asyncio.run(dimmer.async_set_native_value(100))
        asyncio.run(color_temp.async_set_native_value(color_temp.min_value))
        assert_dmx_range(self.universe, 1, [255, 255, 0, 0])
        self.assertEqual(255, light.brightness)
        self.assertEqual(light.min_color_temp_kelvin, light.color_temp_kelvin)

    def test_16bit_dimmer_color_temp_light_updates(self):
        channels = self.fixture.select_mode("16bit")
        entities = delegator.create_entities("Color Temp fader", 1, channels, None, self.universe)

        dimmer: DmxNumberEntity = get_entity_by_name(entities, "Color Temp fader Intensity")
        color_temp: DmxNumberEntity = get_entity_by_name(entities, "Color Temp fader Color Temperature")
        light: DmxLightEntity = get_entity_by_name(entities, "Color Temp fader Light")

        asyncio.run(light.async_turn_on(brightness=69.2, color_temp_kelvin=light.min_color_temp_kelvin))
        assert_dmx_range(self.universe, 1, [69, 120, 0, 0])
        self.assertAlmostEqual(69.0 / 2.55, dimmer.native_value, 0)
        self.assertEqual(color_temp.min_value, color_temp.native_value)

        mid_kelvin = (light.max_color_temp_kelvin + light.min_color_temp_kelvin) / 2
        asyncio.run(light.async_turn_on(brightness=255, color_temp_kelvin=mid_kelvin))
        assert_dmx_range(self.universe, 1, [255, 255, 128, 0])
        self.assertEqual(100, dimmer.native_value)
        self.assertAlmostEqual((color_temp.max_value + color_temp.min_value) / 2, color_temp.native_value, None, "", 5)

        asyncio.run(light.async_turn_on(brightness=255, color_temp_kelvin=light.max_color_temp_kelvin))
        assert_dmx_range(self.universe, 1, [255, 255, 255, 255])
        self.assertEqual(100, dimmer.native_value)
        self.assertEqual(color_temp.max_value, color_temp.native_value)

    def test_turn_on_restore_last_value(self):
        channels = self.fixture.select_mode("16bit")
        entities = delegator.create_entities("Color Temp fader", 1, channels, None, self.universe)

        dimmer: DmxNumberEntity = get_entity_by_name(entities, "Color Temp fader Intensity")
        color_temp: DmxNumberEntity = get_entity_by_name(entities, "Color Temp fader Color Temperature")
        light: DmxLightEntity = get_entity_by_name(entities, "Color Temp fader Light")

        mid_value = (color_temp.max_value + color_temp.min_value) / 2

        asyncio.run(dimmer.async_set_native_value(69))
        asyncio.run(color_temp.async_set_native_value(mid_value))
        self.assertTrue(light.is_on)

        asyncio.run(light.async_turn_off())
        self.assertFalse(light.is_on)
        self.assertEqual(0, dimmer.native_value)
        self.assertAlmostEqual(mid_value, color_temp.native_value, 1)

        asyncio.run(light.async_turn_on())
        self.assertTrue(light.is_on)
        self.assertAlmostEqual(69.0, dimmer.native_value, 0)
        self.assertAlmostEqual(mid_value, color_temp.native_value, None, "", 5)

        asyncio.run(dimmer.async_set_native_value(0))
        self.assertFalse(light.is_on)

        asyncio.run(light.async_turn_on())
        self.assertTrue(light.is_on)
        self.assertAlmostEqual(69.0, dimmer.native_value, 0)
        self.assertAlmostEqual(mid_value, color_temp.native_value, None, "", 5)


if __name__ == "__main__":
    unittest.main()
