import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.dmx.const import DOMAIN, CONF_FIXTURE_ENTITIES
from custom_components.dmx.io.dmx_io import DmxUniverse

log = logging.getLogger(__name__)


class DmxUniverseSwitch(SwitchEntity):
    """Switch entity to control DMX universe output."""

    def __init__(self, universe: DmxUniverse, universe_name: str, hass: HomeAssistant, config_entry: ConfigEntry):
        """Initialize the switch."""
        self._universe = universe
        self._universe_name = universe_name
        self._is_on = True
        self._hass = hass
        self._config_entry = config_entry
        self._attr_unique_id = f"{DOMAIN}_dmx_universe_{universe.port_address.port_address}"
        self._attr_name = f"DMX Universe {universe_name}"

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"universe_{universe.port_address.port_address}")},
            name=f"DMX Universe {universe_name}",
            manufacturer="DMX",
            model="DMX Universe Controller",
        )

    @property
    def is_on(self) -> bool:
        """Return True if the switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        self._is_on = True
        self._universe.set_output_enabled(True)
        self._universe.send_universe_data()
        await self._set_universe_entities_availability(True)
        self.async_write_ha_state()
        log.debug("Enabled output for universe %s", self._universe_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        self._is_on = False
        self._universe.set_output_enabled(False)
        await self._set_universe_entities_availability(False)
        self.async_write_ha_state()
        log.debug("Disabled output for universe %s", self._universe_name)

    async def _set_universe_entities_availability(self, available: bool) -> None:
        """Set availability of all entities in this universe."""
        domain_data = self._hass.data[DOMAIN][self._config_entry.entry_id]
        entities = domain_data.get(CONF_FIXTURE_ENTITIES, [])

        for entity in entities:
            # Check if entity belongs to this universe
            entity_universe = None
            if hasattr(entity, '_universe'):
                entity_universe = entity._universe
            elif hasattr(entity, 'universe'):
                entity_universe = entity.universe

            if entity_universe == self._universe:
                if hasattr(entity, 'available'):
                    entity.available = available
                    if entity.hass:  # Only update state if entity is added to hass
                        entity.async_write_ha_state()

        log.debug(
            "Set availability to %s for entities in universe %s",
            available, self._universe_name
        )

    @property
    def icon(self) -> str:
        """Return the icon for the switch."""
        return "mdi:lightbulb-group" if self._is_on else "mdi:lightbulb-group-off"


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DMX universe switches."""
    domain_data = hass.data[DOMAIN][config_entry.entry_id]

    universes = domain_data.get("universes", {})

    switches = []
    for port_address, universe in universes.items():
        universe_name = f"{port_address.net}/{port_address.sub_net}/{port_address.universe}"
        switch = DmxUniverseSwitch(universe, universe_name, hass, config_entry)
        switches.append(switch)

    async_add_entities(switches)
