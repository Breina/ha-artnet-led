import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.dmx.const import DOMAIN
from custom_components.dmx.io.dmx_io import DmxUniverse

_LOGGER = logging.getLogger(__name__)


class DmxUniverseSwitch(SwitchEntity):
    """Switch entity to control DMX universe output."""

    def __init__(self, universe: DmxUniverse, universe_name: str):
        """Initialize the switch."""
        self._universe = universe
        self._universe_name = universe_name
        self._is_on = True
        self._attr_unique_id = f"{DOMAIN}_dmx_universe_{universe.port_address.port_address}"
        self._attr_name = f"DMX Universe {universe_name}"

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"universe_{universe.port_address.port_address}")},
            name=f"DMX Universe {universe_name}",
            manufacturer="ArtNet DMX",
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
        self.async_write_ha_state()
        _LOGGER.debug("Enabled output for universe %s", self._universe_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        self._is_on = False
        self._universe.set_output_enabled(False)
        self.async_write_ha_state()
        _LOGGER.debug("Disabled output for universe %s", self._universe_name)

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
        switch = DmxUniverseSwitch(universe, universe_name)
        switches.append(switch)

    async_add_entities(switches)
