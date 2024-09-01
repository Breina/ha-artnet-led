from homeassistant.components.select import SelectEntity

from custom_components.dmx import DOMAIN
from custom_components.dmx.entity.number import DmxNumberEntity
from custom_components.dmx.fixture.channel import Channel
from custom_components.dmx.fixture.exceptions import FixtureConfigurationError
from custom_components.dmx.io.dmx_io import Universe


class DmxSelectEntity(SelectEntity):
    def __init__(self,
                 channel: Channel,
                 capability_entities: dict[str, DmxNumberEntity],
                 universe: Universe,
                 dmx_index: int
                 ) -> None:
        super().__init__()

        self._attr_name = channel.name
        self._attr_unique_id = f"{DOMAIN}_{channel.name}"  # TODO add device

        # TODO icon
        # self._attr_icon

        self.capability_types = {
            str(capability): capability for capability in channel.capabilities
        }
        self.capability_entities = capability_entities

        self.dmx_index = dmx_index

        self._attr_options = list(self.capability_types.keys())

        self.universe = universe
        self.universe.register_channel_listener(dmx_index, self.update_value)

    def update_value(self, value: int) -> None:
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

        await self.universe.update_value(self.dmx_index, dmx_value)

    def update_current_option(self, new_option: str) -> None:
        self.capability_entities[self._attr_current_option].available = False
        self._attr_current_option = new_option
        self.capability_entities[self._attr_current_option].available = True
