"""Per-slot arbitration between the remote sACN sources of a universe."""

from dataclasses import dataclass

from custom_components.dmx.server.sacn_packet import START_CODE_PER_ADDRESS_PRIORITY, SacnPacket

SOURCE_LOSS_TIMEOUT = 2.5
"""Seconds without level data after which a source has given up control."""

PRIORITY_LOSS_TIMEOUT = 2.5
"""Seconds without per-address priorities after which a source falls back to its universe priority."""

PRIORITY_WAIT = 1.5
"""Seconds a new source gets to send per-address priorities before its levels count."""

SLOT_COUNT = 512


@dataclass(frozen=True)
class ReceivedSlot:
    """A level from the network, along with who sent it and how strongly it's claimed."""

    level: int
    priority: int
    source: str | None


@dataclass
class _RemoteSource:
    name: str
    first_seen: float
    last_levels: float
    universe_priority: int = 0
    levels: bytes | None = None
    address_priorities: bytes | None = None
    last_priorities: float = 0.0
    waiting_for_priorities: bool = True


def merge_priority(universe_priority: int) -> int:
    """Per-address priority 0 means "not sourced", which a universe priority of 0 doesn't."""
    return max(1, universe_priority)


class SacnMerger:
    """
    Tracks the remote sources of one universe, identified by CID, and arbitrates between them per slot: the highest
    priority wins, and among equals the highest level does (HTP).
    """

    def __init__(self) -> None:
        self._sources: dict[bytes, _RemoteSource] = {}

    def handle_packet(self, packet: SacnPacket, now: float) -> bool:
        """Takes in a level (0x00) or priority (0xDD) packet, returns whether the merge result may have changed."""
        if packet.options.stream_terminated:
            return self._sources.pop(packet.cid, None) is not None

        source = self._sources.get(packet.cid)
        if source is None:
            source = self._sources[packet.cid] = _RemoteSource(packet.source_name, now, now)

        data = bytes(packet.channel_data)

        if packet.start_code == START_CODE_PER_ADDRESS_PRIORITY:
            changed = source.address_priorities != data
            source.address_priorities = data
            source.last_priorities = now
            source.waiting_for_priorities = False
            return changed

        changed = (
            source.levels != data or source.universe_priority != packet.priority or source.name != packet.source_name
        )
        source.levels = data
        source.universe_priority = packet.priority
        source.name = packet.source_name
        source.last_levels = now
        return changed

    def expire(self, now: float) -> bool:
        """Applies everything that happens by a source staying silent, returns whether anything did."""
        changed = False

        for cid, source in list(self._sources.items()):
            if now - source.last_levels >= SOURCE_LOSS_TIMEOUT:
                del self._sources[cid]
                changed = True
                continue

            if source.address_priorities is not None and now - source.last_priorities >= PRIORITY_LOSS_TIMEOUT:
                source.address_priorities = None
                changed = True

            if source.waiting_for_priorities and now - source.first_seen >= PRIORITY_WAIT:
                source.waiting_for_priorities = False
                changed = True

        return changed

    def merge(self) -> dict[int, ReceivedSlot]:
        """The winning remote source's level for every slot that any of them is sourcing."""
        merged: dict[int, ReceivedSlot] = {}

        for source in self._sources.values():
            if source.levels is None or source.waiting_for_priorities:
                continue

            levels = source.levels
            priorities = source.address_priorities
            universe_priority = merge_priority(source.universe_priority)

            for index in range(SLOT_COUNT):
                if priorities is None:
                    priority = universe_priority
                else:
                    priority = priorities[index] if index < len(priorities) else 0
                    if priority == 0:
                        continue

                # Slots past the end of a short frame are still claimed, at level 0.
                level = levels[index] if index < len(levels) else 0

                current = merged.get(index + 1)
                if current is None or (priority, level) > (current.priority, current.level):
                    merged[index + 1] = ReceivedSlot(level, priority, source.name)

        return merged
