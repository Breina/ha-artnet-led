"""Test for partial universe bug fix (issue #106)

Tests that partial universe optimization doesn't truncate DMX packets
and lose channel values beyond the changed channels.
"""

from unittest.mock import MagicMock, Mock

import pytest

from custom_components.dmx.io.dmx_io import DmxUniverse
from custom_components.dmx.server import PortAddress


@pytest.mark.asyncio
async def test_partial_universe_includes_all_configured_channels():
    """Test that partial universe packets include all configured channels, not just changed ones.

    This is a regression test for issue #106 where moving heads would return to home position
    after animations because their pan/tilt channels were being excluded from partial packets.
    """
    # Setup mock controller
    mock_controller = Mock()
    mock_controller.send_dmx = MagicMock()

    # Create universe with partial universe enabled
    port_address = PortAddress(0, 0, 1)
    universe = DmxUniverse(
        port_address=port_address,
        controller=mock_controller,
        use_partial_universe=True,
        sacn_server=None,
        sacn_universe=None,
        hass=None,
        max_fps=30,
    )

    # Simulate a moving head fixture with channels 1-10
    # Channels 1-5: Pan (coarse), Pan (fine), Tilt (coarse), Tilt (fine), Speed
    # Channels 6-10: Dimmer, Red, Green, Blue, White
    initial_values = {
        1: 128,  # Pan coarse - middle position
        2: 0,  # Pan fine
        3: 64,  # Tilt coarse - middle position
        4: 0,  # Tilt fine
        5: 100,  # Speed
        6: 255,  # Dimmer - full
        7: 255,  # Red - full
        8: 0,  # Green - off
        9: 0,  # Blue - off
        10: 0,  # White - off
    }

    # Set initial values (simulating fixture setup)
    await universe.update_multiple_values(initial_values, send_update=True)

    # Verify first send (now uses partial universe too - no special "first send" behavior)
    assert mock_controller.send_dmx.call_count == 1
    first_call_data = mock_controller.send_dmx.call_args[0][1]
    # Should be partial universe: up to channel 10, rounded to even = 10 bytes
    assert len(first_call_data) == 10, f"Expected 10 bytes, got {len(first_call_data)}"

    # Verify all initial values are in the packet
    for channel, value in initial_values.items():
        assert first_call_data[channel - 1] == value, f"Channel {channel} should be {value}"

    mock_controller.send_dmx.reset_mock()

    # Now simulate an animation that only changes color channels (7-9)
    # This simulates what happens when a light entity animates colors
    # but leaves pan/tilt channels untouched
    color_update = {
        7: 128,  # Red - dimmed
        8: 64,  # Green - some green
        9: 192,  # Blue - mostly blue
    }

    await universe.update_multiple_values(color_update, send_update=True)

    # Verify second send
    assert mock_controller.send_dmx.call_count == 1
    second_call_data = mock_controller.send_dmx.call_args[0][1]

    # THE BUG FIX: Packet should include ALL channels up to channel 10,
    # not just up to channel 9 (the highest changed channel)
    # Before fix: len would be 9 or 10 (rounded to even)
    # After fix: len should be 10 (includes all configured channels)
    assert (
        len(second_call_data) >= 10
    ), f"Partial universe packet should include all {max(initial_values.keys())} configured channels"

    # Verify pan/tilt channels (1-5) are still present with original values
    # This is the critical test - these channels were NOT in the update,
    # but they should still be included in the packet
    assert second_call_data[0] == 128, "Pan coarse should still be 128"
    assert second_call_data[1] == 0, "Pan fine should still be 0"
    assert second_call_data[2] == 64, "Tilt coarse should still be 64"
    assert second_call_data[3] == 0, "Tilt fine should still be 0"
    assert second_call_data[4] == 100, "Speed should still be 100"

    # Verify color channels have the new values
    assert second_call_data[6] == 128, "Red should be updated to 128"
    assert second_call_data[7] == 64, "Green should be updated to 64"
    assert second_call_data[8] == 192, "Blue should be updated to 192"

    # Verify dimmer and white are still at original values
    assert second_call_data[5] == 255, "Dimmer should still be 255"
    assert second_call_data[9] == 0, "White should still be 0"


@pytest.mark.asyncio
async def test_partial_universe_with_only_low_channels_changed():
    """Test that changing only low channels doesn't truncate high channel values."""
    mock_controller = Mock()
    mock_controller.send_dmx = MagicMock()

    port_address = PortAddress(0, 0, 1)
    universe = DmxUniverse(
        port_address=port_address,
        controller=mock_controller,
        use_partial_universe=True,
        sacn_server=None,
        sacn_universe=None,
        hass=None,
        max_fps=30,
    )

    # Set a high channel value (simulating a fixture at a high DMX address)
    initial_values = {
        1: 100,  # Low channel
        50: 200,  # High channel
    }

    await universe.update_multiple_values(initial_values, send_update=True)
    mock_controller.send_dmx.reset_mock()

    # Update only the low channel
    await universe.update_multiple_values({1: 150}, send_update=True)

    # Verify the packet still includes the high channel
    call_data = mock_controller.send_dmx.call_args[0][1]
    assert len(call_data) >= 50, "Packet should include channel 50"
    assert call_data[0] == 150, "Channel 1 should be updated"
    assert call_data[49] == 200, "Channel 50 should still have original value"


@pytest.mark.asyncio
async def test_partial_universe_packet_size_is_even():
    """Test that partial universe packets are properly rounded to even sizes."""
    mock_controller = Mock()
    mock_controller.send_dmx = MagicMock()

    port_address = PortAddress(0, 0, 1)
    universe = DmxUniverse(
        port_address=port_address,
        controller=mock_controller,
        use_partial_universe=True,
        sacn_server=None,
        sacn_universe=None,
        hass=None,
        max_fps=30,
    )

    # Set an odd number of channels
    await universe.update_multiple_values({1: 100, 2: 150, 3: 200}, send_update=True)
    mock_controller.send_dmx.reset_mock()

    # Update causing the max channel to be odd (3)
    await universe.update_multiple_values({3: 255}, send_update=True)

    call_data = mock_controller.send_dmx.call_args[0][1]
    # Should be rounded up to 4 (even number)
    assert len(call_data) % 2 == 0, "Partial universe packet should have even length"
    assert len(call_data) >= 4, "Should be rounded up from 3 to 4"
