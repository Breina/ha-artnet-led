from dataclasses import dataclass

from homeassistant.helpers.entity import DeviceInfo


@dataclass
class Fixture:
    fixture_key: str
    device_info: DeviceInfo
    fixture_json: dict
