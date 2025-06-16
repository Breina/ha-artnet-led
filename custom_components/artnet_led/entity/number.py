from typing import List

from homeassistant.components.number import NumberMode, \
    RestoreNumber
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.artnet_led import DOMAIN
from custom_components.artnet_led.fixture.capability import DynamicEntity, Capability
from custom_components.artnet_led.io.dmx_io import DmxUniverse
from typing import List

from homeassistant.components.number import NumberMode, \
    RestoreNumber
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.artnet_led import DOMAIN
from custom_components.artnet_led.fixture.capability import DynamicEntity, Capability
from custom_components.artnet_led.io.dmx_io import DmxUniverse


class DmxNumberEntity(RestoreNumber):
    def __init__(self, name: str, capability: Capability,
                 universe: DmxUniverse, dmx_indexes: List[int],
                 device: DeviceInfo,
                 available: bool = True,  # TODO something wrong here?
                 ) -> None:
        super().__init__()

        assert capability.dynamic_entities \
               and len(capability.dynamic_entities) == 1

        self._attr_name = name
        self._attr_device_info = device
        self._attr_unique_id = f"{DOMAIN}_{name}"  # TODO add device

        self._attr_icon = capability.icon()
        self._attr_extra_state_attributes = capability.extra_attributes()  # TODO not working?

        self.universe = universe
        self.dmx_indexes = dmx_indexes

        self._attr_mode = NumberMode.SLIDER
        self._attr_available = available

        self.capability = capability
        self.dynamic_entity = capability.dynamic_entities[0]
        assert isinstance(self.dynamic_entity, DynamicEntity)

        start_val = self.dynamic_entity.entity_start.value
        end_val = self.dynamic_entity.entity_end.value

        self._attr_native_min_value, self._attr_native_max_value = (
            sorted((start_val, end_val))
        )

        self._attr_native_unit_of_measurement = \
            self.dynamic_entity.entity_start.unit

        possible_dmx_states = pow(2, len(dmx_indexes) * 8)
        native_value_range = (
                self._attr_native_max_value - self._attr_native_min_value)
        self._attr_native_step = native_value_range / float(possible_dmx_states)

        if capability.menu_click:
            self._attr_native_value = capability.menu_click_value
        else:
            self._attr_native_value = 0

        self._is_updating = False
        self.universe.register_channel_listener(dmx_indexes, self.update_value)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Restore last state if available
        last_state = await self.async_get_last_state()
        last_number = await self.async_get_last_number_data()

        if last_number is not None and last_number.native_value is not None:
            self._attr_native_value = last_number.native_value
            # Update the DMX values to match the restored state
            if len(self.dmx_indexes) > 1:
                # Handle multi-byte DMX values
                dmx_values = self.dynamic_entity.to_dmx_fine(self._attr_native_value, len(self.dmx_indexes))
                dmx_updates = {idx: dmx_values[i] for i, idx in enumerate(self.dmx_indexes) if i < len(dmx_values)}
                await self.universe.update_multiple_values(dmx_updates)
            else:
                # Single channel
                dmx_value = self.dynamic_entity.to_dmx(self._attr_native_value)
                await self.universe.update_value(self.dmx_indexes, dmx_value, send_immediately=True)
        elif last_state is not None and last_state.state not in ('unknown', 'unavailable'):
            try:
                # Try to convert the state to a float
                restored_value = float(last_state.state)
                if self._attr_native_min_value <= restored_value <= self._attr_native_max_value:
                    self._attr_native_value = restored_value
                    # Update the DMX values to match the restored state
                    if len(self.dmx_indexes) > 1:
                        # Handle multi-byte DMX values
                        dmx_values = self.dynamic_entity.to_dmx_fine(self._attr_native_value, len(self.dmx_indexes))
                        dmx_updates = {idx: dmx_values[i] for i, idx in enumerate(self.dmx_indexes) if i < len(dmx_values)}
                        await self.universe.update_multiple_values(dmx_updates)
                    else:
                        # Single channel
                        dmx_value = self.dynamic_entity.to_dmx(self._attr_native_value)
                        await self.universe.update_value(self.dmx_indexes, dmx_value, send_immediately=True)
            except (ValueError, TypeError):
                # Unable to convert state to float, use default value
                pass

    def update_value(self, dmx_index: int, value: int) -> None:
        # TODO maybe update self._attr_attribution from source ArtNet node?
        # Skip processing during our own updates
        if getattr(self, '_is_updating', False):
            return

        # If we have multiple DMX indexes, we need to get all values
        # for proper fine channel handling
        if len(self.dmx_indexes) > 1:
            # Get all current DMX values for our channels
            dmx_values = [self.universe.get_channel_value(idx) for idx in self.dmx_indexes]
            # Convert from multi-byte DMX values to entity value
            self._attr_native_value = self.dynamic_entity.from_dmx_fine(dmx_values)
        else:
            # Single channel - use existing method
            self._attr_native_value = self.dynamic_entity.from_dmx(value)

        self.async_schedule_update_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value

        # If we have multiple DMX indexes, we need fine channel handling
        if len(self.dmx_indexes) > 1:
            # Convert to multi-byte DMX values
            dmx_values = self.dynamic_entity.to_dmx_fine(value, len(self.dmx_indexes))

            # Create a dictionary of channel:value pairs for the universe update
            dmx_updates = {}
            for i, dmx_index in enumerate(self.dmx_indexes):
                if i < len(dmx_values):  # Safety check
                    dmx_updates[dmx_index] = dmx_values[i]

            self._is_updating = True
            try:
                await self.universe.update_multiple_values(dmx_updates)
            finally:
                self._is_updating = False
        else:
            # Single channel - use existing method
            dmx_value = self.dynamic_entity.to_dmx(value)

            self._is_updating = True
            try:
                await self.universe.update_value(self.dmx_indexes, dmx_value, send_immediately=True)
            finally:
                self._is_updating = False

    @property
    def available(self) -> bool:
        return self._attr_available

    @available.setter
    def available(self, is_available: bool) -> None:
        self._attr_available = is_available

        # Only refresh state after added to hass
        if self.hass:
            self.async_schedule_update_ha_state()

    @property
    def native_value(self) -> float | None:
        return round(self._attr_native_value, 2)

    def __str__(self) -> str:
        return f"{self._attr_name}: {self.capability.__repr__()}"

    def __repr__(self) -> str:
        return self.__str__()
