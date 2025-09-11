"""
Fixture fingerprinting utility to detect meaningful changes in fixture configurations.
"""

import hashlib
import json
from typing import Union, List, Optional

from custom_components.dmx.fixture.channel import Channel, ChannelOffset, SwitchingChannel
from custom_components.dmx.fixture.capability import Capability


def generate_fixture_fingerprint(
    fixture_name: str, mode_name: str, channels: List[Union[None, ChannelOffset, SwitchingChannel]]
) -> str:
    """
    Generate a fingerprint for a specific fixture mode configuration.

    This fingerprints only the channels used by the specific mode, so that
    changes to unused channels or modes don't affect entities.

    Args:
        fixture_name: Name of the fixture
        mode_name: Name of the mode being used
        channels: List of channels returned by fixture.select_mode()

    Returns:
        8-character hex fingerprint
    """
    # Build a serializable representation of the channel structure
    channel_data = {"fixture_name": fixture_name, "mode_name": mode_name, "channels": []}

    for i, channel in enumerate(channels):
        if channel is None:
            channel_data["channels"].append(None)
        elif isinstance(channel, ChannelOffset):
            channel_data["channels"].append(_serialize_channel_offset(channel))
        elif isinstance(channel, SwitchingChannel):
            channel_data["channels"].append(_serialize_switching_channel(channel))

    # Create hash from the serialized data
    serialized = json.dumps(channel_data, sort_keys=True)
    hash_obj = hashlib.md5(serialized.encode("utf-8"))
    return hash_obj.hexdigest()[:8]


def _serialize_channel_offset(channel_offset: ChannelOffset) -> dict:
    """Serialize a ChannelOffset to a dict representation."""
    return {
        "type": "channel_offset",
        "byte_offset": channel_offset.byte_offset,
        "channel": _serialize_channel(channel_offset.channel),
    }


def _serialize_switching_channel(switching_channel: SwitchingChannel) -> dict:
    """Serialize a SwitchingChannel to a dict representation."""
    return {
        "type": "switching_channel",
        "name": switching_channel.name,
        "controlled_channels": {
            name: _serialize_channel_offset(channel_offset)
            for name, channel_offset in switching_channel.controlled_channels.items()
        },
    }


def _serialize_channel(channel: Channel) -> dict:
    """Serialize a Channel to a dict representation."""
    return {
        "name": channel.name,
        "matrix_key": channel.matrix_key,
        "fine_channel_aliases": channel.fine_channel_aliases,
        "dmx_value_resolution": channel.dmx_value_resolution.value,
        "default_value": channel.default_value,
        "highlight_value": channel.highlight_value,
        "constant": channel.constant,
        "capabilities": [_serialize_capability(cap) for cap in channel.capabilities],
    }


def _serialize_capability(capability: Capability) -> dict:
    """Serialize a Capability to a dict representation."""
    result = {
        "type": capability.__class__.__name__,
        "dmx_range_start": capability.dmx_range_start,
        "dmx_range_end": capability.dmx_range_end,
        "menu_click": (
            capability.menu_click.name if hasattr(capability.menu_click, "name") else str(capability.menu_click)
        ),
        "menu_click_value": capability.menu_click_value,
        "switch_channels": capability.switch_channels,
    }

    # Add type-specific properties that would affect entity behavior
    if hasattr(capability, "color"):
        result["color"] = capability.color.name if hasattr(capability.color, "name") else str(capability.color)
    if hasattr(capability, "color_temperature") and capability.color_temperature is not None:
        result["color_temperature"] = [{"value": ct.value, "unit": ct.unit} for ct in capability.color_temperature]
    if hasattr(capability, "dynamic_entities") and capability.dynamic_entities is not None:
        result["dynamic_entities"] = [
            {
                "start": {"value": de.entity_start.value, "unit": de.entity_start.unit},
                "end": {"value": de.entity_end.value, "unit": de.entity_end.unit},
            }
            for de in capability.dynamic_entities
        ]

    return result
