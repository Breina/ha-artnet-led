import asyncio
from typing import List, Callable, Dict

from custom_components.dmx import PortAddress, ArtNetServer


class DmxUniverse:
    def __init__(self, port_address: PortAddress, controller: ArtNetServer):
        self.port_address = port_address
        self.controller = controller

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

    async def update_value(self, channel: int | List[int], value: int, send_immediately: bool = False) -> None:
        """
        Update the value of one or more channels and notify all listeners.

        Args:
            channel: Single channel number or list of channel numbers
            value: New value for the channel(s)
            send_immediately: Whether to send the universe data immediately after update
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

        # Only send updates immediately if explicitly requested
        if send_immediately:
            self.send_universe_data()

    async def update_multiple_values(self, updates: Dict[int, int]) -> None:
        """
        Update multiple channel values in a batch and send once at the end.

        Args:
            updates: Dictionary mapping channel numbers to values
        """
        # Update each channel value without sending immediately
        for channel, value in updates.items():
            await self.update_value(channel, value, send_immediately=False)

        # Send all updates at once
        self.send_universe_data()

    async def _call_callback(self, callback, channel, value):
        """Helper method to call callbacks that might be async or regular functions."""
        if asyncio.iscoroutinefunction(callback):
            await callback(channel, value)
        else:
            callback(channel, value)

    def get_channel_value(self, channel: int) -> int:
        """Get the current value of a channel."""
        return self._channel_values.get(channel, 0)

    def send_universe_data(self) -> None:
        """
        Gather all channel values into a 512-sized bytearray and send it via ArtNet.
        """
        # Create a bytearray filled with zeros (default DMX value is 0)
        data = bytearray(512)

        # Fill in the values for channels that have been set
        for channel, value in self._channel_values.items():
            # DMX channels are 1-based, but bytearray indices are 0-based
            if 1 <= channel <= 512:
                data[channel - 1] = value

        # Send the data via the controller
        self.controller.send_dmx(self.port_address, data)
