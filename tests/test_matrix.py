import unittest
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import homeassistant.helpers.device_registry

from custom_components.dmx.fixture import parser, delegator
from tests.dmx_test_framework import MockDmxUniverse, get_entity_by_name, MockHomeAssistant

device_info_mock = MagicMock()
homeassistant.helpers.device_registry.DeviceInfo = device_info_mock


class TestSelectEntity(unittest.TestCase):

    def setUp(self):
        self.hass = MockHomeAssistant()
        self.write_ha_state_patcher = patch("homeassistant.helpers.entity.Entity.async_write_ha_state")
        self.mock_write_ha_state = self.write_ha_state_patcher.start()

        self.schedule_update_patcher = patch("homeassistant.helpers.entity.Entity.async_schedule_update_ha_state")
        self.mock_schedule_update = self.schedule_update_patcher.start()

        self.universe = MockDmxUniverse()

    def tearDown(self):
        self.write_ha_state_patcher.stop()
        self.schedule_update_patcher.stop()

    def test_matrix_abc(self):
        fixture_path = Path(__file__).parent / "fixtures" / "hydrabeam-300-rgbw.json"
        fixture = parser.parse(str(fixture_path))
        channels = fixture.select_mode("42ch")
        entities = delegator.create_entities("Hydrabeam", 1, channels, None, self.universe)

        self.assertEqual([1, 2], get_entity_by_name(entities, "Hydrabeam Pan 1").dmx_indexes)
        self.assertEqual([3, 4], get_entity_by_name(entities, "Hydrabeam Tilt 1").dmx_indexes)
        self.assertEqual([5], get_entity_by_name(entities, "Hydrabeam Head Speed 1 simple").dmx_indexes)
        self.assertEqual([6], get_entity_by_name(entities, "Hydrabeam Dimmer 1").dmx_indexes)
        self.assertEqual(7, get_entity_by_name(entities, "Hydrabeam Strobe 1").dmx_index)
        self.assertEqual(8, get_entity_by_name(entities, "Hydrabeam Color 1").dmx_index)
        self.assertEqual(9, get_entity_by_name(entities, "Hydrabeam Mode 1").dmx_index)
        self.assertEqual([10], get_entity_by_name(entities, "Hydrabeam Show mode speed 1").dmx_indexes)
        self.assertEqual([10], get_entity_by_name(entities, "Hydrabeam Sound sensitivity 1").dmx_indexes)
        self.assertEqual([11], get_entity_by_name(entities, "Hydrabeam Red 1").dmx_indexes)
        self.assertEqual([12], get_entity_by_name(entities, "Hydrabeam Green 1").dmx_indexes)
        self.assertEqual([13], get_entity_by_name(entities, "Hydrabeam Blue 1").dmx_indexes)
        self.assertEqual([14], get_entity_by_name(entities, "Hydrabeam White 1").dmx_indexes)

        self.assertEqual([15, 16], get_entity_by_name(entities, "Hydrabeam Pan 2").dmx_indexes)
        self.assertEqual([17, 18], get_entity_by_name(entities, "Hydrabeam Tilt 2").dmx_indexes)
        self.assertEqual([19], get_entity_by_name(entities, "Hydrabeam Head Speed 2 simple").dmx_indexes)
        self.assertEqual([20], get_entity_by_name(entities, "Hydrabeam Dimmer 2").dmx_indexes)
        self.assertEqual(21, get_entity_by_name(entities, "Hydrabeam Strobe 2").dmx_index)
        self.assertEqual(22, get_entity_by_name(entities, "Hydrabeam Color 2").dmx_index)
        self.assertEqual(23, get_entity_by_name(entities, "Hydrabeam Mode 2").dmx_index)
        self.assertEqual([24], get_entity_by_name(entities, "Hydrabeam Show mode speed 2").dmx_indexes)
        self.assertEqual([24], get_entity_by_name(entities, "Hydrabeam Sound sensitivity 2").dmx_indexes)
        self.assertEqual([25], get_entity_by_name(entities, "Hydrabeam Red 2").dmx_indexes)
        self.assertEqual([26], get_entity_by_name(entities, "Hydrabeam Green 2").dmx_indexes)
        self.assertEqual([27], get_entity_by_name(entities, "Hydrabeam Blue 2").dmx_indexes)
        self.assertEqual([28], get_entity_by_name(entities, "Hydrabeam White 2").dmx_indexes)

        self.assertEqual([29, 30], get_entity_by_name(entities, "Hydrabeam Pan 3").dmx_indexes)
        self.assertEqual([31, 32], get_entity_by_name(entities, "Hydrabeam Tilt 3").dmx_indexes)
        self.assertEqual([33], get_entity_by_name(entities, "Hydrabeam Head Speed 3 simple").dmx_indexes)
        self.assertEqual([34], get_entity_by_name(entities, "Hydrabeam Dimmer 3").dmx_indexes)
        self.assertEqual(35, get_entity_by_name(entities, "Hydrabeam Strobe 3").dmx_index)
        self.assertEqual(36, get_entity_by_name(entities, "Hydrabeam Color 3").dmx_index)
        self.assertEqual(37, get_entity_by_name(entities, "Hydrabeam Mode 3").dmx_index)
        self.assertEqual([38], get_entity_by_name(entities, "Hydrabeam Show mode speed 3").dmx_indexes)
        self.assertEqual([38], get_entity_by_name(entities, "Hydrabeam Sound sensitivity 3").dmx_indexes)
        self.assertEqual([39], get_entity_by_name(entities, "Hydrabeam Red 3").dmx_indexes)
        self.assertEqual([40], get_entity_by_name(entities, "Hydrabeam Green 3").dmx_indexes)
        self.assertEqual([41], get_entity_by_name(entities, "Hydrabeam Blue 3").dmx_indexes)
        self.assertEqual([42], get_entity_by_name(entities, "Hydrabeam White 3").dmx_indexes)

    def test_matrix_per_pixel(self):
        fixture_path = Path(__file__).parent / "fixtures" / "solaris-flare.json"
        fixture = parser.parse(str(fixture_path))
        channels = fixture.select_mode("RGBWstrobe12pix")
        entities = delegator.create_entities("Flare", 1, channels, None, self.universe)

        self.assertEqual([9], get_entity_by_name(entities, "Flare 12-Pixel 1 Red").dmx_indexes)
        self.assertEqual([10], get_entity_by_name(entities, "Flare 12-Pixel 1 Green").dmx_indexes)
        self.assertEqual([11], get_entity_by_name(entities, "Flare 12-Pixel 1 Blue").dmx_indexes)
        self.assertEqual([12], get_entity_by_name(entities, "Flare 12-Pixel 1 White").dmx_indexes)

        self.assertEqual([13], get_entity_by_name(entities, "Flare 12-Pixel 2 Red").dmx_indexes)
        self.assertEqual([14], get_entity_by_name(entities, "Flare 12-Pixel 2 Green").dmx_indexes)
        self.assertEqual([15], get_entity_by_name(entities, "Flare 12-Pixel 2 Blue").dmx_indexes)
        self.assertEqual([16], get_entity_by_name(entities, "Flare 12-Pixel 2 White").dmx_indexes)

        self.assertEqual([17], get_entity_by_name(entities, "Flare 12-Pixel 3 Red").dmx_indexes)
        self.assertEqual([18], get_entity_by_name(entities, "Flare 12-Pixel 3 Green").dmx_indexes)
        self.assertEqual([19], get_entity_by_name(entities, "Flare 12-Pixel 3 Blue").dmx_indexes)
        self.assertEqual([20], get_entity_by_name(entities, "Flare 12-Pixel 3 White").dmx_indexes)
