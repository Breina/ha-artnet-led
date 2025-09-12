import asyncio
import logging
import time
from typing import Any, Callable

from homeassistant.core import HomeAssistant

from custom_components.dmx.animation.animation_task import AnimationTask
from custom_components.dmx.entity.light import ChannelMapping, ChannelType

_LOGGER = logging.getLogger(__name__)


class DmxAnimationEngine:
    """Animation engine for DMX lighting transitions (supports Art-Net and sACN)"""

    def __init__(self, hass: HomeAssistant, universe: Any = None, max_fps: int = 30) -> None:
        self.hass = hass
        self.universe = universe
        self.max_fps = max_fps
        self.frame_interval = 1.0 / max_fps
        self.active_animations: dict[str, AnimationTask] = {}
        self.dmx_channel_owners: dict[int, str] = {}  # Maps DMX index to animation_id
        self._animation_counter = 0

    def _generate_animation_id(self) -> str:
        """Generate a unique animation ID"""
        self._animation_counter += 1
        return f"anim_{self._animation_counter}_{int(time.time() * 1000)}"

    def _cancel_conflicting_animations(self, new_animation: AnimationTask) -> None:
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

    def _claim_dmx_channels(self, animation: AnimationTask) -> None:
        """Claim DMX channels for the given animation"""
        for dmx_index in animation.controlled_indexes:
            self.dmx_channel_owners[dmx_index] = animation.animation_id

    def _cleanup_animation(self, animation_id: str) -> None:
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

    async def _run_animation(self, animation: AnimationTask) -> None:
        """Run a single animation to completion"""
        try:
            _LOGGER.debug(f"Starting animation {animation.animation_id} for {animation.duration_seconds}s")

            while not animation.is_cancelled:
                start_time = time.time()

                frame_values = animation.calculate_frame_values()
                progress = animation.get_progress()

                self._output_frame(frame_values)

                if progress >= 1.0:
                    _LOGGER.debug(f"Animation {animation.animation_id} completed")
                    # Call completion callback if provided
                    if hasattr(animation, "completion_callback") and animation.completion_callback:
                        try:
                            animation.completion_callback()
                        except Exception as e:
                            _LOGGER.error(
                                f"Error calling completion callback for animation {animation.animation_id}: {e}"
                            )
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

    def _output_frame(self, frame_values: dict[ChannelType, int]) -> None:
        """Output frame data to DMX universe"""
        if not self.universe:
            return

        # Convert ChannelType values to DMX updates
        dmx_updates = {}
        for channel_type, value in frame_values.items():
            # Find the channel mapping for this channel type
            for animation in self.active_animations.values():
                for mapping in animation.channel_mappings:
                    if mapping.channel_type == channel_type:
                        try:
                            # Convert to DMX values using the mapping
                            capabilities = mapping.channel.capabilities
                            if isinstance(capabilities, list):
                                first_capability = capabilities[0]
                            else:
                                first_capability = capabilities
                            [entity] = first_capability.dynamic_entities
                            norm_val = entity.normalize(value)
                            dmx_values = entity.to_dmx_fine(norm_val, len(mapping.dmx_indexes))

                            for i, dmx_index in enumerate(mapping.dmx_indexes):
                                dmx_updates[dmx_index] = dmx_values[i]
                        except Exception as e:
                            _LOGGER.error(f"Error converting channel {channel_type} value {value} to DMX: {e}")
                        break

        # Send DMX updates to universe (non-blocking)
        if dmx_updates:
            self.hass.create_task(self.universe.update_multiple_values(dmx_updates))
        else:
            _LOGGER.debug(f"No DMX updates generated from frame values: {frame_values}")

    def create_animation(
        self,
        channel_mappings: list[ChannelMapping],
        current_values: dict[ChannelType, int],
        desired_values: dict[ChannelType, int],
        animation_duration_seconds: float,
        min_kelvin: int | None = None,
        max_kelvin: int | None = None,
        completion_callback: Callable[[], None] | None = None,
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
            max_kelvin=max_kelvin,
        )
        animation.completion_callback = completion_callback

        # Cancel any conflicting animations
        self._cancel_conflicting_animations(animation)

        # Claim DMX channels for this animation
        self._claim_dmx_channels(animation)

        # Start the animation task
        animation.task = self.hass.async_create_task(self._run_animation(animation))
        self.active_animations[animation.animation_id] = animation

        _LOGGER.info(
            f"Created animation {animation.animation_id} controlling "
            f"DMX channels: {sorted(animation.controlled_indexes)}"
        )

        return animation.animation_id

    def cancel_animation(self, animation_id: str) -> bool:
        """Cancel a specific animation by ID"""
        if animation_id in self.active_animations:
            animation = self.active_animations[animation_id]
            animation.is_cancelled = True
            if animation.task and not animation.task.done():
                animation.task.cancel()
            return True
        return False

    def cancel_all_animations(self) -> None:
        """Cancel all active animations"""
        for animation_id in list(self.active_animations.keys()):
            self.cancel_animation(animation_id)

    def get_active_animation_count(self) -> int:
        """Get the number of currently active animations"""
        return len(self.active_animations)

    def get_controlled_channels(self) -> dict[int, str]:
        """Get a mapping of DMX channels to their controlling animation IDs"""
        return self.dmx_channel_owners.copy()
