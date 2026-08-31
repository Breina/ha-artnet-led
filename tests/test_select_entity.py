import asyncio
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import homeassistant.helpers.device_registry
from homeassistant.core import State

from custom_components.dmx.entity.number import DmxNumberEntity
from custom_components.dmx.entity.select import DmxSelectEntity
from custom_components.dmx.fixture import delegator, parser
from tests.dmx_test_framework import (
    MockDmxUniverse,
    MockHomeAssistant,
    assert_dmx,
    assert_dmx_range,
    get_entity_by_name,
)

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

    def test_selection_updates(self):
        fixture_path = Path(__file__).parent / "fixtures" / "dj_scan_led.json"
        fixture = parser.parse(str(fixture_path))
        channels = fixture.select_mode("Normal")
        entities = delegator.create_entities("DJ Scan LED", 1, channels, None, self.universe)

        select: DmxSelectEntity = get_entity_by_name(entities, "DJ Scan LED Shutter")
        strobe1: DmxNumberEntity = get_entity_by_name(entities, "DJ Scan LED Shutter Strobe effect 1")
        strobe2: DmxNumberEntity = get_entity_by_name(entities, "DJ Scan LED Shutter Strobe effect 2")

        self.assertEqual("Open", select.current_option, "Default value")
        self.assertFalse(strobe1.available)
        self.assertFalse(strobe2.available)

        asyncio.run(select.async_select_option("Closed"))
        assert_dmx(self.universe, 5, 0)
        self.assertFalse(strobe1.available)
        self.assertFalse(strobe2.available)

        # menuClick center
        asyncio.run(select.async_select_option("Open"))
        assert_dmx(self.universe, 5, 14)
        self.assertFalse(strobe1.available)
        self.assertFalse(strobe2.available)

        asyncio.run(select.async_select_option("Strobe effect 1"))
        assert_dmx(self.universe, 5, 20)
        self.assertTrue(strobe1.available)
        self.assertFalse(strobe2.available)

        # menuClick end
        asyncio.run(select.async_select_option("Open 2"))
        assert_dmx(self.universe, 5, 137)
        self.assertFalse(strobe1.available)
        self.assertFalse(strobe2.available)

        asyncio.run(select.async_select_option("Strobe effect 2"))
        assert_dmx(self.universe, 5, 138)
        self.assertFalse(strobe1.available)
        self.assertTrue(strobe2.available)

    def test_number_updates(self):
        fixture_path = Path(__file__).parent / "fixtures" / "dj_scan_led.json"
        fixture = parser.parse(str(fixture_path))
        channels = fixture.select_mode("Normal")
        entities = delegator.create_entities("DJ Scan LED", 1, channels, None, self.universe)

        select: DmxSelectEntity = get_entity_by_name(entities, "DJ Scan LED Shutter")
        strobe1: DmxNumberEntity = get_entity_by_name(entities, "DJ Scan LED Shutter Strobe effect 1")
        strobe2: DmxNumberEntity = get_entity_by_name(entities, "DJ Scan LED Shutter Strobe effect 2")

        asyncio.run(select.async_select_option("Strobe effect 1"))
        assert_dmx(self.universe, 5, 20)
        self.assertEqual(1, strobe1.native_value)

        asyncio.run(strobe1.async_set_native_value(100))
        assert_dmx(self.universe, 5, 127)

        asyncio.run(select.async_select_option("Strobe effect 2"))
        assert_dmx(self.universe, 5, 138)
        self.assertEqual(1, strobe2.native_value)

        asyncio.run(strobe2.async_set_native_value(100))
        assert_dmx(self.universe, 5, 201)

        asyncio.run(select.async_select_option("Strobe effect 1"))
        assert_dmx(self.universe, 5, 20)
        self.assertEqual(1, strobe1.native_value)

    def test_switching_channel(self):
        fixture_path = Path(__file__).parent / "fixtures" / "hydrabeam-300-rgbw.json"
        fixture = parser.parse(str(fixture_path))
        channels = fixture.select_mode("42ch")
        entities = delegator.create_entities("Hydrabeam", 1, channels, None, self.universe)

        mode: DmxSelectEntity = get_entity_by_name(entities, "Hydrabeam Mode 1")
        speed: DmxNumberEntity = get_entity_by_name(entities, "Hydrabeam Show mode speed 1")
        sound: DmxNumberEntity = get_entity_by_name(entities, "Hydrabeam Sound sensitivity 1")

        asyncio.run(speed.async_set_native_value(1))
        asyncio.run(sound.async_set_native_value(1))

        self.assertEqual("No function", mode.current_option, "Default value")
        self.assertTrue(speed.available)
        self.assertFalse(sound.available)
        assert_dmx_range(self.universe, 9, [0, 0])

        asyncio.run(mode.async_select_option("Show mode 1"))
        self.assertTrue(speed.available)
        self.assertFalse(sound.available)
        assert_dmx_range(self.universe, 9, [8, 0])

        asyncio.run(speed.async_set_native_value(100))
        self.assertEqual(1, sound.native_value)

        assert_dmx_range(self.universe, 9, [8, 255])

        asyncio.run(mode.async_select_option("Sound control sound controlled"))
        self.assertFalse(speed.available)
        self.assertTrue(sound.available)
        assert_dmx_range(self.universe, 9, [100, 0])

        asyncio.run(sound.async_set_native_value(100))
        assert_dmx_range(self.universe, 9, [100, 255])

        asyncio.run(mode.async_select_option("Show mode 2"))
        self.assertTrue(speed.available)
        self.assertFalse(sound.available)
        assert_dmx_range(self.universe, 9, [31, 255])

    def test_restores_option_after_restart(self):
        """A select that was left on a non-default option before an HA restart
        must come back on that same option, and must re-push the corresponding
        DMX value onto the wire -- the physical fixture has no memory of its
        own and silently reverts to its own default the moment DMX goes quiet,
        so restoring HA's in-memory state alone isn't enough.
        """
        fixture_path = Path(__file__).parent / "fixtures" / "dj_scan_led.json"
        fixture = parser.parse(str(fixture_path))
        channels = fixture.select_mode("Normal")
        entities = delegator.create_entities("DJ Scan LED", 1, channels, None, self.universe)

        select: DmxSelectEntity = get_entity_by_name(entities, "DJ Scan LED Shutter")
        strobe1: DmxNumberEntity = get_entity_by_name(entities, "DJ Scan LED Shutter Strobe effect 1")

        # Simulate a fresh universe (as after an HA/fixture restart) where the
        # select entity's own channel hasn't been written to yet, and HA's
        # restore-state cache reports the option it was left on before restart.
        self.assertEqual("Open", select.current_option, "Fresh entity still on its default")
        self.assertFalse(self.universe.is_channel_set(select.dmx_index))

        with patch.object(
            DmxSelectEntity, "async_get_last_state", return_value=State("select.dj_scan_led_shutter", "Strobe effect 1")
        ):
            asyncio.run(select.async_added_to_hass())

        self.assertEqual("Strobe effect 1", select.current_option)
        assert_dmx(self.universe, select.dmx_index, 20)
        self.assertTrue(strobe1.available)

    def test_does_not_restore_over_a_value_already_on_the_wire(self):
        """If something already wrote to this channel (e.g. a racing user
        command) before the restore runs, the restore must not clobber it.
        """
        fixture_path = Path(__file__).parent / "fixtures" / "dj_scan_led.json"
        fixture = parser.parse(str(fixture_path))
        channels = fixture.select_mode("Normal")
        entities = delegator.create_entities("DJ Scan LED", 1, channels, None, self.universe)

        select: DmxSelectEntity = get_entity_by_name(entities, "DJ Scan LED Shutter")
        asyncio.run(select.async_select_option("Strobe effect 1"))
        assert_dmx(self.universe, select.dmx_index, 20)

        with patch.object(
            DmxSelectEntity, "async_get_last_state", return_value=State("select.dj_scan_led_shutter", "Strobe effect 2")
        ):
            asyncio.run(select.async_added_to_hass())

        self.assertEqual("Strobe effect 1", select.current_option, "Restore must not override an already-set channel")
        assert_dmx(self.universe, select.dmx_index, 20)


if __name__ == "__main__":
    unittest.main()
