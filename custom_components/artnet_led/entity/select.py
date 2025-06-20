import logging

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.artnet_led import DOMAIN
from custom_components.artnet_led.entity.number import DmxNumberEntity
from custom_components.artnet_led.fixture.capability import Capability
from custom_components.artnet_led.fixture.channel import Channel
from custom_components.artnet_led.fixture.exceptions import FixtureConfigurationError
from custom_components.artnet_led.io.dmx_io import DmxUniverse

log = logging.getLogger(__name__)


class DmxSelectEntity(SelectEntity):
    def __init__(self,
                 name: str,
                 channel: Channel,
                 capability_entities: dict[str, DmxNumberEntity],
                 universe: DmxUniverse,
                 dmx_index: int,
                 device: DeviceInfo
                 ) -> None:
        super().__init__()

        self._attr_name = name
        self._attr_device_info = device
        self._attr_unique_id = f"{DOMAIN}_{channel.name}"  # TODO add device

        # TODO icon
        # self._attr_icon

        name_counts: dict[str, int] = {}
        self.capability_types: dict[str, Capability] = {}

        for capability in channel.capabilities:
            name = str(capability)
            if name in name_counts:
                name_counts[name] += 1
                unique_name = f"{name} {name_counts[name]}"
            else:
                name_counts[name] = 1
                unique_name = name
            self.capability_types[unique_name] = capability

        self.capability_entities = capability_entities
        for capability_entity in self.capability_entities.values():
            capability_entity.available = False

        self.dmx_index = dmx_index

        self._attr_options = list(self.capability_types.keys())

        self.switching_entities = {}

        self._attr_current_option = self._attr_options[0]
        self.__set_availability(True)

        self.universe = universe
        self.universe.register_channel_listener(dmx_index, self.update_value)

        self.universe.update_value(self.dmx_index, channel.default_value, send_immediately=False)
        self.update_option_to_dmx_value(channel.default_value)

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

    def update_value(self, source: str | None) -> None:
        self._attr_attribution = source

        value = self.universe.get_channel_value(self.dmx_index)

        self.update_option_to_dmx_value(value)
        if self.hass:
            self.async_schedule_update_ha_state()
        else:
            log.debug(f"Not updating {self.name} because it hasn't been added to hass yet.")

    def update_option_to_dmx_value(self, value):
        capability = [
            capability for capability in self.capability_types.values()
            if capability.is_applicable(value)
        ]
        if not any(capability):
            raise FixtureConfigurationError(
                f"Fixture {self._attr_name} received an invalid DMX value: "
                f"{value}")

        self.update_current_option(str(capability[0]))

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
