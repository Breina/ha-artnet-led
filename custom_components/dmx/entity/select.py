import logging

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import DeviceInfo

from custom_components.dmx import DOMAIN
from custom_components.dmx.entity.icon_helper import determine_icon
from custom_components.dmx.entity.number import DmxNumberEntity
from custom_components.dmx.fixture.capability import Capability
from custom_components.dmx.fixture.channel import Channel
from custom_components.dmx.fixture.exceptions import FixtureConfigurationError
from custom_components.dmx.io.dmx_io import DmxUniverse

log = logging.getLogger(__name__)


class DmxSelectEntity(SelectEntity):
    def __init__(
        self,
        fixture_name: str,
        channel_name: str,
        entity_id_prefix: str,
        channel: Channel,
        capability_entities: dict[str, DmxNumberEntity],
        universe: DmxUniverse,
        dmx_index: int,
        device: DeviceInfo,
        fixture_fingerprint: str,
    ) -> None:
        super().__init__()

        self._attr_name = f"{fixture_name} {channel_name}"
        self._attr_device_info = device
        if entity_id_prefix:
            self._attr_unique_id = f"{entity_id_prefix}_{channel_name.lower()}_{fixture_fingerprint}"
            self.entity_id = f"select.{self._attr_unique_id}"
        else:
            self._attr_unique_id = (
                f"{DOMAIN}_{universe.port_address!s}_{fixture_name.lower()}_{channel_name.lower()}_{fixture_fingerprint}"
            )

        self._attr_icon = determine_icon(channel)

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

        self.universe = universe
        self.universe.register_channel_listener(dmx_index, self.update_value)

        # TODO RuntimeWarning: coroutine 'DmxUniverse.update_value' was never awaited
        self.universe.update_value(self.dmx_index, channel.default_value, send_immediately=False)
        self.update_option_to_dmx_value(channel.default_value)

    def link_switching_entities(self, entities: list[DmxNumberEntity]) -> None:
        for capability_name, capability in self.capability_types.items():
            if not capability.switch_channels:
                continue

            for channel_name in capability.switch_channels.values():
                for entity in entities:
                    if entity.name.endswith(channel_name):
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
        capability = [capability for capability in self.capability_types.values() if capability.is_applicable(value)]
        if not any(capability):
            raise FixtureConfigurationError(f"Fixture {self._attr_name} received an invalid DMX value: " f"{value}")

        # Only update the option, don't handle availability here
        self._update_current_option_sync(str(capability[0]))

    async def async_select_option(self, option: str) -> None:
        await self._update_current_option_async(option)

        capability = self.capability_types[option]
        dmx_value = capability.menu_click_value if capability.menu_click else capability.dmx_range_start

        await self.universe.update_value(self.dmx_index, dmx_value, send_immediately=True)

    def _update_current_option_sync(self, new_option: str) -> None:
        """Synchronous version for initialization and DMX value updates"""
        self.__set_availability(False)
        self._attr_current_option = new_option
        self.__set_availability(True)

    async def _update_current_option_async(self, new_option: str) -> None:
        """Async version for user interactions that need to reapply values"""
        await self.__async_set_availability(False)
        self._attr_current_option = new_option
        await self.__async_set_availability(True)

    def __set_availability(self, availability: bool) -> None:
        """Synchronous availability setting (no value reapplication)"""
        if self._attr_current_option in self.capability_entities:
            self.capability_entities[self._attr_current_option].available = availability

        if self._attr_current_option in self.switching_entities:
            switching_entity: DmxNumberEntity = self.switching_entities[self._attr_current_option]
            switching_entity.available = availability

    async def __async_set_availability(self, availability: bool) -> None:
        """Async availability setting with value reapplication"""
        if self._attr_current_option in self.capability_entities:
            self.capability_entities[self._attr_current_option].available = availability

        if self._attr_current_option in self.switching_entities:
            switching_entity: DmxNumberEntity = self.switching_entities[self._attr_current_option]
            switching_entity.available = availability

            if availability:
                # Reapply the current value when the entity becomes available
                await switching_entity.async_set_native_value(switching_entity.native_value)

    def __str__(self) -> str:
        return f"{self._attr_name}: {self.capability_attributes['options']}"

    def __repr__(self) -> str:
        return self.__str__()
