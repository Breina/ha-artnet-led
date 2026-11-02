import unittest
from unittest.mock import MagicMock, patch

import voluptuous as vol

from custom_components.dmx.fixture.capability import DmxValueResolution, Intensity
from custom_components.dmx.fixture.channel import Channel, ChannelOffset
from custom_components.dmx.setup.config_processor import DEVICE_CONFIG
from custom_components.dmx.setup.entity_factory import EntityFactory


class TestStartAddressSchema(unittest.TestCase):
    def test_every_slot_of_a_universe_is_accepted(self):
        for start_address in (1, 2, 511, 512):
            with self.subTest(start_address=start_address):
                config = DEVICE_CONFIG({"start_address": start_address, "fixture": "x"})
                self.assertEqual(start_address, config["start_address"])

    def test_outside_of_a_universe_is_rejected(self):
        for start_address in (-1, 0, 513):
            with self.subTest(start_address=start_address), self.assertRaises(vol.Invalid):
                DEVICE_CONFIG({"start_address": start_address, "fixture": "x"})


def _fixture(channel_count: int) -> MagicMock:
    channel = Channel("Dimmer", [], DmxValueResolution._8BIT)
    channel.define_capability(Intensity(dmx_value_resolution=DmxValueResolution._8BIT))
    fixture = MagicMock()
    fixture.modes = {"mode": None}
    fixture.select_mode.return_value = [ChannelOffset(channel, 0)] * channel_count
    return fixture


class TestDeviceWithinUniverse(unittest.TestCase):
    def _created(self, start_address: int, channel_count: int) -> bool:
        factory = EntityFactory({"fixture": _fixture(channel_count)})
        universe = {"devices": [{"device": {"start_address": start_address, "fixture": "fixture"}}]}
        with patch("custom_components.dmx.setup.entity_factory.create_entities", return_value=[]) as create:
            factory.create_entities_for_universe(universe, MagicMock(), {})
        return create.called

    def test_fits_up_to_the_last_slot(self):
        self.assertTrue(self._created(1, 512))
        self.assertTrue(self._created(512, 1))
        self.assertTrue(self._created(509, 4))

    def test_past_the_last_slot_is_ignored(self):
        with self.assertLogs("custom_components.dmx.setup.entity_factory", "ERROR"):
            self.assertFalse(self._created(512, 2))

    def test_address_zero_from_an_older_config_entry_is_ignored(self):
        with self.assertLogs("custom_components.dmx.setup.entity_factory", "ERROR"):
            self.assertFalse(self._created(0, 1))


if __name__ == "__main__":
    unittest.main()
