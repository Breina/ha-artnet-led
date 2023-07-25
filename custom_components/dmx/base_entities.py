import re
import time
from typing import Union

from homeassistant.components.number import NumberMode, NumberEntityDescription, NumberDeviceClass, \
    RestoreNumber, NumberExtraStoredData, DOMAIN
from homeassistant.const import ATTR_IDENTIFIERS
from homeassistant.helpers.entity import DeviceInfo
from pyartnet import Channel

from custom_components.dmx import const, PortAddress
from custom_components.dmx.bridge.channel_bridge import ChannelBridge
from custom_components.fixtures.model import Fixture

entity_char_matcher = re.compile('[^\da-zA-Z_]')


class IntensityNumber(RestoreNumber):

    def __init__(self, fixture: Fixture, device_name: str, channel_name: str, port_address: PortAddress,
                 channel: Union[Channel, ChannelBridge],
                 lumen: Union[int, None] = None) -> None:
        super().__init__()

        fixture_name_lower = entity_char_matcher.sub('_', fixture.fixture_key).lower()
        channel_name_lower = entity_char_matcher.sub('_', channel_name).lower()

        unique_id = f"{const.DOMAIN}_{fixture_name_lower}_{channel_name_lower}"

        entity_description = NumberEntityDescription(
            unique_id, name=channel_name, mode=NumberMode.SLIDER
        )

        if lumen:
            entity_description.device_class = NumberDeviceClass.ILLUMINANCE
            entity_description.native_max_value = lumen
            entity_description.icon = 'mdi:brightness-6'
            entity_description.unit_of_measurement = 'lx'  # TODO lumen
        else:
            entity_description.icon = 'mdi:brightness-percent'

        self.entity_description = entity_description
        self._channel = channel
        self.entity_id = f"{DOMAIN}.{fixture_name_lower}_{channel_name_lower}"
        self._attr_unique_id = unique_id
        self._attr_name = f"{device_name} {channel_name}"

        device_info = fixture.device_info.copy()
        device_info[ATTR_IDENTIFIERS] = {
            ('device_name', entity_char_matcher.sub('_', device_name).lower()),
            ('start_channel', channel._start),
            ('universe', str(port_address).replace(':', '_'))
        }

        print(f"HELLLOOO {device_info}")

        self._attr_device_info = device_info

        if isinstance(channel, ChannelBridge):
            channel.callback_values_updated = self._update_values
            self._channel_last_update = time.time()

    async def async_set_native_value(self, value: float) -> None:
        self._channel.set_values([value])  # TODO fine channels

    def _update_values(self, values):
        self._attr_value = values[0]  # TODO fine channels
        self._channel_value_change()

    def _channel_value_change(self):
        if time.time() - self._channel_last_update > 1.1:
            self._channel_last_update = time.time()
        self.async_schedule_update_ha_state()

    async def async_added_to_hass(self) -> None:
        last_number_data: Union[NumberExtraStoredData, None] = await self.async_get_last_number_data()
        if not last_number_data:
            return

        self._channel.set_values([last_number_data.native_value])  # TODO fine channels
