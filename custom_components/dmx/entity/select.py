import logging

from homeassistant.components.select import SelectEntity
from homeassistant.core import State
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify

from custom_components.dmx.const import DOMAIN
from custom_components.dmx.entity.icon_helper import determine_icon
from custom_components.dmx.entity.number import DmxNumberEntity
from custom_components.dmx.fixture.capability import Capability
from custom_components.dmx.fixture.channel import Channel, dmx_bytes_to_range_value, range_value_to_dmx_bytes
from custom_components.dmx.io.dmx_io import DmxUniverse

log = logging.getLogger(__name__)


def capability_options(channel: Channel) -> dict[str, Capability]:
    """Returns the channel's capabilities by a name which is unique within the channel."""
    capabilities = channel.capabilities if isinstance(channel.capabilities, list) else [channel.capabilities]
    name_counts: dict[str, int] = {}
    options: dict[str, Capability] = {}
    for capability in capabilities:
        name = str(capability)
        name_counts[name] = name_counts.get(name, 0) + 1
        options[f"{name} {name_counts[name]}" if name_counts[name] > 1 else name] = capability
    return options


class DmxSelectEntity(SelectEntity, RestoreEntity):
    def __init__(
        self,
        fixture_name: str,
        channel_name: str,
        entity_id_prefix: str,
        channel: Channel,
        capability_entities: dict[str, DmxNumberEntity],
        universe: DmxUniverse,
        dmx_indexes: list[int],
        device: DeviceInfo,
        fixture_fingerprint: str,
    ) -> None:
        super().__init__()

        self._attr_name = f"{fixture_name} {channel_name}"
        self._attr_device_info = device
        if entity_id_prefix:
            slug_prefix = slugify(entity_id_prefix)
            slug_channel = slugify(channel_name)
            self._attr_unique_id = f"{slug_prefix}_{slug_channel}_{fixture_fingerprint}"
            # Fingerprint stays in unique_id; entity_id must stay predictable.
            self.entity_id = f"select.{slug_prefix}_{slug_channel}"
        else:
            self._attr_unique_id = (
                f"{DOMAIN}_{universe.port_address!s}_{fixture_name.lower()}_"
                f"{channel_name.lower()}_{fixture_fingerprint}"
            )

        self._attr_icon = determine_icon(channel)

        self.capability_types: dict[str, Capability] = capability_options(channel)

        self.capability_entities = capability_entities
        for capability_entity in self.capability_entities.values():
            capability_entity.available = False

        self.dmx_indexes = dmx_indexes
        self.dmx_index = dmx_indexes[0]
        self._range_bytes = channel.range_bytes

        self._attr_options = list(self.capability_types.keys())

        self.switching_entities: dict[str, DmxNumberEntity] = {}

        self._attr_current_option = self._attr_options[0]

        self.universe = universe
        self.universe.register_channel_listener(dmx_indexes, self.update_value)

        # Initialize with default value - note: this is sync initialization so we can't await
        # The value will be properly set when the entity is added to Home Assistant
        self.update_option_to_dmx_value(channel.default_value)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Same guard as DmxNumberEntity.async_added_to_hass(): don't clobber a
        # value some other code path (e.g. a user command racing this restore)
        # already wrote to this channel.
        if self._is_channel_set():
            return

        last_state: State | None = await self.async_get_last_state()

        # Re-check after the await: state may have changed while we were suspended.
        if self._is_channel_set():
            return

        if last_state is None or last_state.state not in self.capability_types:
            return

        option = last_state.state

        self._update_current_option_sync(option)
        await self._write_capability(self.capability_types[option])

    def link_switching_entities(self, entities: list[DmxNumberEntity]) -> None:
        for capability_name, capability in self.capability_types.items():
            if not capability.switch_channels:
                continue

            for channel_name in capability.switch_channels.values():
                if channel_name is None:
                    continue

                for entity in entities:
                    if isinstance(entity.name, str) and entity.name.endswith(channel_name):
                        self.switching_entities[capability_name] = entity
                        entity.available = False
                        break

        self.__set_availability(True)

    def update_value(self, source: str | None) -> None:
        self._attr_attribution = source

        values = [self.universe.get_channel_value(index) for index in self.dmx_indexes]

        self.update_option_to_dmx_value(dmx_bytes_to_range_value(values, self._range_bytes))
        if self.hass:
            self.async_schedule_update_ha_state()
        else:
            log.debug(f"Not updating {self.name} because it hasn't been added to hass yet.")

    def update_option_to_dmx_value(self, value: int) -> None:
        option = next((name for name, c in self.capability_types.items() if c.is_applicable(value)), None)
        if option is None:
            # A hidden capability or a gap in the fixture's ranges: no option represents this value.
            log.debug(f"Keeping option of {self._attr_name}, as none applies to DMX value {value}")
            return

        # Only update the option, don't handle availability here
        self._update_current_option_sync(option)

    async def async_select_option(self, option: str) -> None:
        await self._update_current_option_async(option)
        await self._write_capability(self.capability_types[option])

    def _is_channel_set(self) -> bool:
        return any(self.universe.is_channel_set(index) for index in self.dmx_indexes)

    async def _write_capability(self, capability: Capability) -> None:
        value: int = (
            capability.menu_click_value if capability.menu_click_value is not None else capability.dmx_range_start
        )
        dmx_values = range_value_to_dmx_bytes(value, len(self.dmx_indexes), self._range_bytes)

        updates = dict(zip(self.dmx_indexes, dmx_values, strict=True))
        await self.universe.update_multiple_values(updates, send_update=False)
        self.universe.send_universe_data()

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
                current_value = switching_entity.native_value
                if current_value is not None:
                    await switching_entity.async_set_native_value(current_value)

    def __str__(self) -> str:
        return f"{self._attr_name}: {self._attr_options}"

    def __repr__(self) -> str:
        return self.__str__()
