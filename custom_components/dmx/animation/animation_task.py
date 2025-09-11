import logging
import time
from typing import Dict, List, Optional, Set

from custom_components.dmx.animation.color_calculator import LightTransitionAnimator
from custom_components.dmx.entity.light import ChannelMapping, ChannelType

_LOGGER = logging.getLogger(__name__)


class AnimationTask:
    """Represents a single running animation"""

    def __init__(
        self,
        animation_id: str,
        channel_mappings: List[ChannelMapping],
        current_values: Dict[ChannelType, int],
        desired_values: Dict[ChannelType, int],
        duration_seconds: float,
        min_kelvin: Optional[int] = None,
        max_kelvin: Optional[int] = None,
    ):
        self.animation_id = animation_id
        self.channel_mappings = channel_mappings
        self.duration_seconds = duration_seconds
        self.start_time = time.time()
        self.is_cancelled = False

        self.task = None

        self.controlled_indexes: Set[int] = set()
        for mapping in channel_mappings:
            self.controlled_indexes.update(mapping.dmx_indexes)

        self.animator = LightTransitionAnimator(current_values, desired_values, min_kelvin, max_kelvin)

    def get_progress(self) -> float:
        """Get animation progress from 0.0 to 1.0"""
        if self.duration_seconds <= 0:
            return 1.0

        elapsed = time.time() - self.start_time
        progress = min(elapsed / self.duration_seconds, 1.0)
        return progress

    def calculate_frame_values(self) -> Dict[ChannelType, int]:
        """Calculate the current frame values based on animation progress"""
        progress = self.get_progress()

        return self.animator.interpolate(progress)
