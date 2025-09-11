import asyncio
import os
import sys
from typing import List, Dict, Set
from unittest.mock import MagicMock

import pytest
from homeassistant.helpers.entity import Entity

from custom_components.dmx.entity.number import DmxNumberEntity
from custom_components.dmx.entity.select import DmxSelectEntity
from custom_components.dmx.io.dmx_io import DmxUniverse

# Ensure custom_components can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from custom_components.dmx.entity.light.light_entity import DmxLightEntity


class MockDmxUniverse(DmxUniverse):
    """Mock DMX Universe for testing."""

    def __init__(self):
        # Create a mock hass for animation engine
        mock_hass = MockHomeAssistant()
        super().__init__(None, None, True, hass=mock_hass, max_fps=30)
        self.values = [0] * 512
        self.channel_callbacks = {}

    def register_channel_listener(self, channels, callback):
        """Register callback for channels."""
        if isinstance(channels, int):
            channels = [channels]
        for channel in channels:
            if channel not in self.channel_callbacks:
                self.channel_callbacks[channel] = []
            self.channel_callbacks[channel].append(callback)

    def unregister_channel_listener(self, channels, callback):
        """Unregister callback for channels."""
        if isinstance(channels, int):
            channels = [channels]
        for channel in channels:
            if channel in self.channel_callbacks:
                if callback in self.channel_callbacks[channel]:
                    self.channel_callbacks[channel].remove(callback)

    async def update_value(self, channel, value, send_immediately=False, source: str | None = None):
        """Update single value."""
        if isinstance(channel, int):
            channel = [channel]
        await self.update_multiple_values({ch: value for ch in channel}, source)

    async def update_multiple_values(self, updates: Dict[int, int], source: str | None = None, send_update=True):
        """Update multiple values.
        :param send_update:
        """
        self.set_values(updates)

    def get_values(self):
        """Get all DMX values."""
        return self.values.copy()

    def clear(self):
        """Reset all values to zero."""
        self.values = [0] * 512

    def get_channel_value(self, channel: int) -> int:
        """Get specific channel value."""
        if 1 <= channel <= 512:
            return self.values[channel - 1]
        return 0

    def set_values(self, values: dict):
        """Set DMX values for channels."""
        changed_channels = []
        for channel, value in values.items():
            if 1 <= channel <= 512:
                assert 0 <= value <= 255, f"DMX value {value} for channel {channel} must be between 0 and 255"
                assert isinstance(value, int), f"DMX value {value} for channel {channel} must be an integer"
                self.values[channel - 1] = value
                changed_channels.append(channel)

        called_callbacks = set()
        for channel in changed_channels:
            if channel in self.channel_callbacks:
                for callback in self.channel_callbacks[channel]:
                    if callback in called_callbacks:
                        continue
                    called_callbacks.add(callback)
                    try:
                        callback("Test LOL!")
                    except Exception as e:
                        print(f"Error calling callback for channel {channel}: {e}")


class MockHomeAssistant(MagicMock):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.states = {}
        self.services = {}
        self.config = {}
        self.bus = MagicMock()
        self.bus.async_fire = MagicMock()
        self.bus.async_listen = MagicMock()
        self.bus.async_listen_once = MagicMock()
        self._tasks: Set[asyncio.Task] = set()
        self._task_results = []

    async def async_add_executor_job(self, func, *args, **kwargs):
        return func(*args, **kwargs)

    def async_create_task(self, coro):
        """Create and track async tasks"""
        task = asyncio.create_task(coro)
        self._tasks.add(task)

        # Clean up completed tasks
        def cleanup_task(t):
            self._tasks.discard(t)

        task.add_done_callback(cleanup_task)
        return task

    async def wait_for_all_tasks(self, timeout=5.0):
        """Wait for all created tasks to complete"""
        if self._tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*self._tasks, return_exceptions=True), timeout=timeout)
            except asyncio.TimeoutError:
                # Cancel remaining tasks
                for task in self._tasks:
                    if not task.done():
                        task.cancel()
                raise

    def get_active_task_count(self) -> int:
        """Get number of active tasks"""
        return len([t for t in self._tasks if not t.done()])


def assert_dmx(universe: MockDmxUniverse, channel: int, value: int):
    assert (
        universe.get_channel_value(channel) == value
    ), f"Channel {channel} value is {universe.get_channel_value(channel)}, expected {value}"


def assert_dmx_range(universe: MockDmxUniverse, start_channel: int, values: List[int]):
    """Assert a range of DMX values starting from a specific channel.

    Args:
        universe: MockDmxUniverse to check values from
        start_channel: First channel to check (1-indexed)
        values: List of expected values
    """
    actual_values = []
    mismatched_values = []

    for i, expected_value in enumerate(values):
        channel = start_channel + i
        actual_value = universe.get_channel_value(channel)
        actual_values.append(actual_value)
        if actual_value != expected_value:
            mismatched_values.append((channel, actual_value, expected_value))

    if mismatched_values:
        error_msg = "\nMismatched DMX values:\n"
        for channel, actual, expected in mismatched_values:
            error_msg += f"Channel {channel}: got {actual}, expected {expected}\n"
        error_msg += f"\nFull range comparison (channels {start_channel}-{start_channel + len(values) - 1}):\n"
        error_msg += f"Expected: {values}\n"
        error_msg += f"Actual:   {actual_values}"
        assert False, error_msg


def get_entity_by_name(entities: List[Entity], name: str) -> DmxNumberEntity | DmxSelectEntity | DmxLightEntity:
    found = next((entity for entity in entities if entity._attr_name == name), None)
    assert found, f"{name} entity not found, valid names are: {[e._attr_name for e in entities]}"
    found.hass = MagicMock()
    return found
