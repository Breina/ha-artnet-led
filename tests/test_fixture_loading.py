"""Channel layouts from the Open Fixture Library which used to keep a fixture or a mode from loading."""

import unittest
from typing import Any, ClassVar

from custom_components.dmx.entity.light.light_entity import DmxLightEntity
from custom_components.dmx.entity.number import DmxNumberEntity
from custom_components.dmx.entity.select import DmxSelectEntity
from custom_components.dmx.fixture import delegator, parser
from custom_components.dmx.fixture.exceptions import FixtureConfigurationError
from custom_components.dmx.io.dmx_io import DmxUniverse

START = 1


def _load(channels: dict[str, Any], mode: list[str | None]) -> tuple[list[Any], DmxUniverse]:
    fixture = parser._parse_fixture_data(
        {
            "name": "T",
            "categories": ["Other"],
            "availableChannels": channels,
            "modes": [{"name": "m", "channels": mode}],
        }
    )
    universe = DmxUniverse(None, None, True)
    return delegator.create_entities("X", START, fixture.select_mode("m"), None, universe), universe


def _one(entities: list[Any], kind: type) -> Any:
    found = [e for e in entities if isinstance(e, kind)]
    assert len(found) == 1, found
    return found[0]


def _slider(entities: list[Any], name_part: str) -> DmxNumberEntity:
    return next(e for e in entities if isinstance(e, DmxNumberEntity) and name_part in e.name)


def _slots(universe: DmxUniverse, count: int) -> list[int]:
    return [universe.get_channel_value(slot) for slot in range(START, START + count)]


def _generic(start: int, end: int, comment: str) -> dict[str, Any]:
    return {"dmxRange": [start, end], "type": "Generic", "comment": comment}


GREEN_MAGENTA = {
    "fineChannelAliases": ["Point fine"],
    "capabilities": [
        _generic(0, 5000, "Neutral"),
        _generic(5001, 30000, "Minus"),
        _generic(30001, 65535, "Plus"),
    ],
}


class TestRedirect(unittest.TestCase):
    def test_redirect_says_where_the_definition_is(self):
        data = {"name": "Old", "redirectTo": "maker/new", "reason": "FixtureRenamed"}
        with self.assertRaisesRegex(FixtureConfigurationError, "maker/new"):
            parser._parse_fixture_data(data)


class TestSwitchingToUnusedChannel(unittest.TestCase):
    CHANNELS: ClassVar[dict[str, Any]] = {
        "Switch": {
            "defaultValue": 0,
            "capabilities": [
                {**_generic(0, 127, "Foo mode"), "switchChannels": {"Alias": "Foo"}},
                {**_generic(128, 255, "Nothing"), "switchChannels": {"Alias": None}},
            ],
        },
        "Foo": {"capability": {"type": "Intensity"}},
    }

    def test_loads_with_the_other_switched_channel(self):
        entities, _ = _load(self.CHANNELS, ["Switch", "Alias"])

        number = next(e for e in entities if isinstance(e, DmxNumberEntity) and e.name == "X Foo")
        self.assertEqual([2], number.dmx_indexes)

    def test_switched_channels_have_a_fixed_order(self):
        fixture = parser._parse_fixture_data(
            {
                "name": "T",
                "categories": ["Other"],
                "availableChannels": {
                    "Switch": {
                        "defaultValue": 0,
                        "capabilities": [
                            {**_generic(0, 100, "C"), "switchChannels": {"Alias": "C"}},
                            {**_generic(101, 200, "A"), "switchChannels": {"Alias": "A"}},
                            {**_generic(201, 255, "B"), "switchChannels": {"Alias": "B"}},
                        ],
                    },
                    "A": {"capability": {"type": "Intensity"}},
                    "B": {"capability": {"type": "Intensity"}},
                    "C": {"capability": {"type": "Intensity"}},
                },
                "modes": [{"name": "m", "channels": ["Switch", "Alias"]}],
            }
        )
        self.assertEqual(["A", "B", "C"], list(fixture.switching_channels["Alias"].controlled_channels))


class TestChannelDoingOneThing(unittest.IsolatedAsyncioTestCase):
    async def test_controllable_through_its_raw_value(self):
        entities, universe = _load({"Output": {"capability": {"type": "Maintenance"}}}, ["Output"])

        number = _one(entities, DmxNumberEntity)
        self.assertEqual((0, 255), (number.native_min_value, number.native_max_value))

        await number.async_set_native_value(128)
        self.assertEqual([128], _slots(universe, 1))

    def test_no_function_has_nothing_to_control(self):
        entities, _ = _load({"Reserved": {"capability": {"type": "NoFunction"}}}, ["Reserved"])
        self.assertEqual([], entities)

    def test_fixed_color_temperature_is_no_light_channel(self):
        channels = {"Kelvin": {"capability": {"type": "ColorTemperature", "colorTemperature": "3200K"}}}
        entities, _ = _load(channels, ["Kelvin"])

        self.assertFalse(any(isinstance(e, DmxLightEntity) for e in entities))
        self.assertEqual([1], _one(entities, DmxNumberEntity).dmx_indexes)


class TestCapabilityChangingSeveralThings(unittest.IsolatedAsyncioTestCase):
    async def test_slider_is_for_the_first_thing(self):
        channels = {
            "Wheel": {
                "capabilities": [
                    _generic(0, 99, "Open"),
                    {
                        "dmxRange": [100, 200],
                        "type": "WheelShake",
                        "shakeSpeedStart": "slow",
                        "shakeSpeedEnd": "fast",
                        "shakeAngleStart": "10deg",
                        "shakeAngleEnd": "25deg",
                    },
                ],
            }
        }
        entities, universe = _load(channels, ["Wheel"])

        number = _slider(entities, "slow")
        self.assertEqual((1, 100), (number.native_min_value, number.native_max_value))

        await number.async_set_native_value(100)
        self.assertEqual([200], _slots(universe, 1))


class TestSixteenBitCapabilities(unittest.IsolatedAsyncioTestCase):
    async def test_select_writes_both_bytes(self):
        entities, universe = _load({"Point": GREEN_MAGENTA}, ["Point", "Point fine"])

        select = _one(entities, DmxSelectEntity)
        self.assertEqual([1, 2], select.dmx_indexes)

        await select.async_select_option("Minus")
        self.assertEqual([5001 >> 8, 5001 & 0xFF], _slots(universe, 2))

    async def test_select_follows_both_bytes(self):
        entities, universe = _load({"Point": GREEN_MAGENTA}, ["Point", "Point fine"])
        select = _one(entities, DmxSelectEntity)

        await universe.update_multiple_values({1: 30001 >> 8, 2: 30001 & 0xFF})
        self.assertEqual("Plus", select.current_option)

        await universe.update_multiple_values({1: 30000 >> 8, 2: 30000 & 0xFF})
        self.assertEqual("Minus", select.current_option)

    async def test_mode_without_the_fine_channel_stays_within_the_capability(self):
        entities, universe = _load({"Point": GREEN_MAGENTA}, ["Point"])
        select = _one(entities, DmxSelectEntity)

        await select.async_select_option("Minus")
        self.assertEqual([20], _slots(universe, 1))  # 19 would be 4864: part of Neutral

        select.update_value(None)
        self.assertEqual("Minus", select.current_option)

    async def test_slider_covers_the_range_of_its_capability(self):
        channels = {
            "Motor": {
                "fineChannelAliases": ["Motor fine"],
                "capabilities": [
                    _generic(0, 9999, "Stop"),
                    {"dmxRange": [10000, 20000], "type": "Rotation", "speedStart": "slow CW", "speedEnd": "fast CW"},
                ],
            }
        }
        entities, universe = _load(channels, ["Motor", "Motor fine"])
        number = _slider(entities, "slow")

        await number.async_set_native_value(100)
        self.assertEqual([20000 >> 8, 20000 & 0xFF], _slots(universe, 2))

        await number.async_set_native_value(1)
        self.assertEqual([10000 >> 8, 10000 & 0xFF], _slots(universe, 2))

        await universe.update_multiple_values({1: 15000 >> 8, 2: 15000 & 0xFF})
        number.available = True
        number.update_value(None)
        self.assertAlmostEqual(50.5, number.native_value, delta=0.1)

    async def test_eight_bit_capabilities_with_a_fine_channel(self):
        channels = {
            "Point": {
                "fineChannelAliases": ["Point fine"],
                "dmxValueResolution": "8bit",
                "capabilities": [_generic(0, 99, "Low"), _generic(100, 255, "High")],
            }
        }
        entities, universe = _load(channels, ["Point", "Point fine"])
        select = _one(entities, DmxSelectEntity)

        await select.async_select_option("High")
        self.assertEqual([100, 0], _slots(universe, 2))

        await universe.update_multiple_values({1: 99, 2: 255})
        self.assertEqual("Low", select.current_option)

    def test_constant_value_spans_both_bytes(self):
        channels = {
            "Point": {
                "fineChannelAliases": ["Point fine"],
                "constant": True,
                "defaultValue": 1000,
                "capabilities": [_generic(0, 5000, "Low"), _generic(5001, 65535, "High")],
            }
        }
        _, universe = _load(channels, ["Point", "Point fine"])
        self.assertEqual([1000 >> 8, 1000 & 0xFF], _slots(universe, 2))


class TestValuesWithoutAnOption(unittest.IsolatedAsyncioTestCase):
    CHANNELS: ClassVar[dict[str, Any]] = {
        "Rotation": {
            "defaultValue": 128,
            "capabilities": [
                _generic(0, 99, "Low"),
                {**_generic(100, 199, "Stop"), "menuClick": "hidden"},
                _generic(200, 255, "High"),
            ],
        }
    }

    async def test_hidden_capability_keeps_the_current_option(self):
        entities, universe = _load(self.CHANNELS, ["Rotation"])
        select = _one(entities, DmxSelectEntity)
        self.assertEqual("Low", select.current_option)

        await universe.update_multiple_values({1: 220})
        self.assertEqual("High", select.current_option)

        await universe.update_multiple_values({1: 150})
        self.assertEqual("High", select.current_option)


class TestEqualNames(unittest.IsolatedAsyncioTestCase):
    def _rotation(self, start: int, end: int) -> dict[str, Any]:
        return {
            "dmxRange": [start, end],
            "type": "Rotation",
            "speedStart": "slow CW",
            "speedEnd": "fast CW",
            "comment": "Spin",
        }

    async def test_every_slider_has_its_own_option_and_identity(self):
        channels = {"Gobo": {"capabilities": [self._rotation(0, 127), self._rotation(128, 255)]}}
        entities, universe = _load(channels, ["Gobo"])

        select = _one(entities, DmxSelectEntity)
        self.assertEqual(["Spin", "Spin 2"], select.options)
        self.assertEqual({"Spin", "Spin 2"}, set(select.capability_entities))

        unique_ids = [e.unique_id for e in entities]
        self.assertEqual(len(unique_ids), len(set(unique_ids)))

        # The first keeps its plain name, and with that its existing unique ID.
        self.assertEqual("X Gobo Spin", select.capability_entities["Spin"].name)

        await universe.update_multiple_values({1: 200})
        self.assertEqual("Spin 2", select.current_option)


class TestChannelsSpreadOverTheMode(unittest.IsolatedAsyncioTestCase):
    CHANNELS: ClassVar[dict[str, Any]] = {
        "Pan": {
            "fineChannelAliases": ["Pan fine"],
            "capability": {"type": "Pan", "angleStart": "0deg", "angleEnd": "540deg"},
        },
        "Tilt": {
            "fineChannelAliases": ["Tilt fine"],
            "capability": {"type": "Tilt", "angleStart": "0deg", "angleEnd": "180deg"},
        },
    }

    async def test_fine_channel_elsewhere_in_the_mode(self):
        entities, universe = _load(self.CHANNELS, ["Pan", "Tilt", "Pan fine", "Tilt fine"])

        indexes = {e.name: e.dmx_indexes for e in entities}
        self.assertEqual({"X Pan": [1, 3], "X Tilt": [2, 4]}, indexes)

        pan = next(e for e in entities if e.name == "X Pan")
        await pan.async_set_native_value(540)
        self.assertEqual([255, 0, 255, 0], _slots(universe, 4))

    def test_fine_channel_before_its_coarse_channel(self):
        entities, _ = _load(self.CHANNELS, ["Pan fine", "Tilt", "Pan"])

        self.assertEqual({"X Pan": [3, 1], "X Tilt": [2]}, {e.name: e.dmx_indexes for e in entities})

    def test_same_channel_in_two_slots_is_two_entities(self):
        channels = {"Speed": {"capability": {"type": "Intensity"}}, "Other": {"capability": {"type": "Intensity"}}}
        entities, _ = _load(channels, ["Speed", "Other", "Speed"])

        numbers = {e.name: e.dmx_indexes for e in entities if isinstance(e, DmxNumberEntity)}
        self.assertEqual({"X Speed": [1], "X Other": [2], "X Speed 2": [3]}, numbers)

        unique_ids = [e.unique_id for e in entities]
        self.assertEqual(len(unique_ids), len(set(unique_ids)))


if __name__ == "__main__":
    unittest.main()
