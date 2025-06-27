import asyncio
import logging
import time
from typing import Dict, List, Optional

from homeassistant.core import HomeAssistant

from custom_components.dmx.animation.animation_task import AnimationTask
from custom_components.dmx.entity.light import ChannelMapping, ChannelType

_LOGGER = logging.getLogger(__name__)


class ArtNetAnimationEngine:
    """Animation engine for Art-Net DMX lighting transitions"""

    def __init__(self, hass: HomeAssistant, max_fps: int = 30):
        self.hass = hass
        self.max_fps = max_fps
        self.frame_interval = 1.0 / max_fps
        self.active_animations: Dict[str, AnimationTask] = {}
        self.dmx_channel_owners: Dict[int, str] = {}  # Maps DMX index to animation_id
        self._animation_counter = 0

    def _generate_animation_id(self) -> str:
        """Generate a unique animation ID"""
        self._animation_counter += 1
        return f"anim_{self._animation_counter}_{int(time.time() * 1000)}"

    def _cancel_conflicting_animations(self, new_animation: AnimationTask):
        """Cancel any animations that control the same DMX channels"""
        conflicting_animations = []

        for dmx_index in new_animation.controlled_indexes:
            if dmx_index in self.dmx_channel_owners:
                conflicting_anim_id = self.dmx_channel_owners[dmx_index]
                if conflicting_anim_id in self.active_animations:
                    conflicting_animations.append(conflicting_anim_id)

        for anim_id in set(conflicting_animations):
            if anim_id in self.active_animations:
                _LOGGER.debug(f"Cancelling conflicting animation: {anim_id}")
                self._cleanup_animation(anim_id)

    def _claim_dmx_channels(self, animation: AnimationTask):
        """Claim DMX channels for the given animation"""
        for dmx_index in animation.controlled_indexes:
            self.dmx_channel_owners[dmx_index] = animation.animation_id

    def _cleanup_animation(self, animation_id: str):
        """Clean up a completed or cancelled animation"""
        if animation_id not in self.active_animations:
            return

        animation = self.active_animations[animation_id]

        # Release owned DMX channels
        for dmx_index in animation.controlled_indexes:
            if self.dmx_channel_owners.get(dmx_index) == animation_id:
                del self.dmx_channel_owners[dmx_index]

        # Remove from active animations
        del self.active_animations[animation_id]
        _LOGGER.debug(f"Cleaned up animation: {animation_id}")

    async def _run_animation(self, animation: AnimationTask):
        """Run a single animation to completion"""
        try:
            _LOGGER.debug(f"Starting animation {animation.animation_id} for {animation.duration_seconds}s")

            last_frame_time = time.time()

            while not animation.is_cancelled:
                start_time = time.time()

                frame_values = animation.calculate_frame_values()
                progress = animation.get_progress()

                self._output_frame(frame_values)

                if progress >= 1.0:
                    _LOGGER.debug(f"Animation {animation.animation_id} completed")
                    break

                elapsed = time.time() - start_time
                sleep_time = self.frame_interval - elapsed
                await asyncio.sleep(max(0.0, sleep_time))

        except asyncio.CancelledError:
            _LOGGER.debug(f"Animation {animation.animation_id} was cancelled")
        except Exception as e:
            _LOGGER.error(f"Error in animation {animation.animation_id}: {e}")
        finally:
            self._cleanup_animation(animation.animation_id)

    def _output_frame(self, frame_values: Dict[ChannelType, int]):
        """Output frame data (dummy implementation)"""
        pass

    def create_animation(
            self,
            channel_mappings: List[ChannelMapping],
            current_values: Dict[ChannelType, int],
            desired_values: Dict[ChannelType, int],
            animation_duration_seconds: float,
            min_kelvin: Optional[int] = None,
            max_kelvin: Optional[int] = None
    ) -> str:
        """
        Create and start a new animation.

        Returns:
            str: Animation ID that can be used to track or cancel the animation
        """
        animation = AnimationTask(
            animation_id=self._generate_animation_id(),
            channel_mappings=channel_mappings,
            current_values=current_values,
            desired_values=desired_values,
            duration_seconds=animation_duration_seconds,
            min_kelvin=min_kelvin,
            max_kelvin=max_kelvin
        )

        # Cancel any conflicting animations
        self._cancel_conflicting_animations(animation)

        # Claim DMX channels for this animation
        self._claim_dmx_channels(animation)

        # Start the animation task
        animation.task = self.hass.async_create_task(self._run_animation(animation))
        self.active_animations[animation.animation_id] = animation

        _LOGGER.info(f"Created animation {animation.animation_id} controlling "
                     f"DMX channels: {sorted(animation.controlled_indexes)}")

        return animation.animation_id

    def cancel_animation(self, animation_id: str) -> bool:
        """Cancel a specific animation by ID"""
        if animation_id in self.active_animations:
            return True
        return False

    def get_active_animation_count(self) -> int:
        """Get the number of currently active animations"""
        return len(self.active_animations)

    def get_controlled_channels(self) -> Dict[int, str]:
        """Get a mapping of DMX channels to their controlling animation IDs"""
        return self.dmx_channel_owners.copy()
