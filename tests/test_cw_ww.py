import asyncio
import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

import homeassistant.helpers.device_registry

from custom_components.artnet_led.entity.light.light_entity import DmxLightEntity
from custom_components.artnet_led.entity.number import DmxNumberEntity
from custom_components.artnet_led.fixture import parser
from custom_components.artnet_led.fixture_delegator import delegator
from test_helpers.dmx_test_framework import MockDmxUniverse, assert_entity_by_name, MockHomeAssistant, assert_dmx_range

device_info_mock = MagicMock()
homeassistant.helpers.device_registry.DeviceInfo = device_info_mock


class TestRgbwFixture(unittest.TestCase):

    def setUp(self):
        self.hass = MockHomeAssistant()
        self.write_ha_state_patcher = patch('homeassistant.helpers.entity.Entity.async_write_ha_state')
        self.mock_write_ha_state = self.write_ha_state_patcher.start()

        self.schedule_update_patcher = patch('homeassistant.helpers.entity.Entity.async_schedule_update_ha_state')
        self.mock_schedule_update = self.schedule_update_patcher.start()

        self.fixture = parser.parse('fixtures/cw-ww-fader.json')
        self.universe = MockDmxUniverse()

    def tearDown(self):
        self.write_ha_state_patcher.stop()
        self.schedule_update_patcher.stop()

    def test_8bit_wc_number_updates(self):
        channels = self.fixture.select_mode('8bit-wc')
        entities = delegator.create_entities('WC fader', 1, channels, None, self.universe)

        warm_white: DmxNumberEntity = assert_entity_by_name(entities, 'WC fader Warm White')
        cold_white: DmxNumberEntity = assert_entity_by_name(entities, 'WC fader Cold White')
        light: DmxLightEntity = assert_entity_by_name(entities, 'WC fader Light')

        asyncio.run(warm_white.async_set_native_value(100))
        asyncio.run(cold_white.async_set_native_value(0))
        assert_dmx_range(self.universe, 1, [255, 0])
        self.assertEqual(light.brightness, 255)
        self.assertEqual(light.color_temp, light.max_mireds)

        mid_mired = (light.min_mireds + light.max_mireds - 1) / 2
        asyncio.run(warm_white.async_set_native_value(50))
        asyncio.run(cold_white.async_set_native_value(50))
        assert_dmx_range(self.universe, 1, [127, 127])
        self.assertEqual(light.brightness, 127)
        self.assertEqual(light.color_temp, mid_mired)

        asyncio.run(warm_white.async_set_native_value(100))
        asyncio.run(cold_white.async_set_native_value(100))
        assert_dmx_range(self.universe, 1, [255, 255])
        self.assertEqual(light.brightness, 255)
        self.assertEqual(light.color_temp, mid_mired)

        asyncio.run(warm_white.async_set_native_value(0))
        asyncio.run(cold_white.async_set_native_value(100))
        assert_dmx_range(self.universe, 1, [0, 255])
        self.assertEqual(light.brightness, 255)
        self.assertEqual(light.color_temp, light.min_mireds)

    def test_8bit_wc_light_updates(self):
        channels = self.fixture.select_mode('8bit-wc')
        entities = delegator.create_entities('WC fader', 1, channels, None, self.universe)

        warm_white: DmxNumberEntity = assert_entity_by_name(entities, 'WC fader Warm White')
        cold_white: DmxNumberEntity = assert_entity_by_name(entities, 'WC fader Cold White')
        light: DmxLightEntity = assert_entity_by_name(entities, 'WC fader Light')

        asyncio.run(light.async_turn_on(brightness=255, color_temp=light.max_mireds))
        assert_dmx_range(self.universe, 1, [255, 0])
        self.assertEqual(warm_white.native_value, 100)
        self.assertEqual(cold_white.native_value, 0)

        mid_mired = (light.min_mireds + light.max_mireds - 1) / 2
        asyncio.run(light.async_turn_on(brightness=127, color_temp=mid_mired))
        assert_dmx_range(self.universe, 1, [127, 127])
        self.assertEqual(warm_white.native_value, 50)
        self.assertEqual(cold_white.native_value, 50)

        asyncio.run(light.async_turn_on(brightness=255, color_temp=light.min_mireds))
        assert_dmx_range(self.universe, 1, [0, 255])
        self.assertEqual(warm_white.native_value, 0)
        self.assertEqual(cold_white.native_value, 100)

    def test_16bit_cw_number_updates(self):
        channels = self.fixture.select_mode('16bit-cw')
        entities = delegator.create_entities('CW fader', 1, channels, None, self.universe)

        warm_white: DmxNumberEntity = assert_entity_by_name(entities, 'CW fader Warm White')
        cold_white: DmxNumberEntity = assert_entity_by_name(entities, 'CW fader Cold White')
        light: DmxLightEntity = assert_entity_by_name(entities, 'CW fader Light')

        asyncio.run(warm_white.async_set_native_value(100))
        asyncio.run(cold_white.async_set_native_value(0))
        assert_dmx_range(self.universe, 1, [0, 0, 255, 255])
        self.assertEqual(light.brightness, 255)
        self.assertEqual(light.color_temp, light.max_mireds)

        mid_mired = (light.min_mireds + light.max_mireds - 1) / 2
        asyncio.run(warm_white.async_set_native_value(50))
        asyncio.run(cold_white.async_set_native_value(50))
        assert_dmx_range(self.universe, 1, [127, 127, 127, 127])
        self.assertEqual(light.brightness, 127)
        self.assertEqual(light.color_temp, mid_mired)

        asyncio.run(warm_white.async_set_native_value(100))
        asyncio.run(cold_white.async_set_native_value(100))
        assert_dmx_range(self.universe, 1, [255, 255, 255, 255])
        self.assertEqual(light.brightness, 255)
        self.assertEqual(light.color_temp, mid_mired)

        asyncio.run(warm_white.async_set_native_value(0))
        asyncio.run(cold_white.async_set_native_value(100))
        assert_dmx_range(self.universe, 1, [255, 255, 0, 0])
        self.assertEqual(light.brightness, 255)
        self.assertEqual(light.color_temp, light.min_mireds)

    def test_16bit_cw_light_updates(self):
        channels = self.fixture.select_mode('16bit-cw')
        entities = delegator.create_entities('CW fader', 1, channels, None, self.universe)

        warm_white: DmxNumberEntity = assert_entity_by_name(entities, 'CW fader Warm White')
        cold_white: DmxNumberEntity = assert_entity_by_name(entities, 'CW fader Cold White')
        light: DmxLightEntity = assert_entity_by_name(entities, 'CW fader Light')

        asyncio.run(light.async_turn_on(brightness=255, color_temp=light.max_mireds))
        assert_dmx_range(self.universe, 1, [0, 0, 255, 255])
        self.assertEqual(warm_white.native_value, 100)
        self.assertEqual(cold_white.native_value, 0)

        mid_mired = (light.min_mireds + light.max_mireds - 1) / 2
        asyncio.run(light.async_turn_on(brightness=127, color_temp=mid_mired))
        assert_dmx_range(self.universe, 1, [127, 127, 127, 127])
        self.assertEqual(warm_white.native_value, 50)
        self.assertEqual(cold_white.native_value, 50)

        asyncio.run(light.async_turn_on(brightness=255, color_temp=light.min_mireds))
        assert_dmx_range(self.universe, 1, [255, 255, 0, 0])
        self.assertEqual(warm_white.native_value, 0)
        self.assertEqual(cold_white.native_value, 100)


if __name__ == "__main__":
    unittest.main()
