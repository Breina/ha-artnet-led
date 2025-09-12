import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.dmx.const import CONF_FIXTURE_ENTITIES, DOMAIN

log = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities = [
        e for e in hass.data[DOMAIN][config_entry.entry_id][CONF_FIXTURE_ENTITIES] if isinstance(e, SensorEntity)
    ]

    log.info(f"Adding {len(entities)} entities...")
    async_add_entities(entities)

    pass
