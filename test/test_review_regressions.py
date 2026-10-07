"""Review 5443709090 regressions; real HA imports, isolated output boundary."""
from array import array
from unittest.mock import Mock

import pytest
from homeassistant.core import State

from custom_components.artnet_led.light import DmxRGBWW, DmxWhite
from custom_components.artnet_led.util.channel_switch import clamp_color_temp_kelvin, to_values


BOUNDS = [(2700, 6000), (6000, 2700)]


def make_light(cls, bounds=(2700, 6000), channel=None):
    channel = channel if channel is not None else Mock()
    entity = cls(name="Review test", unique_id="local-review-test", channel=channel,
                 transition=0, channel_size="16bit", type=cls.CONF_TYPE,
                 min_temp=f"{bounds[0]}K", max_temp=f"{bounds[1]}K")
    # No entity is registered in HA; intercept only HA state scheduling.
    entity.async_schedule_update_ha_state = Mock()
    return entity


@pytest.mark.parametrize("bounds", BOUNDS)
@pytest.mark.parametrize("value, expected", [(-1, 2700), (2000, 2700), (2700, 2700),
    (4350.5, 4350.5), (6000, 6000), (7000, 6000)])
def test_clamp_order_independent(bounds, value, expected):
    assert clamp_color_temp_kelvin(value, *bounds) == expected


def test_clamp_equal_bounds():
    assert clamp_color_temp_kelvin(4000, 2700, 2700) == 2700


@pytest.mark.parametrize("bounds", BOUNDS)
@pytest.mark.parametrize("value", [2000, 2700, 4350, 6000, 7000])
@pytest.mark.parametrize("brightness", [0, 1, 102, 255])
@pytest.mark.parametrize("is_on", [False, True])
def test_cct_16bit_direction_and_range(bounds, value, brightness, is_on, caplog):
    # At the midpoint this integration normalizes BOTH channels to brightness.
    if value <= 2700:
        expected = [0, brightness * 256]
    elif value >= 6000:
        expected = [brightness * 256, 0]
    else:
        expected = [brightness * 256, brightness * 256]
    if bounds[0] > bounds[1]:
        expected.reverse()
    if not is_on:
        expected = [0, 0]
    assert to_values("ch", 256, is_on, brightness, color_temp_kelvin=value,
                     min_kelvin=bounds[0], max_kelvin=bounds[1]) == expected
    assert "isn't within bound" not in caplog.text


@pytest.mark.parametrize("cls", [DmxWhite, DmxRGBWW])
@pytest.mark.parametrize("bounds", BOUNDS)
@pytest.mark.parametrize("value, expected", [(2000, 2700), (4350, 4350), (7000, 6000)])
@pytest.mark.parametrize("state", ["on", "off"])
@pytest.mark.asyncio
async def test_restore_clamps_entity_state(cls, bounds, value, expected, state):
    entity = make_light(cls, bounds)
    values = value if cls is DmxWhite else (10, 20, 30, 40, 50, value)
    old = State(entity.entity_id, state, {"values": values, "bright": 102})
    await entity.restore_state(old)
    assert entity.color_temp_kelvin == expected
    assert entity.brightness == 102
    assert old.attributes["values"] == values  # Restore must not mutate its input.
    if cls is DmxRGBWW:
        assert entity.rgbww_color == (10, 20, 30, 40, 50)
    assert entity.channel.set_fade.call_count == (state == "on")


@pytest.mark.parametrize("cls", [DmxWhite, DmxRGBWW])
@pytest.mark.parametrize("bounds", BOUNDS)
@pytest.mark.parametrize("value, expected", [(2000, 2700), (4350, 4350), (7000, 6000)])
@pytest.mark.asyncio
async def test_service_clamps_entity_state(cls, bounds, value, expected, caplog):
    entity = make_light(cls, bounds)
    await entity.async_turn_on(color_temp_kelvin=value, brightness=102, transition=0)
    assert entity.color_temp_kelvin == expected
    assert entity.is_on
    targets = entity.channel.set_fade.call_args.args[0]
    assert all(0 <= v <= 65535 for v in targets)
    assert "isn't within bound" not in caplog.text


@pytest.mark.parametrize("bounds, expected", [((2700, 6500), 4600),
    ((2700, 6000), 4350), ((6000, 2700), 4350)])
def test_rgbww_initial_midpoint(bounds, expected):
    assert make_light(DmxRGBWW, bounds).color_temp_kelvin == expected


@pytest.mark.parametrize("state", ["on", "off"])
@pytest.mark.parametrize("container", [list, tuple])
@pytest.mark.asyncio
async def test_rgbww_restore_none_after_incoming_dmx(state, container):
    previous = make_light(DmxRGBWW)
    previous._update_values(array("i", [1024, 2048, 3072, 4096, 5120]))
    assert previous.color_temp_kelvin is None
    values = container(previous._vals)
    restored = make_light(DmxRGBWW)
    await restored.restore_state(State(restored.entity_id, state,
                                      {"values": values, "bright": previous.brightness}))
    assert restored.color_temp_kelvin is None
    assert restored.rgbww_color == previous.rgbww_color
    assert list(values) == list(previous._vals)


@pytest.mark.parametrize("cls", [DmxWhite, DmxRGBWW])
@pytest.mark.asyncio
async def test_missing_restore_values_keeps_default(cls):
    entity = make_light(cls)
    await entity.restore_state(State(entity.entity_id, "off", {"bright": 102}))
    assert entity.color_temp_kelvin == 4350


@pytest.mark.xfail(strict=True, raises=TypeError,
                   reason="Existing RGBWW tuple mutation after incoming DMX; intentionally out of scope")
@pytest.mark.asyncio
async def test_known_rgbww_tuple_mutation_not_silently_fixed():
    entity = make_light(DmxRGBWW)
    entity._update_values(array("i", [1024, 2048, 3072, 4096, 5120]))
    await entity.async_turn_on(color_temp_kelvin=4350)
