import asyncio
import logging
import time
from collections.abc import Callable

from custom_components.dmx.animation.color_calculator import LightTransitionAnimator
from custom_components.dmx.entity.light import ChannelMapping, ChannelType

_LOGGER = logging.getLogger(__name__)


class AnimationTask:
    """Represents a single running animation"""

    def __init__(
        self,
        animation_id: str,
        channel_mappings: list[ChannelMapping],
        current_values: dict[ChannelType, int],
        desired_values: dict[ChannelType, int],
        duration_seconds: float,
        min_kelvin: int | None = None,
        max_kelvin: int | None = None,
    ):
        self.animation_id = animation_id
        self.channel_mappings = channel_mappings
        self.duration_seconds = duration_seconds
        self.start_time = time.time()
        self.is_cancelled = False

        self.task: asyncio.Task[None] | None = None
        self.completion_callback: Callable[[], None] | None = None

        self.controlled_indexes: set[int] = set()
        for mapping in channel_mappings:
            self.controlled_indexes.update(mapping.dmx_indexes)

        # Convert int values to float for the animator
        current_values_float = {k: float(v) for k, v in current_values.items()}
        desired_values_float = {k: float(v) for k, v in desired_values.items()}
        self.animator = LightTransitionAnimator(current_values_float, desired_values_float, min_kelvin, max_kelvin)

    def get_progress(self) -> float:
        """Get animation progress from 0.0 to 1.0"""
        if self.duration_seconds <= 0:
            return 1.0

        elapsed = time.time() - self.start_time
        progress = min(elapsed / self.duration_seconds, 1.0)
        return progress

    def calculate_frame_values(self) -> dict[ChannelType, int]:
        """Calculate the current frame values based on animation progress"""
        progress = self.get_progress()

        float_values = self.animator.interpolate(progress)
        return {k: round(v) for k, v in float_values.items()}
