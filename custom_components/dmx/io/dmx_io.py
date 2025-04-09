import asyncio
from typing import List, Callable


class Universe:
    def __init__(self):
        # Dictionary to store channel value: {channel_number: current_value}
        self._channel_values = {}

        # Dictionary to store callbacks: {channel_number: [callback1, callback2, ...]}
        self._channel_callbacks = {}

    def register_channel_listener(self, channels: int | List[int],
                                  callback: Callable[[int, int], None]) -> None:
        """
        Register a callback to be called when a channel value changes.

        Args:
            channels: Single channel number or list of channel numbers
            callback: Function to call with channel number and new value
        """
        if isinstance(channels, int):
            channels = [channels]

        for channel in channels:
            if channel not in self._channel_callbacks:
                self._channel_callbacks[channel] = []

            if callback not in self._channel_callbacks[channel]:
                self._channel_callbacks[channel].append(callback)

    def unregister_channel_listener(self, channels: int | List[int],
                                    callback: Callable[[int, int], None]) -> None:
        """Remove a callback from the registry."""
        if isinstance(channels, int):
            channels = [channels]

        for channel in channels:
            if channel in self._channel_callbacks and callback in self._channel_callbacks[channel]:
                self._channel_callbacks[channel].remove(callback)

    async def update_value(self, channel: int | List[int], value: int) -> None:
        """
        Update the value of one or more channels and notify all listeners.

        Args:
            channel: Single channel number or list of channel numbers
            value: New value for the channel(s)
        """
        # Convert to list if single channel
        if isinstance(channel, int):
            channels = [channel]
        else:
            channels = channel

        # Update all specified channels
        for ch in channels:
            # Only process if value has changed or channel is new
            if ch not in self._channel_values or self._channel_values[ch] != value:
                # Update stored value
                self._channel_values[ch] = value

                # Notify all listeners for this channel
                if ch in self._channel_callbacks:
                    for callback in self._channel_callbacks[ch]:
                        try:
                            # Pass both channel and value to callback
                            await self._call_callback(callback, ch, value)
                        except Exception as e:
                            print(f"Error calling callback for channel {ch}: {e}")

                # Perform actual DMX output
                print(f"Updating DMX channel {ch} to value {value}")
                # Actual DMX output code would go here

    async def _call_callback(self, callback, channel, value):
        """Helper method to call callbacks that might be async or regular functions."""
        if asyncio.iscoroutinefunction(callback):
            await callback(channel, value)
        else:
            callback(channel, value)

    def get_channel_value(self, channel: int) -> int:
        """Get the current value of a channel."""
        return self._channel_values.get(channel, 0)