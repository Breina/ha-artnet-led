from dataclasses import dataclass


@dataclass
class Channel:
    """Represents a DMX channel configuration"""
    index: int
    name: str
    min_value: int = 0
    max_value: int = 255
