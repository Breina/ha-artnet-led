import asyncio
from typing import List, Callable, Dict

from custom_components.artnet_led import PortAddress, ArtNetServer


class DmxUniverse:
    def __init__(self, port_address: PortAddress, controller: ArtNetServer, use_partial_universe: bool = True):
        self.port_address = port_address
        self.controller = controller
        self.use_partial_universe = use_partial_universe

        # Dictionary to store channel value: {channel_number: current_value}
        self._channel_values = {}

        # Dictionary to store callbacks: {channel_number: [callback1, callback2, ...]}
        self._channel_callbacks = {}

        # Set to track channels changed since last send
        self._changed_channels = set()

        # Flag to track if this is the first send (to send full universe initially)
        self._first_send = True

    def register_channel_listener(self, channels: int | List[int], callback: Callable[[str | None], None]) -> None:
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

    async def update_value(self, channel: int | List[int], value: int, send_immediately: bool = False, source: str | None = None) -> set[Callable[[str | None], None]]:
        """
        Update the value of one or more channels and notify all listeners.

        Args:
            channel: Single channel number or list of channel numbers
            value: New value for the channel(s)
            send_immediately: Whether to send the universe data immediately after update
            source: From where the update came from
        """
        # Convert to list if single channel
        if isinstance(channel, int):
            channels = [channel]
        else:
            channels = channel

        callbacks_to_call = set()
        changed_channels = []

        for ch in channels:
            if ch not in self._channel_values or self._channel_values[ch] != value:
                self._channel_values[ch] = value
                self._changed_channels.add(ch)
                changed_channels.append(ch)

        for ch in changed_channels:
            if ch in self._channel_callbacks:
                for callback in self._channel_callbacks[ch]:
                    if callback in callbacks_to_call:
                        continue
                    callbacks_to_call.add(callback)
                    try:
                        await self._call_callback(callback, source)
                    except Exception as e:
                        print(f"Error calling callback for channel {ch}: {e}")

        if send_immediately:
            self.send_universe_data()

        return callbacks_to_call

    async def update_multiple_values(self, updates: Dict[int, int], source: str | None = None, send_update: bool = True) -> None:
        """
        Update multiple channel values in a batch and send once at the end.

        Args:
            updates: Dictionary mapping channel numbers to values
            source: From where the update came from
            :param send_update:
        """
        callbacks_to_call = set()
        for channel, value in updates.items():
            callbacks_to_call.update(await self.update_value(channel, value, send_immediately=False, source=source))

        for callback in callbacks_to_call:
            await self._call_callback(callback, source)

        if send_update:
            self.send_universe_data()

    @staticmethod
    async def _call_callback(callback, source: str | None = None):
        """Helper method to call callbacks that might be async or regular functions."""
        if asyncio.iscoroutinefunction(callback):
            await callback(source)
        else:
            callback(source)

    def get_channel_value(self, channel: int) -> int:
        """Get the current value of a channel."""
        return self._channel_values.get(channel, 0)

    def send_universe_data(self) -> None:
        """
        Gather all channel values into a bytearray and send it via ArtNet.
        If use_partial_universe is enabled, only send up to the highest
        changed channel since last transmission (rounded up to a multiple of 2).
        """
        if not self._channel_values:
            # If no channels have been set, send a minimum-sized packet
            data = bytearray(2)  # Minimum size is 2 bytes
            self.controller.send_dmx(self.port_address, data)
            self._changed_channels.clear()
            self._first_send = False
            return

        if self.use_partial_universe and not self._first_send and self._changed_channels:
            # Find the highest channel number that has changed since last send
            max_changed_channel = max(self._changed_channels)

            # Round up to the next multiple of 2
            data_length = (max_changed_channel + (2 - (max_changed_channel % 2))) if max_changed_channel % 2 else max_changed_channel

            # Ensure data_length is at least 2 bytes
            data_length = max(2, data_length)

            # Create a byte array of the appropriate size
            data = bytearray(data_length)
        else:
            # Use the full DMX universe (512 channels) for first send or when partial universe is disabled
            data = bytearray(512)

        # Fill in the values for channels that have been set
        for channel, value in self._channel_values.items():
            # DMX channels are 1-based, but bytearray indices are 0-based
            if 1 <= channel <= len(data):
                data[channel - 1] = value

        # Send the data via the controller
        self.controller.send_dmx(self.port_address, data)

        # Clear the changed channels set after sending
        self._changed_channels.clear()
        self._first_send = False
