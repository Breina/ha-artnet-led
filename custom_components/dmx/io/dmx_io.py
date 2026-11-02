import asyncio
from collections.abc import Callable
from typing import Any

from custom_components.dmx.animation.engine import DmxAnimationEngine
from custom_components.dmx.server import PortAddress
from custom_components.dmx.server.artnet_server import ArtNetServer
from custom_components.dmx.server.sacn_merge import ReceivedSlot, merge_priority
from custom_components.dmx.server.sacn_server import SacnServer


class DmxUniverse:

    def __init__(
        self,
        port_address: PortAddress,
        controller: ArtNetServer | None,
        use_partial_universe: bool = True,
        sacn_server: SacnServer | None = None,
        sacn_universe: int | None = None,
        hass: Any = None,
        max_fps: int = 30,
    ) -> None:
        self.port_address = port_address
        self.controller = controller
        self.sacn_server = sacn_server
        self.sacn_universe = sacn_universe
        self.use_partial_universe = use_partial_universe
        self._hass = hass

        # What we send ourselves, which only local changes write to. Anything received stays in _received, otherwise
        # we'd end up transmitting other controllers' levels as our own.
        self._channel_values: dict[int, int] = {}
        self._received: dict[int, ReceivedSlot] = {}
        # Art-Net has no priorities: there, whoever wrote a channel last wins.
        self._output_priority = merge_priority(sacn_server.config.priority) if sacn_server else None
        self._constant_values: dict[int, int] = {}
        self._channel_callbacks: dict[int, list[Callable[[str | None], None]]] = {}
        self._output_enabled: bool = True
        self._send_timer: asyncio.TimerHandle | None = None
        self._last_send_time: float = 0.0
        self._frame_interval: float = 1.0 / max_fps
        self.animation_engine: DmxAnimationEngine | None = None

        if hass:
            self.animation_engine = DmxAnimationEngine(hass, self, max_fps)

        if self.sacn_server and self.sacn_universe:
            self.sacn_server.add_universe(self.sacn_universe)

    def set_output_enabled(self, enabled: bool) -> None:
        self._output_enabled = enabled
        if self.sacn_server and self.sacn_universe:
            if not enabled:
                self.sacn_server.terminate_universe(self.sacn_universe)
            else:
                self.sacn_server.add_universe(self.sacn_universe)
                self.send_universe_data()

    def is_output_enabled(self) -> bool:
        return self._output_enabled

    def set_constant_value(self, channels: list[int], value: int) -> None:

        for ch in channels:
            self._constant_values[ch] = value
            self._channel_values[ch] = value

    def register_channel_listener(self, channels: int | list[int], callback: Callable[[str | None], None]) -> None:
        if isinstance(channels, int):
            channels = [channels]

        for channel in channels:
            if channel not in self._channel_callbacks:
                self._channel_callbacks[channel] = []

            if callback not in self._channel_callbacks[channel]:
                self._channel_callbacks[channel].append(callback)

    async def update_value(
        self,
        channel: int | list[int],
        value: int,
        send_immediately: bool = False,
        fire_callbacks: bool = True,
    ) -> dict[Callable[[str | None], None], str | None]:
        """Changes a value we're sending ourselves."""

        channels = [channel] if isinstance(channel, int) else channel

        callbacks_to_call: dict[Callable[[str | None], None], str | None] = {}
        affected_channels: list[int] = []

        for ch in channels:
            if ch in self._constant_values:
                continue

            changed = ch not in self._channel_values or self._channel_values[ch] != value
            self._channel_values[ch] = value

            overwrote_received = self._output_priority is None and self._received.pop(ch, None) is not None

            # Also when nothing changed: if another source still wins, whoever asked for this has to hear about it.
            if changed or overwrote_received or self._winning_slot(ch) is not None:
                affected_channels.append(ch)

        for ch in affected_channels:
            source = self.get_channel_source(ch)
            for callback in self._channel_callbacks.get(ch, ()):
                if callback in callbacks_to_call:
                    continue
                callbacks_to_call[callback] = source
                if fire_callbacks:
                    try:
                        await self._call_callback(callback, source)
                    except Exception as e:
                        print(f"Error calling callback for channel {ch}: {e}")

        if send_immediately:
            self.send_universe_data()

        return callbacks_to_call

    async def update_multiple_values(self, updates: dict[int, int], send_update: bool = True) -> None:
        """Changes values we're sending ourselves."""
        # Collect all affected callbacks without firing them, so every callback
        # fires exactly once after all channel values have been written.
        # This matters for 16-bit (fine) channels where coarse and fine bytes
        # must both be updated before the callback reads the combined value.
        callbacks_to_call: dict[Callable[[str | None], None], str | None] = {}
        for channel, value in updates.items():
            for callback, source in (
                await self.update_value(channel, value, send_immediately=False, fire_callbacks=False)
            ).items():
                callbacks_to_call.setdefault(callback, source)

        for callback, source in callbacks_to_call.items():
            await self._call_callback(callback, source)

        if send_update:
            self._schedule_send()

    async def receive_values(self, updates: dict[int, int], source: str | None) -> None:
        """Takes in levels from a controller on the network, for protocols without priorities."""
        received = {channel: ReceivedSlot(value, 0, source) for channel, value in updates.items()}
        await self.set_received({**self._received, **received})

    async def set_received(self, received: dict[int, ReceivedSlot]) -> None:
        """Replaces what the network is sending. Never gets transmitted, it's only what entities get to show."""
        channels = self._received.keys() | received.keys()
        previous_values = {channel: self.get_channel_value(channel) for channel in channels}

        self._received = received

        callbacks_to_call: dict[Callable[[str | None], None], str | None] = {}
        for channel in channels:
            if self.get_channel_value(channel) != previous_values[channel]:
                source = self.get_channel_source(channel)
                for callback in self._channel_callbacks.get(channel, ()):
                    callbacks_to_call.setdefault(callback, source)

        for callback, source in callbacks_to_call.items():
            await self._call_callback(callback, source)

    def _winning_slot(self, channel: int) -> ReceivedSlot | None:
        """What was received for this channel, if that takes precedence over what we're sending ourselves."""
        received = self._received.get(channel)
        if received is None:
            return None

        own_value = self._channel_values.get(channel)
        if own_value is None or self._output_priority is None:
            return received

        if received.priority != self._output_priority:
            return received if received.priority > self._output_priority else None

        return received if received.level > own_value else None

    def _schedule_send(self) -> None:
        """Throttle send_universe_data to at most once per frame interval.

        Sends immediately if enough time has passed since the last send.
        Otherwise schedules a send at the next frame boundary, coalescing
        any intermediate updates into a single frame.
        """
        import time

        now = time.monotonic()
        elapsed = now - self._last_send_time

        if elapsed >= self._frame_interval:
            # Enough time has passed, send immediately
            if self._send_timer is not None:
                self._send_timer.cancel()
                self._send_timer = None
            self._do_send()
        elif self._send_timer is None:
            if self._hass:
                # Schedule send at next frame boundary
                remaining = self._frame_interval - elapsed
                self._send_timer = self._hass.loop.call_later(remaining, self._do_send)
            else:
                # No event loop available (e.g. unit tests); send synchronously
                self._do_send()

    def _do_send(self) -> None:
        import time

        self._send_timer = None
        self._last_send_time = time.monotonic()
        self.send_universe_data()

    @staticmethod
    async def _call_callback(callback: Callable[[str | None], None], source: str | None = None) -> None:
        if asyncio.iscoroutinefunction(callback):
            await callback(source)
        else:
            callback(source)

    def get_channel_value(self, channel: int) -> int:
        """The level this channel is effectively at, considering everyone sending to this universe."""
        winning_slot = self._winning_slot(channel)
        return winning_slot.level if winning_slot else self._channel_values.get(channel, 0)

    def get_channel_source(self, channel: int) -> str | None:
        """Who the channel's effective level comes from, None if that's us."""
        winning_slot = self._winning_slot(channel)
        return winning_slot.source if winning_slot else None

    def is_channel_set(self, channel: int) -> bool:
        """Whether we've given this channel a level ourselves."""
        return channel in self._channel_values

    def send_universe_data(self) -> None:
        if not self._output_enabled:
            return

        if not self._channel_values:
            data = bytearray(2)  # Minimum size is 2 bytes

            if self.controller:
                self.controller.send_dmx(self.port_address, data)

            # Send via sACN if available
            if self.sacn_server and self.sacn_universe:
                sacn_data = bytearray([0] + [0] * 24)
                self.sacn_server.send_dmx_data(self.sacn_universe, sacn_data, b"")

            return

        if self.use_partial_universe:
            max_channel = max(self._channel_values.keys()) if self._channel_values else 2

            data_length = max_channel + (max_channel % 2)
            data_length = max(2, data_length)

            data = bytearray(data_length)
        else:
            data = bytearray(512)

        for channel, value in self._channel_values.items():
            if 1 <= channel <= len(data):
                data[channel - 1] = value

        if self.controller:
            self.controller.send_dmx(self.port_address, data)

        # Send via sACN if available
        if self.sacn_server and self.sacn_universe:
            # sACN requires start code + channel data (minimum 25 bytes total)
            sacn_data = bytearray([0, *data])  # Add start code
            if len(sacn_data) < 25:
                sacn_data.extend([0] * (25 - len(sacn_data)))

            # Only claim the slots we've given a level, the others are free for other controllers to use.
            assert self._output_priority is not None  # Set whenever there's an sACN server
            address_priorities = bytes(
                self._output_priority if channel in self._channel_values else 0 for channel in range(1, len(data) + 1)
            )
            self.sacn_server.send_dmx_data(self.sacn_universe, sacn_data, address_priorities)
