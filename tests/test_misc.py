import unittest
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import homeassistant.helpers.device_registry

from custom_components.dmx.fixture import parser, delegator
from tests.dmx_test_framework import MockDmxUniverse, MockHomeAssistant

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

    def test_uv(self):
        fixture_path = Path(__file__).parent / "fixtures" / "par-uv.json"
        fixture = parser.parse(str(fixture_path))
        channels = fixture.select_mode("A")
        delegator.create_entities("PAR UV", 1, channels, None, self.universe)


if __name__ == "__main__":
    unittest.main()
