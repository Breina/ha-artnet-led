import unittest

import yaml

from custom_components.dmx.migration import extract_old_entries, run_migration, to_plain_types


class AnnotatedStr(str):
    """Stand-in for annotatedyaml.objects.NodeStrClass.

    Home Assistant hands async_setup a config parsed by annotatedyaml, whose
    scalars are str subclasses carrying __config_file__ / __line__ metadata.
    PyYAML serialises those as !!python/object tags unless they are flattened
    first, which is what these tests guard against.
    """

    __slots__ = ("__config_file__", "__line__")


class AnnotatedDict(dict):
    pass


class AnnotatedList(list):
    pass


OLD_CONFIG = {
    "light": AnnotatedList(
        [
            AnnotatedDict(
                {
                    "platform": AnnotatedStr("artnet_led"),
                    "host": AnnotatedStr("192.168.1.15"),
                    "max_fps": 43,
                    "refresh_every": 0,
                    "node_type": AnnotatedStr("artnet-controller"),
                    "universes": AnnotatedDict(
                        {
                            0: AnnotatedDict(
                                {
                                    "send_partial_universe": True,
                                    "output_correction": AnnotatedStr("quadratic"),
                                    "devices": AnnotatedList(
                                        [
                                            AnnotatedDict(
                                                {
                                                    "channel": 1,
                                                    "name": AnnotatedStr("Bureau NO"),
                                                    "type": AnnotatedStr("color_temp"),
                                                    "channel_size": AnnotatedStr("16bit"),
                                                    "min_temp": AnnotatedStr("2500K"),
                                                    "max_temp": AnnotatedStr("6500K"),
                                                }
                                            ),
                                        ]
                                    ),
                                }
                            ),
                        }
                    ),
                }
            )
        ]
    )
}


class TestToPlainTypes(unittest.TestCase):

    def test_strips_str_subclass(self):
        result = to_plain_types(AnnotatedStr("quadratic"))
        self.assertEqual(result, "quadratic")
        self.assertIs(type(result), str)

    def test_strips_nested_containers(self):
        result = to_plain_types(
            AnnotatedDict({AnnotatedStr("k"): AnnotatedList([AnnotatedStr("v"), AnnotatedDict({})])})
        )
        self.assertIs(type(result), dict)
        self.assertIs(type(next(iter(result))), str)
        self.assertIs(type(result["k"]), list)
        self.assertIs(type(result["k"][0]), str)

    def test_bool_stays_bool(self):
        # bool is a subclass of int, so order of the isinstance checks matters
        self.assertIs(to_plain_types(True), True)
        self.assertIs(type(to_plain_types(True)), bool)

    def test_tuple_becomes_list(self):
        self.assertEqual(to_plain_types((1, 2)), [1, 2])


class TestMigrationOutputIsSafeYaml(unittest.TestCase):

    def setUp(self):
        self.result = run_migration(extract_old_entries(OLD_CONFIG))

    def test_config_round_trips_through_safe_yaml(self):
        dumped = yaml.safe_dump(self.result.dmx_config, sort_keys=False)
        self.assertNotIn("!!python", dumped)
        self.assertEqual(yaml.safe_load(dumped), self.result.dmx_config)

    def test_device_name_key_is_plain_str(self):
        devices = self.result.dmx_config["dmx"]["artnet"]["universes"][0][0]["devices"]
        [(name, device)] = devices[0].items()
        self.assertIs(type(name), str)
        self.assertEqual(name, "Bureau NO")
        self.assertIs(type(device["output_correction"]), str)

    def test_fixture_short_name_matches_the_key_the_config_references(self):
        """The registry indexes fixtures by shortName/name, never by filename."""
        devices = self.result.dmx_config["dmx"]["artnet"]["universes"][0][0]["devices"]
        referenced = {next(iter(d.values()))["fixture"] for d in devices}
        short_names = {f["shortName"] for f in self.result.fixture_map.values()}
        self.assertTrue(referenced)
        self.assertTrue(referenced <= short_names, f"{referenced - short_names} not resolvable")

    def test_short_name_matches_generated_filename_key(self):
        for sig, fixture in self.result.fixture_map.items():
            self.assertEqual(fixture["shortName"], self.result.fixture_key_map[sig])

    def test_start_address_is_one_based(self):
        """`channel: 1` in the old format is the first DMX slot, and so is
        `start_address: 1` in the new one -- an off-by-one here silently shifts every
        device in the universe by one channel."""
        devices = self.result.dmx_config["dmx"]["artnet"]["universes"][0][0]["devices"]
        [(name, device)] = devices[0].items()
        self.assertEqual(name, "Bureau NO")  # old config had channel: 1
        self.assertEqual(device["start_address"], 1)

    def test_no_entity_id_prefix_is_emitted(self):
        """The device name alone reproduces the old light.{slugify(name)} entity_id.

        Emitting entity_id_prefix from friendly_name would change the entity_id, which
        is exactly what must not happen for automations to survive the migration.
        """
        for universe in self.result.dmx_config["dmx"]["artnet"]["universes"]:
            for device_dict in next(iter(universe.values()))["devices"]:
                [(_, device)] = device_dict.items()
                self.assertNotIn("entity_id_prefix", device)

    def test_fixtures_round_trip_through_safe_yaml(self):
        for fixture in self.result.fixture_map.values():
            dumped = yaml.safe_dump(fixture, sort_keys=False)
            self.assertNotIn("!!python", dumped)


if __name__ == "__main__":
    unittest.main()
