import asyncio
import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

import homeassistant.helpers.device_registry

from custom_components.artnet_led.entity.light.light_entity import DmxLightEntity
from custom_components.artnet_led.entity.number import DmxNumberEntity
from custom_components.artnet_led.fixture import parser
from custom_components.artnet_led.fixture_delegator import delegator
from tests.dmx_test_framework import MockDmxUniverse, assert_entity_by_name, MockHomeAssistant, assert_dmx_range

device_info_mock = MagicMock()
homeassistant.helpers.device_registry.DeviceInfo = device_info_mock


class TestColorTemperatureFader(unittest.TestCase):

    def setUp(self):
        self.hass = MockHomeAssistant()
        self.write_ha_state_patcher = patch('homeassistant.helpers.entity.Entity.async_write_ha_state')
        self.mock_write_ha_state = self.write_ha_state_patcher.start()

        self.schedule_update_patcher = patch('homeassistant.helpers.entity.Entity.async_schedule_update_ha_state')
        self.mock_schedule_update = self.schedule_update_patcher.start()

        self.fixture = parser.parse('fixtures/color-temperature-fader.json')
        self.universe = MockDmxUniverse()

    def tearDown(self):
        self.write_ha_state_patcher.stop()
        self.schedule_update_patcher.stop()

    def test_color_temperature_metadata(self):
        channels = self.fixture.select_mode('8bit')
        entities = delegator.create_entities('Color Temp fader', 1, channels, None, self.universe)

        color_temp: DmxNumberEntity = assert_entity_by_name(entities, 'Color Temp fader Color Temperature')
        light: DmxLightEntity = assert_entity_by_name(entities, 'Color Temp fader Light')

        self.assertEqual(color_temp.min_value, 6500)
        self.assertEqual(color_temp.max_value, 8500)
        self.assertEqual(light.min_color_temp_kelvin, 6500)
        self.assertEqual(light.max_color_temp_kelvin, 8500)

    def test_8bit_dimmer_color_temp_number_updates(self):
        channels = self.fixture.select_mode('8bit')
        entities = delegator.create_entities('Color Temp fader', 1, channels, None, self.universe)

        dimmer: DmxNumberEntity = assert_entity_by_name(entities, 'Color Temp fader Intensity')
        color_temp: DmxNumberEntity = assert_entity_by_name(entities, 'Color Temp fader Color Temperature')
        light: DmxLightEntity = assert_entity_by_name(entities, 'Color Temp fader Light')

        asyncio.run(dimmer.async_set_native_value(100))
        asyncio.run(color_temp.async_set_native_value(color_temp.max_value))
        assert_dmx_range(self.universe, 1, [255, 255])
        self.assertEqual(255, light.brightness)
        self.assertEqual(light.max_mireds, light.color_temp)

        asyncio.run(dimmer.async_set_native_value(50))
        asyncio.run(color_temp.async_set_native_value((color_temp.max_value + color_temp.min_value) / 2))
        assert_dmx_range(self.universe, 1, [127, 128])
        self.assertEqual(light.brightness, 127)
        self.assertEqual((light.min_mireds + light.max_mireds) / 2, light.color_temp)

        asyncio.run(dimmer.async_set_native_value(100))
        asyncio.run(color_temp.async_set_native_value(color_temp.min_value))
        assert_dmx_range(self.universe, 1, [255, 0])
        self.assertEqual(light.brightness, 255)
        self.assertEqual(light.min_mireds, light.color_temp)

if __name__ == "__main__":
    unittest.main()