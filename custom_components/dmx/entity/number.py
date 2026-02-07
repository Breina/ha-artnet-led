import logging

from homeassistant.components.number import NumberExtraStoredData, NumberMode, RestoreNumber
from homeassistant.core import State, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import slugify

from custom_components.dmx.const import DOMAIN
from custom_components.dmx.fixture.capability import Capability, DynamicEntity
from custom_components.dmx.io.dmx_io import DmxUniverse

log = logging.getLogger(__name__)


class DmxNumberEntity(RestoreNumber):
    def __init__(
        self,
        fixture_name: str,
        channel_name: str,
        entity_id_prefix: str | None,
        capability: Capability,
        universe: DmxUniverse,
        dmx_indexes: list[int],
        device: DeviceInfo,
        fixture_fingerprint: str,
        available: bool = True,
    ) -> None:
        super().__init__()

        assert capability.dynamic_entities and len(capability.dynamic_entities) == 1

        self._attr_name = f"{fixture_name} {channel_name}"
        self._attr_device_info = device

        if entity_id_prefix:
            slug_prefix = slugify(entity_id_prefix)
            slug_channel = slugify(channel_name)
            self._attr_unique_id = f"{slug_prefix}_{slug_channel}_{fixture_fingerprint}"
            self.entity_id = f"number.{self._attr_unique_id}"
        else:
            self._attr_unique_id = (
                f"{DOMAIN}_{universe.port_address!s}_{fixture_name.lower()}_"
                f"{channel_name.lower()}_{fixture_fingerprint}"
            )

        self._attr_icon = capability.icon()
        self._attr_extra_state_attributes = capability.extra_attributes()

        self.universe = universe
        self.dmx_indexes = dmx_indexes

        self._attr_mode = NumberMode.SLIDER
        self._attr_available = available

        self.capability = capability
        self.dynamic_entity = capability.dynamic_entities[0]
        assert isinstance(self.dynamic_entity, DynamicEntity)

        start_val: float = self.dynamic_entity.entity_start.value
        end_val: float = self.dynamic_entity.entity_end.value

        self._attr_native_min_value, self._attr_native_max_value = sorted((start_val, end_val))

        self._attr_native_unit_of_measurement = self.dynamic_entity.entity_start.unit

        possible_dmx_states: int = pow(2, len(dmx_indexes) * 8)
        native_value_range: float = self._attr_native_max_value - self._attr_native_min_value
        self._attr_native_step = native_value_range / float(possible_dmx_states)

        if capability.menu_click and capability.menu_click_value is not None:
            self._attr_native_value = self.dynamic_entity.from_dmx(capability.menu_click_value)
        else:
            self._attr_native_value = self.dynamic_entity.from_dmx(0)

        self._is_updating = False
        self.universe.register_channel_listener(dmx_indexes, self.update_value)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Restore last state if available
        last_state: State | None = await self.async_get_last_state()
        last_number: NumberExtraStoredData | None = await self.async_get_last_number_data()

        if last_number is not None and last_number.native_value is not None:
            self._attr_native_value = last_number.native_value
            # Update the DMX values to match the restored state
            dmx_values: list[int] = self.dynamic_entity.to_dmx_fine(self._attr_native_value, len(self.dmx_indexes))
            dmx_updates: dict[int, int] = {
                idx: dmx_values[i] for i, idx in enumerate(self.dmx_indexes) if i < len(dmx_values)
            }
            await self.universe.update_multiple_values(dmx_updates)
        elif last_state is not None and last_state.state not in ("unknown", "unavailable"):
            try:
                # Try to convert the state to a float
                restored_value: float = float(last_state.state)
                if self._attr_native_min_value <= restored_value <= self._attr_native_max_value:
                    self._attr_native_value = restored_value
                    # Update the DMX values to match the restored state
                    dmx_values_2: list[int] = self.dynamic_entity.to_dmx_fine(
                        self._attr_native_value, len(self.dmx_indexes)
                    )
                    dmx_updates_2: dict[int, int] = {
                        idx: dmx_values_2[i] for i, idx in enumerate(self.dmx_indexes) if i < len(dmx_values_2)
                    }
                    await self.universe.update_multiple_values(dmx_updates_2)
            except (ValueError, TypeError):
                pass

    @callback
    def update_value(self, source: str | None) -> None:
        if not self.available:
            return

        if getattr(self, "_is_updating", False):
            return

        self._attr_attribution = source

        dmx_values: list[int] = [self.universe.get_channel_value(idx) for idx in self.dmx_indexes]
        self._attr_native_value = self.dynamic_entity.from_dmx_fine(dmx_values)

        if not self.hass:
            log.debug(f"Not updating {self.name} because it hasn't been added to hass yet.")
            return

        self.async_schedule_update_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        dmx_values: list[int] = self.dynamic_entity.to_dmx_fine(value, len(self.dmx_indexes))

        self._attr_native_value = self.dynamic_entity.from_dmx_fine(
            dmx_values
        )  # Set to closest value that can be represented through DMX values

        dmx_updates: dict[int, int] = {}
        for i, dmx_index in enumerate(self.dmx_indexes):
            if i < len(dmx_values):  # Safety check
                dmx_updates[dmx_index] = dmx_values[i]

        self._is_updating = True
        try:
            await self.universe.update_multiple_values(dmx_updates)
        finally:
            self._is_updating = False

    @property
    def available(self) -> bool:
        return self._attr_available

    @available.setter
    def available(self, is_available: bool) -> None:
        self._attr_available = is_available

        if not self.hass:
            log.debug(f"Not updating {self.name} because it hasn't been added to hass yet.")
            return

        self.async_schedule_update_ha_state()

    @property
    def native_value(self) -> float | None:
        if self._attr_native_value is None:
            return None
        return round(self._attr_native_value, 2)

    def __str__(self) -> str:
        return f"{self._attr_name}: {self.capability.__repr__()}"

    def __repr__(self) -> str:
        return self.__str__()
