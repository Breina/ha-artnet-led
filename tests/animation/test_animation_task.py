import asyncio
import time
from unittest.mock import patch

import pytest

from custom_components.dmx.animation import Channel
from custom_components.dmx.animation.engine import AnimationTask, ArtNetAnimationEngine
from custom_components.dmx.entity.light import ChannelType, ChannelMapping
from tests.dmx_test_framework import MockHomeAssistant


@pytest.fixture
def mock_hass():
    """Fixture providing a mock HomeAssistant instance"""
    return MockHomeAssistant()


@pytest.fixture
def sample_channels():
    """Fixture providing sample DMX channels"""
    return {
        'red': Channel(index=1, name="Red", min_value=0, max_value=255),
        'green': Channel(index=2, name="Green", min_value=0, max_value=255),
        'blue': Channel(index=3, name="Blue", min_value=0, max_value=255),
        'dimmer': Channel(index=4, name="Dimmer", min_value=0, max_value=255),
        'color_temp': Channel(index=5, name="ColorTemp", min_value=0, max_value=255),
    }


@pytest.fixture
def sample_channel_mappings(sample_channels):
    """Fixture providing sample channel mappings"""
    return [
        ChannelMapping([1], sample_channels['red'], ChannelType.RED),
        ChannelMapping([2], sample_channels['green'], ChannelType.GREEN),
        ChannelMapping([3], sample_channels['blue'], ChannelType.BLUE),
        ChannelMapping([4], sample_channels['dimmer'], ChannelType.DIMMER),
    ]


@pytest.fixture
def animation_engine(mock_hass):
    """Fixture providing an animation engine instance"""
    return ArtNetAnimationEngine(mock_hass, max_fps=60)


class TestAnimationTask:
    """Test cases for AnimationTask class"""

    def test_animation_task_initialization(self, sample_channel_mappings):
        """Test AnimationTask initialization"""
        current_values = {ChannelType.RED: 0, ChannelType.GREEN: 0}
        desired_values = {ChannelType.RED: 255, ChannelType.GREEN: 128}

        task = AnimationTask(
            animation_id="test_anim",
            channel_mappings=sample_channel_mappings,
            current_values=current_values,
            desired_values=desired_values,
            duration_seconds=2.0,
            min_kelvin=2700,
            max_kelvin=6500
        )

        assert task.animation_id == "test_anim"
        assert task.duration_seconds == 2.0
        assert task.min_kelvin == 2700
        assert task.max_kelvin == 6500
        assert not task.is_cancelled
        assert task.controlled_indexes == {1, 2, 3, 4}

    def test_progress_calculation(self, sample_channel_mappings):
        """Test animation progress calculation"""
        task = AnimationTask(
            animation_id="test_progress",
            channel_mappings=sample_channel_mappings,
            current_values={ChannelType.RED: 0},
            desired_values={ChannelType.RED: 255},
            duration_seconds=1.0
        )

        # Test initial progress
        initial_progress = task.get_progress()
        assert 0.0 <= initial_progress <= 0.1  # Should be near 0

        # Test progress after some time
        time.sleep(0.5)
        mid_progress = task.get_progress()
        assert 0.4 <= mid_progress <= 0.6  # Should be around 0.5

        # Test completed progress
        time.sleep(0.6)
        final_progress = task.get_progress()
        assert final_progress == 1.0

    def test_value_interpolation(self, sample_channel_mappings):
        """Test value interpolation"""
        task = AnimationTask(
            animation_id="test_interp",
            channel_mappings=sample_channel_mappings,
            current_values={ChannelType.RED: 0, ChannelType.GREEN: 100},
            desired_values={ChannelType.RED: 255, ChannelType.GREEN: 200},
            duration_seconds=1.0
        )

        # Test interpolation at different progress points
        assert task.interpolate_value(0, 255, 0.0) == 0
        assert task.interpolate_value(0, 255, 0.5) == 127
        assert task.interpolate_value(0, 255, 1.0) == 255
        assert task.interpolate_value(100, 200, 0.5) == 150

    def test_frame_value_calculation(self, sample_channel_mappings):
        """Test frame value calculation"""
        task = AnimationTask(
            animation_id="test_frame",
            channel_mappings=sample_channel_mappings,
            current_values={ChannelType.RED: 0, ChannelType.GREEN: 100},
            desired_values={ChannelType.RED: 255, ChannelType.GREEN: 50},
            duration_seconds=0.1  # Short duration for immediate testing
        )

        # Get initial frame values
        initial_values = task.calculate_frame_values()
        assert initial_values[ChannelType.RED] <= 50  # Should be low
        assert initial_values[ChannelType.GREEN] >= 75  # Should be closer to 100

        # Wait for completion and test final values
        time.sleep(0.2)
        final_values = task.calculate_frame_values()
        assert final_values[ChannelType.RED] == 255
        assert final_values[ChannelType.GREEN] == 50




if __name__ == "__main__":
    # Example of running tests manually
    async def run_manual_test():
        """Run a basic test manually"""
        hass = MockHomeAssistant()
        engine = ArtNetAnimationEngine(hass, max_fps=30)

        # Create sample channels
        red_channel = Channel(1, "Red")
        green_channel = Channel(2, "Green")

        mappings = [
            ChannelMapping([1], red_channel, ChannelType.RED),
            ChannelMapping([2], green_channel, ChannelType.GREEN),
        ]

        print("Starting animation test...")

        animation_id = engine.create_animation(
            channel_mappings=mappings,
            current_values={ChannelType.RED: 0, ChannelType.GREEN: 0},
            desired_values={ChannelType.RED: 255, ChannelType.GREEN: 128},
            animation_duration_seconds=1.0
        )

        print(f"Created animation: {animation_id}")
        print(f"Active animations: {engine.get_active_animation_count()}")

        # Wait for animation to complete
        await hass.wait_for_all_tasks()

        print("Animation completed!")
        print(f"Final active animations: {engine.get_active_animation_count()}")

    # Uncomment to run manual test
    # asyncio.run(run_manual_test())
