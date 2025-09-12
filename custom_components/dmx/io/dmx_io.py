import asyncio
from collections.abc import Callable
from typing import Any

from custom_components.dmx.animation.engine import DmxAnimationEngine
from custom_components.dmx.server import PortAddress
from custom_components.dmx.server.artnet_server import ArtNetServer
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

        self._channel_values: dict[int, int] = {}
        self._constant_values: dict[int, int] = {}
        self._channel_callbacks: dict[int, list[Callable[[str | None], None]]] = {}
        self._changed_channels: set[int] = set()
        self._first_send: bool = True
        self._output_enabled: bool = True
        self.animation_engine: DmxAnimationEngine | None = None

        if hass:
            self.animation_engine = DmxAnimationEngine(hass, self, max_fps)

        if self.sacn_server and self.sacn_universe:
            self.sacn_server.add_universe(self.sacn_universe)

    def set_output_enabled(self, enabled: bool) -> None:
        self._output_enabled = enabled

    def is_output_enabled(self) -> bool:
        return self._output_enabled

    def set_constant_value(self, channels: list[int], value: int) -> None:

        for ch in channels:
            self._constant_values[ch] = value
            self._channel_values[ch] = value
            self._changed_channels.add(ch)

    def register_channel_listener(self, channels: int | list[int], callback: Callable[[str | None], None]) -> None:
        if isinstance(channels, int):
            channels = [channels]

        for channel in channels:
            if channel not in self._channel_callbacks:
                self._channel_callbacks[channel] = []

            if callback not in self._channel_callbacks[channel]:
                self._channel_callbacks[channel].append(callback)

    async def update_value(
        self, channel: int | list[int], value: int, send_immediately: bool = False, source: str | None = None
    ) -> set[Callable[[str | None], None]]:

        channels = [channel] if isinstance(channel, int) else channel

        callbacks_to_call: set[Callable[[str | None], None]] = set()
        changed_channels: list[int] = []

        for ch in channels:
            if ch in self._constant_values and source is None:
                continue

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

    async def update_multiple_values(
        self, updates: dict[int, int], source: str | None = None, send_update: bool = True
    ) -> None:
        callbacks_to_call: set[Callable[[str | None], None]] = set()
        for channel, value in updates.items():
            callbacks_to_call.update(await self.update_value(channel, value, send_immediately=False, source=source))

        for callback in callbacks_to_call:
            await self._call_callback(callback, source)

        if send_update:
            self.send_universe_data()

    @staticmethod
    async def _call_callback(callback: Callable[[str | None], None], source: str | None = None) -> None:
        if asyncio.iscoroutinefunction(callback):
            await callback(source)
        else:
            callback(source)

    def get_channel_value(self, channel: int) -> int:
        return self._channel_values.get(channel, 0)

    def send_universe_data(self) -> None:
        if not self._output_enabled:
            return

        for channel, constant_value in self._constant_values.items():
            if self._channel_values.get(channel) != constant_value:
                self._channel_values[channel] = constant_value
                self._changed_channels.add(channel)

        if not self._channel_values:
            data = bytearray(2)  # Minimum size is 2 bytes

            if self.controller:
                self.controller.send_dmx(self.port_address, data)

            # Send via sACN if available
            if self.sacn_server and self.sacn_universe:
                sacn_data = bytearray([0] + [0] * 24)
                self.sacn_server.send_dmx_data(self.sacn_universe, sacn_data)

            self._changed_channels.clear()
            self._first_send = False
            return

        if self.use_partial_universe and not self._first_send and self._changed_channels:
            max_changed_channel = max(self._changed_channels)

            data_length = (
                (max_changed_channel + (2 - (max_changed_channel % 2)))
                if max_changed_channel % 2
                else max_changed_channel
            )

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
            self.sacn_server.send_dmx_data(self.sacn_universe, sacn_data)

        self._changed_channels.clear()
        self._first_send = False
