"""
Every combination of dimmer, RGB, white and color temperature channels has to get a light entity that only
offers what the fixture can do, and that has its requests end up on the channels that exist.
"""

import asyncio
import json
import tempfile
import unittest
from itertools import product
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import homeassistant.helpers.device_registry
from homeassistant.components.light import ColorMode

from custom_components.dmx.entity.light import ChannelType
from custom_components.dmx.entity.light.light_entity import DmxLightEntity
from custom_components.dmx.fixture import delegator, parser
from custom_components.dmx.io.dmx_io import DmxUniverse

homeassistant.helpers.device_registry.DeviceInfo = MagicMock()

CHANNELS: dict[str, tuple[str, dict[str, str]]] = {
    "D": ("Dimmer", {"type": "Intensity"}),
    "R": ("Red", {"type": "ColorIntensity", "color": "Red"}),
    "G": ("Green", {"type": "ColorIntensity", "color": "Green"}),
    "B": ("Blue", {"type": "ColorIntensity", "color": "Blue"}),
    "W": ("White", {"type": "ColorIntensity", "color": "White"}),
    "C": ("Cold", {"type": "ColorIntensity", "color": "Cold White"}),
    "H": ("Warm", {"type": "ColorIntensity", "color": "Warm White"}),
    "T": ("CCT", {"type": "ColorTemperature", "colorTemperatureStart": "2700K", "colorTemperatureEnd": "6500K"}),
    "V": ("Reversed", {"type": "ColorTemperature", "colorTemperatureStart": "8000K", "colorTemperatureEnd": "2700K"}),
}


def make_light(signature: str, start: int = 1) -> tuple[DmxLightEntity, DmxUniverse]:
    """Make a light from a channel layout, where each letter of the signature is one channel, in that order."""
    fixture_json = {
        "name": signature,
        "shortName": signature,
        "categories": ["Color Changer"],
        "meta": {"authors": ["test"], "createDate": "2026-01-01", "lastModifyDate": "2026-01-01"},
        "physical": {},
        "availableChannels": {CHANNELS[c][0]: {"capability": CHANNELS[c][1]} for c in signature},
        "modes": [{"name": "mode", "channels": [CHANNELS[c][0] for c in signature]}],
    }

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "fixture.json"
        path.write_text(json.dumps(fixture_json))
        fixture = parser.parse(str(path))

    universe = DmxUniverse(None, None, True)
    entities = delegator.create_entities(signature, start, fixture.select_mode("mode"), None, universe)
    light = next(entity for entity in entities if isinstance(entity, DmxLightEntity))
    light.hass = MagicMock()
    return light, universe


def dmx(light: DmxLightEntity, universe: DmxUniverse) -> dict[str, int]:
    """Read the DMX output of each of the light's channels, keyed by the letter used in the signature."""
    letters = {
        ChannelType.DIMMER: "D",
        ChannelType.RED: "R",
        ChannelType.GREEN: "G",
        ChannelType.BLUE: "B",
        ChannelType.COLD_WHITE: "C",
        ChannelType.WARM_WHITE: "W",
        ChannelType.COLOR_TEMPERATURE: "T",
    }
    return {
        letters[channel_type]: universe.get_channel_value(mapping.dmx_indexes[0])
        for channel_type, mapping in light.channel_map.items()
    }


def turn_on(light: DmxLightEntity, **kwargs: Any) -> None:
    asyncio.run(light.async_turn_on(**kwargs))


def turn_off(light: DmxLightEntity) -> None:
    asyncio.run(light.async_turn_off())


class ConfigurationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        for target in ("async_write_ha_state", "async_schedule_update_ha_state"):
            patcher = patch(f"homeassistant.helpers.entity.Entity.{target}")
            patcher.start()
            self.addCleanup(patcher.stop)


class TestColorModes(ConfigurationTestCase):
    def test_supported_color_modes(self) -> None:
        expected = {
            "D": {ColorMode.BRIGHTNESS},
            "W": {ColorMode.BRIGHTNESS},
            "C": {ColorMode.BRIGHTNESS},
            "DW": {ColorMode.BRIGHTNESS},
            "CH": {ColorMode.COLOR_TEMP},
            "DCH": {ColorMode.COLOR_TEMP},
            "T": {ColorMode.COLOR_TEMP},
            "DT": {ColorMode.COLOR_TEMP},
            "WT": {ColorMode.COLOR_TEMP},
            "DWT": {ColorMode.COLOR_TEMP},
            "CHT": {ColorMode.COLOR_TEMP},
            "RGB": {ColorMode.RGB},
            "DRGB": {ColorMode.RGB},
            "RGBW": {ColorMode.RGBW},
            "RGBC": {ColorMode.RGBW},
            "DRGBW": {ColorMode.RGBW},
            "RGBCH": {ColorMode.RGBWW},
            "DRGBCH": {ColorMode.RGBWW},
            "DRGBCHT": {ColorMode.RGBWW},
            "RGBT": {ColorMode.RGB},
            "DRGBT": {ColorMode.COLOR_TEMP, ColorMode.RGB},
            "RGBWT": {ColorMode.COLOR_TEMP, ColorMode.RGBW},
            "RGBCT": {ColorMode.COLOR_TEMP, ColorMode.RGBW},
            "DRGBWT": {ColorMode.COLOR_TEMP, ColorMode.RGBW},
        }
        for signature, modes in expected.items():
            with self.subTest(signature):
                light, _ = make_light(signature)
                self.assertEqual(modes, light.supported_color_modes)
                self.assertIn(light.color_mode, modes)

    def test_every_combination_survives_every_kind_of_request(self) -> None:
        requests: list[dict[str, Any]] = [
            {},
            {"brightness": 128},
            {"rgb_color": (255, 128, 0)},
            {"rgbw_color": (1, 2, 3, 4)},
            {"rgbww_color": (1, 2, 3, 4, 5)},
            {"color_temp_kelvin": 3000},
            {"color_temp_kelvin": 1000, "brightness": 10},
            {"color_temp_kelvin": 20000},
        ]
        options = product(["", "D"], ["", "RGB"], ["", "W", "C", "H", "CH"], ["", "T", "V"])
        for signature in ("".join(parts) for parts in options):
            if not signature:
                continue
            light, _ = make_light(signature)
            for request in requests:
                with self.subTest(signature=signature, request=request):
                    turn_on(light, **request)
                    turn_off(light)
                    turn_on(light)
                    self.assertTrue(light.state_attributes is not None)


class TestRgbWithColorTemperature(ConfigurationTestCase):
    """Issue 132: Dimmer/CCT/R/G/B, where the fixture itself ignores CCT for as long as there's RGB output."""

    def setUp(self) -> None:
        super().setUp()
        self.light, self.universe = make_light("DTRGB")

    def assert_dmx(self, **expected: int) -> None:
        self.assertEqual(expected, dmx(self.light, self.universe))

    def test_kelvin_range_comes_from_the_fixture(self) -> None:
        self.assertEqual(2700, self.light.min_color_temp_kelvin)
        self.assertEqual(6500, self.light.max_color_temp_kelvin)

    def test_color_temperature_reaches_the_cct_channel(self) -> None:
        turn_on(self.light, brightness=255, color_temp_kelvin=6500)
        self.assert_dmx(D=255, T=255, R=0, G=0, B=0)
        self.assertEqual(ColorMode.COLOR_TEMP, self.light.color_mode)
        self.assertEqual(6500, self.light.color_temp_kelvin)

        turn_on(self.light, color_temp_kelvin=2700)
        self.assert_dmx(D=255, T=0, R=0, G=0, B=0)
        self.assertEqual(2700, self.light.color_temp_kelvin)

    def test_color_is_written_as_requested(self) -> None:
        turn_on(self.light, brightness=255, rgb_color=(255, 128, 128))
        self.assert_dmx(D=255, T=0, R=255, G=128, B=128)
        self.assertEqual(ColorMode.RGB, self.light.color_mode)
        self.assertEqual((255, 128, 128), self.light.rgb_color)

    def test_white_clears_the_color(self) -> None:
        turn_on(self.light, brightness=255, rgb_color=(255, 0, 0))
        turn_on(self.light, color_temp_kelvin=4600)
        self.assert_dmx(D=255, T=128, R=0, G=0, B=0)
        self.assertEqual(ColorMode.COLOR_TEMP, self.light.color_mode)

    def test_turning_on_while_white_does_not_bring_the_color_back(self) -> None:
        turn_on(self.light, brightness=255, rgb_color=(255, 128, 0))
        turn_on(self.light, color_temp_kelvin=4600)
        turn_on(self.light)
        self.assert_dmx(D=255, T=128, R=0, G=0, B=0)
        self.assertEqual(ColorMode.COLOR_TEMP, self.light.color_mode)

    def test_off_and_on_keep_the_color(self) -> None:
        turn_on(self.light, brightness=200, rgb_color=(255, 0, 0))
        turn_off(self.light)
        self.assert_dmx(D=0, T=0, R=255, G=0, B=0)
        self.assertFalse(self.light.is_on)

        turn_on(self.light)
        self.assert_dmx(D=200, T=255, R=255, G=0, B=0)
        self.assertEqual(ColorMode.RGB, self.light.color_mode)

    def test_off_and_on_keep_the_white(self) -> None:
        turn_on(self.light, brightness=200, rgb_color=(255, 0, 0))
        turn_on(self.light, color_temp_kelvin=4600)
        turn_off(self.light)
        turn_on(self.light)
        self.assert_dmx(D=200, T=128, R=0, G=0, B=0)
        self.assertEqual(ColorMode.COLOR_TEMP, self.light.color_mode)

    def test_incoming_dmx_switches_the_mode(self) -> None:
        turn_on(self.light, brightness=255, color_temp_kelvin=4600)

        asyncio.run(self.universe.receive_values({3: 200}, "sender"))
        self.assertEqual(ColorMode.RGB, self.light.color_mode)
        self.assertEqual((200, 0, 0), self.light.rgb_color)

        asyncio.run(self.universe.receive_values({3: 0}, "sender"))
        self.assertEqual(ColorMode.COLOR_TEMP, self.light.color_mode)

        turn_on(self.light)
        self.assert_dmx(D=255, T=128, R=0, G=0, B=0)

    def test_cct_beyond_range_is_clamped(self) -> None:
        turn_on(self.light, brightness=255, color_temp_kelvin=1000)
        self.assert_dmx(D=255, T=0, R=0, G=0, B=0)
        turn_on(self.light, color_temp_kelvin=20000)
        self.assert_dmx(D=255, T=255, R=0, G=0, B=0)

    def test_restore_after_restart(self) -> None:
        for attributes, mode, rgb, kelvin in (
            ({"color_mode": "rgb", "brightness": 200, "rgb_color": (255, 0, 0)}, ColorMode.RGB, (255, 0, 0), 3000),
            (
                # Home Assistant derives this rgb_color from the color temperature: it's not on the RGB channels.
                {
                    "color_mode": "color_temp",
                    "brightness": 200,
                    "rgb_color": (255, 200, 150),
                    "color_temp_kelvin": 4600,
                },
                ColorMode.COLOR_TEMP,
                (0, 0, 0),
                4600,
            ),
            (
                # Saved before this fixture had two modes. Only rgb_color is derived, the rgbww_color was output.
                {"color_mode": "rgbww", "brightness": 200, "rgb_color": (9, 8, 7), "rgbww_color": (10, 0, 0, 255, 255)},
                ColorMode.RGB,
                (10, 0, 0),
                3000,
            ),
            (
                {"color_mode": "rgbww", "brightness": 200, "rgb_color": (9, 8, 7), "rgbww_color": (0, 0, 0, 255, 255)},
                ColorMode.COLOR_TEMP,
                (0, 0, 0),
                3000,
            ),
        ):
            with self.subTest(attributes=attributes):
                light, universe = make_light("DTRGB")
                last_state = MagicMock(state="on", attributes=attributes)
                with (
                    patch("homeassistant.helpers.restore_state.RestoreEntity.async_added_to_hass", AsyncMock()),
                    patch.object(DmxLightEntity, "async_get_last_state", AsyncMock(return_value=last_state)),
                ):
                    asyncio.run(light.async_added_to_hass())

                self.assertEqual(mode, light.color_mode)
                self.assertEqual(rgb, light._state.rgb)
                self.assertEqual(kelvin, light._state.color_temp_kelvin)

                turn_on(light)
                self.assertEqual(rgb, tuple(dmx(light, universe)[c] for c in "RGB"))
                if mode == ColorMode.COLOR_TEMP and "color_temp_kelvin" in attributes:
                    self.assertEqual(128, dmx(light, universe)["T"])

    def test_without_a_dimmer_it_is_plain_rgb(self) -> None:
        light, universe = make_light("TRGB")
        self.assertEqual({ColorMode.RGB}, light.supported_color_modes)
        self.assertNotIn(ChannelType.COLOR_TEMPERATURE, light.channel_map)

        turn_on(light, rgb_color=(255, 128, 128))
        self.assertEqual({"R": 255, "G": 128, "B": 128}, dmx(light, universe))
        turn_off(light)
        self.assertEqual({"R": 0, "G": 0, "B": 0}, dmx(light, universe))
        # CCT is left alone for its number entity, rather than being written by the light.
        self.assertFalse(universe.is_channel_set(1))


class TestRgbWhiteWithColorTemperature(ConfigurationTestCase):
    """ARRI, Lupo, Robe: a white channel for intensity, and a CCT channel for its color temperature."""

    def test_with_dimmer(self) -> None:
        light, universe = make_light("DTRGBW")

        turn_on(light, brightness=128, color_temp_kelvin=4600)
        self.assertEqual({"D": 128, "T": 128, "R": 0, "G": 0, "B": 0, "W": 255}, dmx(light, universe))
        self.assertEqual(ColorMode.COLOR_TEMP, light.color_mode)
        self.assertEqual(128, light.brightness)

        turn_on(light, rgbw_color=(255, 0, 0, 0))
        self.assertEqual({"D": 128, "T": 128, "R": 255, "G": 0, "B": 0, "W": 0}, dmx(light, universe))
        self.assertEqual(ColorMode.RGBW, light.color_mode)
        self.assertEqual((255, 0, 0, 0), light.rgbw_color)

        turn_off(light)
        turn_on(light)
        self.assertEqual({"D": 128, "T": 128, "R": 255, "G": 0, "B": 0, "W": 0}, dmx(light, universe))

    def test_without_dimmer(self) -> None:
        light, universe = make_light("TRGBW")

        turn_on(light, brightness=128, color_temp_kelvin=4600)
        self.assertEqual({"T": 128, "R": 0, "G": 0, "B": 0, "W": 128}, dmx(light, universe))
        self.assertEqual(128, light.brightness)

        turn_on(light, brightness=64)
        self.assertEqual({"T": 128, "R": 0, "G": 0, "B": 0, "W": 64}, dmx(light, universe))
        self.assertEqual(64, light.brightness)

        turn_off(light)
        self.assertEqual({"T": 128, "R": 0, "G": 0, "B": 0, "W": 0}, dmx(light, universe))
        self.assertFalse(light.is_on)

        turn_on(light)
        self.assertEqual({"T": 128, "R": 0, "G": 0, "B": 0, "W": 64}, dmx(light, universe))
        self.assertTrue(light.is_on)


class TestReversedColorTemperature(ConfigurationTestCase):
    """Profiles may run from cold to warm: 8000K at DMX 0 and 2700K at DMX 255."""

    def test_on_its_own(self) -> None:
        light, universe = make_light("DV")
        self.assertEqual(2700, light.min_color_temp_kelvin)
        self.assertEqual(8000, light.max_color_temp_kelvin)

        turn_on(light, brightness=255, color_temp_kelvin=8000)
        self.assertEqual({"D": 255, "T": 0}, dmx(light, universe))
        self.assertEqual(8000, light.color_temp_kelvin)

        turn_on(light, color_temp_kelvin=2700)
        self.assertEqual({"D": 255, "T": 255}, dmx(light, universe))
        self.assertEqual(2700, light.color_temp_kelvin)

    def test_next_to_rgb(self) -> None:
        light, universe = make_light("DVRGB")
        self.assertEqual(2700, light.min_color_temp_kelvin)

        turn_on(light, brightness=255, color_temp_kelvin=8000)
        self.assertEqual({"D": 255, "T": 0, "R": 0, "G": 0, "B": 0}, dmx(light, universe))

    def test_incoming_dmx(self) -> None:
        light, universe = make_light("DV")
        asyncio.run(universe.receive_values({1: 255, 2: 255}, "sender"))
        self.assertEqual(2700, light.color_temp_kelvin)
        asyncio.run(universe.receive_values({2: 0}, "sender"))
        self.assertEqual(8000, light.color_temp_kelvin)


class TestOnlyTheFirstColorTemperatureChannelCounts(ConfigurationTestCase):
    def test_second_one_stays_a_number(self) -> None:
        # Kelvin Epos: CCT, followed by a "RGB device white point" with a different range
        light, universe = make_light("DTVRGB")
        self.assertEqual(2700, light.min_color_temp_kelvin)
        self.assertEqual(6500, light.max_color_temp_kelvin)

        turn_on(light, brightness=255, color_temp_kelvin=6500)
        self.assertEqual(255, universe.get_channel_value(2))
        self.assertFalse(universe.is_channel_set(3))


class TestSingleWhite(ConfigurationTestCase):
    def test_cold_white_next_to_rgb_is_the_white_channel(self) -> None:
        for signature in ("RGBC", "RGBW", "RGBH"):
            with self.subTest(signature):
                light, universe = make_light(signature)

                turn_on(light)
                self.assertEqual({"R": 255, "G": 255, "B": 255, "W": 255}, dmx(light, universe))

                turn_on(light, rgbw_color=(0, 0, 0, 200))
                self.assertEqual({"R": 0, "G": 0, "B": 0, "W": 200}, dmx(light, universe))
                self.assertEqual(200, light.brightness)

                turn_off(light)
                self.assertEqual({"R": 0, "G": 0, "B": 0, "W": 0}, dmx(light, universe))
                turn_on(light)
                self.assertEqual({"R": 0, "G": 0, "B": 0, "W": 200}, dmx(light, universe))

    def test_brightness_without_dimmer(self) -> None:
        for signature in ("W", "C", "H"):
            with self.subTest(signature):
                light, universe = make_light(signature)

                turn_on(light, brightness=128)
                self.assertEqual({"W": 128}, dmx(light, universe))
                self.assertEqual(128, light.brightness)

                turn_on(light)
                self.assertEqual({"W": 128}, dmx(light, universe))

                turn_off(light)
                self.assertEqual({"W": 0}, dmx(light, universe))

                turn_on(light, brightness=60)
                self.assertEqual({"W": 60}, dmx(light, universe))

    def test_with_color_temperature_without_dimmer(self) -> None:
        light, universe = make_light("WT")

        turn_on(light, brightness=128)
        self.assertEqual(128, dmx(light, universe)["W"])
        self.assertEqual(128, light.brightness)

        turn_on(light, brightness=100, color_temp_kelvin=4600)
        self.assertEqual({"W": 100, "T": 128}, dmx(light, universe))
        self.assertEqual(100, light.brightness)

        turn_off(light)
        turn_on(light, color_temp_kelvin=6500)
        self.assertEqual({"W": 100, "T": 255}, dmx(light, universe))

    def test_with_color_temperature_and_dimmer(self) -> None:
        light, universe = make_light("DWT")

        turn_on(light, brightness=128, color_temp_kelvin=4600)
        self.assertEqual({"D": 128, "W": 255, "T": 128}, dmx(light, universe))


class TestRequestsBecomeVisible(ConfigurationTestCase):
    def test_brightness_on_never_written_color_channels(self) -> None:
        for signature, expected in (
            ("DRGB", {"D": 128, "R": 255, "G": 255, "B": 255}),
            ("DRGBW", {"D": 128, "R": 255, "G": 255, "B": 255, "W": 255}),
            ("DW", {"D": 128, "W": 255}),
            ("DCH", {"D": 128, "C": 255, "W": 255}),
            ("D", {"D": 128}),
        ):
            with self.subTest(signature):
                light, universe = make_light(signature)
                turn_on(light, brightness=128)
                self.assertEqual(expected, dmx(light, universe))

    def test_color_on_a_dimmer_that_is_off(self) -> None:
        light, universe = make_light("DRGB")

        turn_on(light, rgb_color=(255, 0, 0))
        self.assertEqual({"D": 255, "R": 255, "G": 0, "B": 0}, dmx(light, universe))

        turn_on(light, brightness=100)
        turn_off(light)
        self.assertFalse(light.is_on)

        turn_on(light, rgb_color=(0, 255, 0))
        self.assertEqual({"D": 100, "R": 0, "G": 255, "B": 0}, dmx(light, universe))
        self.assertTrue(light.is_on)

    def test_color_temperature_on_a_dimmer_that_is_off(self) -> None:
        light, universe = make_light("DT")
        turn_on(light, color_temp_kelvin=4600)
        self.assertEqual({"D": 255, "T": 128}, dmx(light, universe))

    def test_brightness_after_off_without_dimmer(self) -> None:
        for signature, expected in (
            ("RGB", {"R": 60, "G": 0, "B": 0}),
            ("RGBW", {"R": 60, "G": 0, "B": 0, "W": 0}),
            ("RGBCH", {"R": 60, "G": 0, "B": 0, "C": 0, "W": 0}),
        ):
            with self.subTest(signature):
                light, universe = make_light(signature)
                color = {"RGB": {"rgb_color": (255, 0, 0)}, "RGBW": {"rgbw_color": (255, 0, 0, 0)}}
                turn_on(light, **color.get(signature, {"rgbww_color": (255, 0, 0, 0, 0)}))
                turn_off(light)

                turn_on(light, brightness=60)
                self.assertEqual(expected, dmx(light, universe))
                self.assertEqual(60, light.brightness)

    def test_color_temperature_after_off_without_dimmer(self) -> None:
        light, universe = make_light("CH")
        turn_on(light, brightness=128, color_temp_kelvin=6500)
        turn_off(light)

        turn_on(light, color_temp_kelvin=2700)
        self.assertGreater(dmx(light, universe)["W"], 0)
        self.assertTrue(light.is_on)


class TestBrightnessIsAppliedOnce(ConfigurationTestCase):
    def test_color_with_brightness_without_dimmer(self) -> None:
        light, universe = make_light("RGB")
        turn_on(light, rgb_color=(255, 0, 0), brightness=128)
        self.assertEqual({"R": 128, "G": 0, "B": 0}, dmx(light, universe))
        self.assertEqual(128, light.brightness)

    def test_color_with_brightness_with_dimmer(self) -> None:
        light, universe = make_light("DRGB")
        turn_on(light, rgb_color=(255, 0, 0), brightness=128)
        self.assertEqual({"D": 128, "R": 255, "G": 0, "B": 0}, dmx(light, universe))

    def test_color_temperature_with_dimmer_and_whites(self) -> None:
        light, universe = make_light("DCH")
        turn_on(light, color_temp_kelvin=6500, brightness=128)
        self.assertEqual({"D": 128, "C": 255, "W": 0}, dmx(light, universe))

    def test_color_temperature_with_whites_and_cct(self) -> None:
        light, universe = make_light("DCHT")
        turn_on(light, color_temp_kelvin=6500, brightness=128)
        self.assertEqual({"D": 128, "C": 255, "W": 0, "T": 255}, dmx(light, universe))


class TestNoOutputChannels(ConfigurationTestCase):
    def test_color_temperature_only(self) -> None:
        light, universe = make_light("T")

        turn_on(light, color_temp_kelvin=4600)
        self.assertEqual({"T": 128}, dmx(light, universe))
        self.assertTrue(light.is_on)

        turn_off(light)
        self.assertFalse(light.is_on)

        turn_on(light)
        self.assertTrue(light.is_on)
        self.assertEqual({"T": 128}, dmx(light, universe))
        self.assertEqual(255, light.brightness)


class TestRestoreAfterRestart(ConfigurationTestCase):
    @staticmethod
    def restore(signature: str, attributes: dict[str, Any]) -> tuple[DmxLightEntity, DmxUniverse]:
        light, universe = make_light(signature)
        last_state = MagicMock(state="on", attributes=attributes)
        with (
            patch("homeassistant.helpers.restore_state.RestoreEntity.async_added_to_hass", AsyncMock()),
            patch.object(DmxLightEntity, "async_get_last_state", AsyncMock(return_value=last_state)),
        ):
            asyncio.run(light.async_added_to_hass())
        return light, universe

    def test_rgbw_comes_back_with_its_white(self) -> None:
        light, universe = self.restore(
            "DRGBW",
            {"color_mode": "rgbw", "brightness": 200, "rgb_color": (250, 240, 230), "rgbw_color": (10, 20, 30, 40)},
        )
        self.assertEqual((10, 20, 30, 40), light.rgbw_color)

        turn_on(light)
        self.assertEqual({"D": 200, "R": 10, "G": 20, "B": 30, "W": 40}, dmx(light, universe))

    def test_rgbww_comes_back_with_its_whites(self) -> None:
        light, universe = self.restore(
            "RGBCH",
            {
                "color_mode": "rgbww",
                "brightness": 50,
                "rgb_color": (250, 240, 230),
                "rgbww_color": (10, 20, 30, 40, 50),
            },
        )
        self.assertEqual((10, 20, 30, 40, 50), light.rgbww_color)

        turn_on(light)
        self.assertEqual({"R": 10, "G": 20, "B": 30, "C": 40, "W": 50}, dmx(light, universe))

    def test_color_temperature_comes_back_on_its_channel(self) -> None:
        light, universe = self.restore("DT", {"color_mode": "color_temp", "brightness": 200, "color_temp_kelvin": 4600})
        turn_on(light)
        self.assertEqual({"D": 200, "T": 128}, dmx(light, universe))

    def test_single_white_comes_back_at_its_brightness(self) -> None:
        light, universe = self.restore("W", {"color_mode": "brightness", "brightness": 80})
        turn_on(light)
        self.assertEqual({"W": 80}, dmx(light, universe))

    def test_cold_and_warm_white_come_back_from_their_temperature(self) -> None:
        light, universe = self.restore("CH", {"color_mode": "color_temp", "brightness": 100, "color_temp_kelvin": 6500})
        turn_on(light)
        self.assertEqual({"C": 100, "W": 0}, dmx(light, universe))


class TestTransitions(ConfigurationTestCase):
    def test_last_values_are_those_of_the_transition_target(self) -> None:
        light, _ = make_light("DRGB")
        engine = MagicMock()
        engine.create_animation.return_value = "animation"
        light._controller.animation_engine = engine

        turn_on(light, brightness=255, rgb_color=(255, 0, 0))
        turn_on(light, rgb_color=(0, 255, 0), transition=1.0)
        self.assertEqual((0, 255, 0), light._state.last_rgb)
        self.assertTrue(light._state._preserve_last_values)

        # Frames of the animation don't leave a trace.
        light._state.apply_channel_update(ChannelType.RED, 100)
        self.assertEqual((0, 255, 0), light._state.last_rgb)

    def test_white_is_the_target_on_rgb_with_color_temperature(self) -> None:
        light, _ = make_light("DTRGB")
        engine = MagicMock()
        engine.create_animation.return_value = "animation"
        light._controller.animation_engine = engine

        turn_on(light, brightness=255, rgb_color=(255, 0, 0))
        turn_on(light, color_temp_kelvin=4600, transition=1.0)
        self.assertEqual((0, 0, 0), light._state.last_rgb)
        self.assertEqual(ColorMode.COLOR_TEMP, light.color_mode)

        desired = engine.create_animation.call_args.kwargs["desired_values"]
        self.assertEqual(0, desired[ChannelType.RED])
        self.assertAlmostEqual(127.5, desired[ChannelType.COLOR_TEMPERATURE], delta=1)


if __name__ == "__main__":
    unittest.main()
