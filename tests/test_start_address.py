import unittest

import voluptuous as vol

from custom_components.dmx.setup.config_processor import DEVICE_CONFIG


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


if __name__ == "__main__":
    unittest.main()
