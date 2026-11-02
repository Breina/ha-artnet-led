import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import homeassistant.helpers.device_registry

from custom_components.dmx.fixture import delegator, parser
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

    def test_light_entity_name_has_no_light_suffix(self):
        """The light's name drives its entity_id.

        The old artnet_led integration produced light.{slugify(name)}. Appending
        anything to the name here (a " Light" suffix, say) changes the entity_id HA
        derives from it and silently breaks every migrated automation, scene and group.
        """
        from homeassistant.util import slugify

        from custom_components.dmx.entity.light.light_entity import DmxLightEntity

        fixture_path = Path(__file__).parent / "fixtures" / "rgbw-fader.json"
        fixture = parser.parse(str(fixture_path))
        channels = fixture.select_mode(next(iter(fixture.modes)))
        entities = delegator.create_entities("Bureau NO", 1, channels, None, self.universe)

        lights = [e for e in entities if isinstance(e, DmxLightEntity)]
        self.assertEqual(len(lights), 1)
        self.assertEqual(lights[0]._attr_name, "Bureau NO")
        self.assertEqual(f"light.{slugify(lights[0]._attr_name)}", "light.bureau_no")


if __name__ == "__main__":
    unittest.main()
