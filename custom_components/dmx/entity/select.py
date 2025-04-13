import logging

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.dmx import DOMAIN
from custom_components.dmx.entity.number import DmxNumberEntity
from custom_components.dmx.fixture.channel import Channel
from custom_components.dmx.fixture.exceptions import FixtureConfigurationError
from custom_components.dmx.io.dmx_io import DmxUniverse

log = logging.getLogger(__name__)


class DmxSelectEntity(SelectEntity):
    def __init__(self,
                 channel: Channel,
                 capability_entities: dict[str, DmxNumberEntity],
                 universe: DmxUniverse,
                 dmx_index: int,
                 device: DeviceInfo
                 ) -> None:
        super().__init__()

        self._attr_name = channel.name
        self._attr_device_info = device
        self._attr_unique_id = f"{DOMAIN}_{channel.name}"  # TODO add device

        # TODO icon
        # self._attr_icon

        self.capability_types = {
            str(capability): capability for capability in channel.capabilities
        }
        self.capability_entities = capability_entities
        for capability_entity in self.capability_entities.values():
            capability_entity.available = False

        self.dmx_index = dmx_index

        self._attr_options = list(self.capability_types.keys())

        self.switching_entities = {}

        self._attr_current_option = self._attr_options[0] # TODO isn't there something for this?
        self.__set_availability(True)

        self.universe = universe
        self.universe.register_channel_listener(dmx_index, self.update_value)

    def link_switching_entities(self, entities: list[DmxNumberEntity]) -> None:
        for capability_name, capability in self.capability_types.items():
            if not capability.switch_channels:
                continue

            for channel_name in capability.switch_channels.values():
                for entity in entities:
                    if entity.name == channel_name:
                        self.switching_entities[capability_name] = entity
                        entity.available = False
                        break

        self.__set_availability(True)

    def update_value(self, dmx_index: int, value: int) -> None:
        # TODO maybe update self._attr_attribution from source ArtNet node?
        capability = [
            capability for capability in self.capability_types.values()
            if capability.is_applicable(value)
        ]
        if not any(capability):
            raise FixtureConfigurationError(
                f"Fixture {self._attr_name} received an invalid DMX value: "
                f"{value}")

        self.update_current_option(str(capability[0]))
        self.async_schedule_update_ha_state()

    async def async_select_option(self, option: str) -> None:
        self.update_current_option(option)

        capability = self.capability_types[option]
        if capability.menu_click:
            dmx_value = capability.menu_click_value
        else:
            dmx_value = capability.dmx_range_start

        await self.universe.update_value(self.dmx_index, dmx_value, send_immediately=True)

    def update_current_option(self, new_option: str) -> None:
        self.__set_availability(False)
        self._attr_current_option = new_option
        self.__set_availability(True)

    def __set_availability(self, availability: bool) -> None:
        if self._attr_current_option in self.capability_entities:
            self.capability_entities[self._attr_current_option].available = availability

        if self._attr_current_option in self.switching_entities:
            self.switching_entities[
                self._attr_current_option].available = availability

    def __str__(self) -> str:
        return f"{self._attr_name}: {self.capability_attributes['options']}"

    def __repr__(self) -> str:
        return self.__str__()
