from typing import List

from homeassistant.components.number import NumberMode, \
    RestoreNumber
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.dmx import DOMAIN
from custom_components.dmx.fixture.capability import DynamicEntity, Capability
from custom_components.dmx.io.dmx_io import Universe


class DmxNumberEntity(RestoreNumber):
    def __init__(self, name: str, capability: Capability,
                 universe: Universe, dmx_indexes: List[int],
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

        self.universe.register_channel_listener(dmx_indexes, self.update_value)

    def update_value(self, value: int) -> None:
        # TODO maybe update self._attr_attribution from source ArtNet node?
        self._attr_native_value = self.dynamic_entity.from_dmx(value)
        self.async_schedule_update_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        dmx_value = self.dynamic_entity.to_dmx(value)
        await self.universe.update_value(self.dmx_indexes, dmx_value)

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
