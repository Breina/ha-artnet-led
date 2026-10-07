"""Real pyartnet 2.0 channel/fade/UDP checks, restricted to local loopback."""
import asyncio
import socket

import pyartnet
import pytest
from pyartnet.base.network import UnicastNetworkTarget
from homeassistant.core import State

from custom_components.artnet_led.light import DmxWhite
from test.test_review_regressions import make_light


@pytest.mark.parametrize("bounds", [(2700, 6000), (6000, 2700)])
@pytest.mark.parametrize("kelvin", [2000, 4350, 7000])
@pytest.mark.parametrize("byte_order", ["big", "little"])
@pytest.mark.asyncio
async def test_cct_real_channel_fade_and_udp(bounds, kelvin, byte_order):
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.setblocking(False)
    target = UnicastNetworkTarget.create("127.0.0.1", receiver.getsockname()[1], source_ip="127.0.0.1")
    try:
        async with pyartnet.ArtNetNode(target, refresh_every=0) as node:
            await node.stop_refresh()
            channel = node.add_universe(0).add_channel(1, 2, byte_size=2, byte_order=byte_order)
            entity = make_light(DmxWhite, bounds, channel)
            await entity.restore_state(State(entity.entity_id, "on", {"values": kelvin, "bright": 102}))
            await asyncio.wait_for(channel, timeout=2)
            expected = [0, 26112] if kelvin < 2700 else [26112, 0] if kelvin > 6000 else [26112, 26112]
            if bounds[0] > bounds[1]:
                expected.reverse()
            assert list(channel.get_values()) == expected
            expected_bytes = b"".join(v.to_bytes(2, byte_order) for v in expected)
            async with asyncio.timeout(2):
                while True:
                    packet = await asyncio.get_running_loop().sock_recv(receiver, 1024)
                    assert packet[:8] == b"Art-Net\x00"
                    if packet[8:10] == b"\x00\x50" and packet[18:22] == expected_bytes:
                        break
            await entity.async_turn_off(transition=0)
            await asyncio.wait_for(channel, timeout=2)
            assert list(channel.get_values()) == [0, 0]
    finally:
        receiver.close()
