"""Rate limiter utility for ArtNet LED integration."""

import asyncio
import time
from collections.abc import Callable

from homeassistant.core import HomeAssistant, callback


class RateLimiter:
    """Utility class to manage rate limiting for entity updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        update_method: Callable[[], None],
        update_interval: float = 0.5,
        force_update_after: float = 2.0,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            hass: Home Assistant instance
            update_method: The method to call when an update should be performed
            update_interval: Minimum time between updates in seconds
            force_update_after: Force an update after this time if pending
        """
        self._hass = hass
        self._update_method = update_method
        self._update_interval = update_interval
        self._force_update_after = force_update_after

        # State tracking
        self._last_update_time = 0.0  # Track last update time
        self._update_scheduled = False  # Track if an update is already scheduled
        self._pending_update = False  # Track if there are pending changes
        self._update_lock = asyncio.Lock()  # Lock to prevent race conditions
        self._last_forced_time = 0.0  # Track last time we forced an update

    @callback
    def schedule_update(self) -> None:
        """Schedule an update with rate limiting."""
        self._pending_update = True
        current_time = time.monotonic()

        # Check if we need to force an update due to elapsed time
        time_since_forced = current_time - self._last_forced_time
        force_update = time_since_forced >= self._force_update_after

        # If we're within the update interval, schedule a delayed update if not already scheduled
        time_since_last_update = current_time - self._last_update_time
        if time_since_last_update < self._update_interval and not force_update:
            if not self._update_scheduled:
                self._update_scheduled = True
                # Schedule update after the remaining interval time
                remaining_time = max(0.001, self._update_interval - time_since_last_update)
                self._hass.async_create_task(self._delayed_update(remaining_time))
        else:
            # We're outside the update interval or forcing an update
            self._do_update()
            if force_update:
                self._last_forced_time = current_time

    async def _delayed_update(self, delay: float) -> None:
        """Handle delayed update to reduce update frequency."""
        try:
            await asyncio.sleep(delay)
            async with self._update_lock:
                # Only update if there are pending changes
                if self._pending_update:
                    self._do_update()
        finally:
            # Reset the scheduled flag
            self._update_scheduled = False

            # If changes happened during our sleep, schedule another update check
            # to ensure we don't miss the final state
            if self._pending_update:
                # Small delay to see if more updates are coming
                await asyncio.sleep(0.05)
                self.schedule_update()

    def _do_update(self) -> None:
        """Perform the actual update."""
        self._last_update_time = time.monotonic()
        self._pending_update = False
        self._update_method()
