import asyncio
from unittest.mock import patch

import pytest

from custom_components.dmx.animation import Channel
from custom_components.dmx.animation.engine import DmxAnimationEngine
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
    return DmxAnimationEngine(mock_hass, max_fps=10)


class TestDmxAnimationEngine:
    """Test cases for DmxAnimationEngine class"""

    def test_engine_initialization(self, mock_hass):
        """Test animation engine initialization"""
        engine = DmxAnimationEngine(mock_hass, max_fps=30)

        assert engine.hass == mock_hass
        assert engine.max_fps == 30
        assert engine.frame_interval == 1.0 / 30
        assert len(engine.active_animations) == 0
        assert len(engine.dmx_channel_owners) == 0

    def test_animation_id_generation(self, animation_engine):
        """Test unique animation ID generation"""
        id1 = animation_engine._generate_animation_id()
        id2 = animation_engine._generate_animation_id()

        assert id1 != id2
        assert id1.startswith("anim_")
        assert id2.startswith("anim_")

    @pytest.mark.asyncio
    async def test_create_single_animation(self, animation_engine, sample_channel_mappings):
        """Test creating a single animation"""
        current_values = {ChannelType.RED: 0, ChannelType.GREEN: 0}
        desired_values = {ChannelType.RED: 255, ChannelType.GREEN: 128}

        with patch('builtins.print') as mock_print:  # Capture dummy output
            animation_id = animation_engine.create_animation(
                channel_mappings=sample_channel_mappings,
                current_values=current_values,
                desired_values=desired_values,
                animation_duration_seconds=0.1
            )

        # Verify animation was created
        assert animation_id in animation_engine.active_animations
        assert len(animation_engine.active_animations) == 1

        # Verify channel ownership
        expected_channels = {1, 2, 3, 4}
        for channel in expected_channels:
            assert animation_engine.dmx_channel_owners[channel] == animation_id

        # Wait for animation to complete
        await animation_engine.hass.wait_for_all_tasks(timeout=2.0)

        # Verify cleanup
        assert len(animation_engine.active_animations) == 0
        assert len(animation_engine.dmx_channel_owners) == 0

        # Verify frame output was called
        assert mock_print.called

    @pytest.mark.asyncio
    async def test_conflicting_animations(self, animation_engine, sample_channel_mappings):
        """Test that conflicting animations are cancelled"""
        current_values = {ChannelType.RED: 0}
        desired_values1 = {ChannelType.RED: 255}
        desired_values2 = {ChannelType.RED: 128}

        with patch('builtins.print'):  # Suppress output
            # Start first animation
            animation_id1 = animation_engine.create_animation(
                channel_mappings=sample_channel_mappings,
                current_values=current_values,
                desired_values=desired_values1,
                animation_duration_seconds=1.0
            )

            # Verify first animation is active
            assert len(animation_engine.active_animations) == 1
            assert animation_id1 in animation_engine.active_animations

            # Start conflicting animation
            animation_id2 = animation_engine.create_animation(
                channel_mappings=sample_channel_mappings,
                current_values=current_values,
                desired_values=desired_values2,
                animation_duration_seconds=0.5
            )

            # Wait a moment for cancellation to process
            await asyncio.sleep(0.05)

            # Verify only second animation is active
            assert len(animation_engine.active_animations) == 1
            assert animation_id2 in animation_engine.active_animations
            assert animation_id1 not in animation_engine.active_animations

        # Wait for remaining animation to complete
        await animation_engine.hass.wait_for_all_tasks(timeout=2.0)

    @pytest.mark.asyncio
    async def test_partial_channel_conflict(self, animation_engine, sample_channels):
        """Test animations with partial channel conflicts"""
        # Create mappings for different channel sets
        rgb_mappings = [
            ChannelMapping([1], sample_channels['red'], ChannelType.RED),
            ChannelMapping([2], sample_channels['green'], ChannelType.GREEN),
            ChannelMapping([3], sample_channels['blue'], ChannelType.BLUE),
        ]

        dimmer_mappings = [
            ChannelMapping([4], sample_channels['dimmer'], ChannelType.DIMMER),
        ]

        red_dimmer_mappings = [
            ChannelMapping([1], sample_channels['red'], ChannelType.RED),
            ChannelMapping([4], sample_channels['dimmer'], ChannelType.DIMMER),
        ]

        with patch('builtins.print'):  # Suppress output
            # Start RGB animation
            rgb_anim = animation_engine.create_animation(
                channel_mappings=rgb_mappings,
                current_values={ChannelType.RED: 0, ChannelType.GREEN: 0, ChannelType.BLUE: 0},
                desired_values={ChannelType.RED: 255, ChannelType.GREEN: 255, ChannelType.BLUE: 255},
                animation_duration_seconds=1.0
            )

            # Start dimmer animation (no conflict)
            dimmer_anim = animation_engine.create_animation(
                channel_mappings=dimmer_mappings,
                current_values={ChannelType.DIMMER: 0},
                desired_values={ChannelType.DIMMER: 255},
                animation_duration_seconds=1.0
            )

            # Both should be active (no conflict)
            assert len(animation_engine.active_animations) == 2

            # Start red+dimmer animation (partial conflict)
            red_dimmer_anim = animation_engine.create_animation(
                channel_mappings=red_dimmer_mappings,
                current_values={ChannelType.RED: 128, ChannelType.DIMMER: 128},
                desired_values={ChannelType.RED: 0, ChannelType.DIMMER: 0},
                animation_duration_seconds=0.5
            )

            await asyncio.sleep(0.05)  # Allow cancellation to process

            # RGB animation should be cancelled (red conflict)
            # Dimmer animation should be cancelled (dimmer conflict)
            # Only red+dimmer animation should remain
            assert len(animation_engine.active_animations) == 1
            assert red_dimmer_anim in animation_engine.active_animations

        await animation_engine.hass.wait_for_all_tasks(timeout=2.0)

    @pytest.mark.asyncio
    async def test_manual_animation_cancellation(self, animation_engine, sample_channel_mappings):
        """Test manually cancelling animations"""
        with patch('builtins.print'):  # Suppress output
            animation_id = animation_engine.create_animation(
                channel_mappings=sample_channel_mappings,
                current_values={ChannelType.RED: 0},
                desired_values={ChannelType.RED: 255},
                animation_duration_seconds=2.0
            )

            # Verify animation is active
            assert len(animation_engine.active_animations) == 1

            # Cancel the animation
            cancelled = animation_engine.cancel_animation(animation_id)
            assert cancelled == True

            # Wait for cancellation to process
            await asyncio.sleep(0.1)

            # Verify animation was cleaned up
            assert len(animation_engine.active_animations) == 0
            assert len(animation_engine.dmx_channel_owners) == 0

    @pytest.mark.asyncio
    async def test_cancel_all_animations(self, animation_engine, sample_channel_mappings):
        """Test cancelling all animations"""
        with patch('builtins.print'):  # Suppress output
            # Create multiple animations
            for i in range(3):
                animation_engine.create_animation(
                    channel_mappings=[ChannelMapping([10 + i], Channel(10 + i, f"Test{i}"), ChannelType.DIMMER)],
                    current_values={ChannelType.DIMMER: 0},
                    desired_values={ChannelType.DIMMER: 255},
                    animation_duration_seconds=2.0
                )

            # Verify all animations are active
            assert len(animation_engine.active_animations) == 3

            # Cancel all animations
            animation_engine.cancel_all_animations()

            # Wait for cancellations to process
            await asyncio.sleep(0.1)

            # Verify all animations were cleaned up
            assert len(animation_engine.active_animations) == 0
            assert len(animation_engine.dmx_channel_owners) == 0

    def test_engine_state_queries(self, animation_engine, sample_channel_mappings):
        """Test engine state query methods"""
        # Initially empty
        assert animation_engine.get_active_animation_count() == 0
        assert animation_engine.get_controlled_channels() == {}

        with patch('builtins.print'):  # Suppress output
            # Create an animation
            animation_id = animation_engine.create_animation(
                channel_mappings=sample_channel_mappings,
                current_values={ChannelType.RED: 0},
                desired_values={ChannelType.RED: 255},
                animation_duration_seconds=1.0
            )

            # Test state queries
            assert animation_engine.get_active_animation_count() == 1
            controlled = animation_engine.get_controlled_channels()
            assert len(controlled) == 4  # RGB + Dimmer
            assert all(controlled[i] == animation_id for i in [1, 2, 3, 4])

    @pytest.mark.asyncio
    async def test_animation_frame_output(self, animation_engine, sample_channel_mappings):
        """Test that animation frames are output correctly"""
        current_values = {ChannelType.RED: 0, ChannelType.GREEN: 100}
        desired_values = {ChannelType.RED: 255, ChannelType.GREEN: 200}

        frame_outputs = []

        def capture_frame_output(*args):
            frame_outputs.append(args)

        with patch('builtins.print', side_effect=capture_frame_output):
            animation_id = animation_engine.create_animation(
                channel_mappings=sample_channel_mappings,
                current_values=current_values,
                desired_values=desired_values,
                animation_duration_seconds=0.2
            )

            # Wait for animation to complete
            await animation_engine.hass.wait_for_all_tasks(timeout=1.0)

        # Verify frames were output
        assert len(frame_outputs) > 0

        # Check that frame output contains expected data
        first_frame = frame_outputs[0][0] if frame_outputs else ""
        last_frame = frame_outputs[-1][0] if frame_outputs else ""

        assert animation_id in first_frame
        assert "DMX Values:" in first_frame
        assert "Progress:" in first_frame

    @pytest.mark.asyncio
    async def test_zero_duration_animation(self, animation_engine, sample_channel_mappings):
        """Test animation with zero duration completes immediately"""
        with patch('builtins.print') as mock_print:
            animation_id = animation_engine.create_animation(
                channel_mappings=sample_channel_mappings,
                current_values={ChannelType.RED: 0},
                desired_values={ChannelType.RED: 255},
                animation_duration_seconds=0.0
            )

            # Wait briefly for task to complete
            await animation_engine.hass.wait_for_all_tasks(timeout=0.5)

        # Animation should complete immediately and clean up
        assert len(animation_engine.active_animations) == 0
        assert mock_print.called
