import asyncio
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import homeassistant.helpers.device_registry

from custom_components.dmx.entity.light.light_entity import DmxLightEntity
from custom_components.dmx.entity.number import DmxNumberEntity
from custom_components.dmx.fixture import parser, delegator
from tests.dmx_test_framework import MockDmxUniverse, get_entity_by_name, MockHomeAssistant, assert_dmx_range

device_info_mock = MagicMock()
homeassistant.helpers.device_registry.DeviceInfo = device_info_mock


class TestColorTemperatureFader(unittest.TestCase):

    def setUp(self):
        self.hass = MockHomeAssistant()
        self.write_ha_state_patcher = patch('homeassistant.helpers.entity.Entity.async_write_ha_state')
        self.mock_write_ha_state = self.write_ha_state_patcher.start()

        self.schedule_update_patcher = patch('homeassistant.helpers.entity.Entity.async_schedule_update_ha_state')
        self.mock_schedule_update = self.schedule_update_patcher.start()

        fixture_path = Path(__file__).parent / 'fixtures' / 'desk-channel.json'
        self.fixture = parser.parse(str(fixture_path))
        self.universe = MockDmxUniverse()

    def tearDown(self):
        self.write_ha_state_patcher.stop()
        self.schedule_update_patcher.stop()

    def test_8bit_number_updates(self):
        channels = self.fixture.select_mode('8bit')
        entities = delegator.create_entities('Desk channel', 1, channels, None, self.universe)

        dimmer: DmxNumberEntity = get_entity_by_name(entities, 'Desk channel Intensity')
        light: DmxLightEntity = get_entity_by_name(entities, 'Desk channel Light')

        asyncio.run(dimmer.async_set_native_value(0))
        assert_dmx_range(self.universe, 1, [0])
        self.assertEqual(0, light.brightness)

        asyncio.run(dimmer.async_set_native_value(1))
        assert_dmx_range(self.universe, 1, [3])
        self.assertEqual(3, light.brightness)

        asyncio.run(dimmer.async_set_native_value(99))
        assert_dmx_range(self.universe, 1, [252])
        self.assertEqual(252, light.brightness)

        asyncio.run(dimmer.async_set_native_value(100))
        assert_dmx_range(self.universe, 1, [255])
        self.assertEqual(255, light.brightness)

    def test_8bit_light_updates(self):
        channels = self.fixture.select_mode('8bit')
        entities = delegator.create_entities('Desk channel', 1, channels, None, self.universe)

        dimmer: DmxNumberEntity = get_entity_by_name(entities, 'Desk channel Intensity')
        light: DmxLightEntity = get_entity_by_name(entities, 'Desk channel Light')

        asyncio.run(light.async_turn_on(brightness=0))
        assert_dmx_range(self.universe, 1, [0])
        self.assertEqual(0, dimmer.native_value)

        asyncio.run(light.async_turn_on(brightness=3))
        assert_dmx_range(self.universe, 1, [3])
        self.assertAlmostEqual(1.0, dimmer.native_value, 0)

        asyncio.run(light.async_turn_on(brightness=252))
        assert_dmx_range(self.universe, 1, [252])
        self.assertAlmostEqual(99, dimmer.native_value, 0)

        asyncio.run(light.async_turn_on(brightness=255))
        assert_dmx_range(self.universe, 1, [255])
        self.assertEqual(100, dimmer.native_value)

    def test_16bit_number_updates(self):
        channels = self.fixture.select_mode('16bit')
        entities = delegator.create_entities('Desk channel', 1, channels, None, self.universe)

        dimmer: DmxNumberEntity = get_entity_by_name(entities, 'Desk channel Intensity')

        asyncio.run(dimmer.async_set_native_value(0))
        assert_dmx_range(self.universe, 1, [0, 0])

        asyncio.run(dimmer.async_set_native_value(1.2))
        assert_dmx_range(self.universe, 1, [3, 18])

        asyncio.run(dimmer.async_set_native_value(99))
        assert_dmx_range(self.universe, 1, [253, 112])

        asyncio.run(dimmer.async_set_native_value(100))
        assert_dmx_range(self.universe, 1, [255, 255])

    def test_16bit_light_updates(self):
        channels = self.fixture.select_mode('16bit')
        entities = delegator.create_entities('Desk channel', 1, channels, None, self.universe)

        light: DmxLightEntity = get_entity_by_name(entities, 'Desk channel Light')

        asyncio.run(light.async_turn_on(brightness=0))
        assert_dmx_range(self.universe, 1, [0, 0])

        asyncio.run(light.async_turn_on(brightness=3))
        assert_dmx_range(self.universe, 1, [3, 3])

        asyncio.run(light.async_turn_on(brightness=252))
        assert_dmx_range(self.universe, 1, [252, 252])

        asyncio.run(light.async_turn_on(brightness=255))
        assert_dmx_range(self.universe, 1, [255, 255])


if __name__ == "__main__":
    unittest.main()
