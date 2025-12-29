import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.dmx.const import CONF_FIXTURE_ENTITIES, DOMAIN

log = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry[dict[str, Any]],
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities = [
        e for e in hass.data[DOMAIN][config_entry.entry_id][CONF_FIXTURE_ENTITIES] if isinstance(e, SelectEntity)
    ]

    log.info(f"Adding {len(entities)} entities...")
    async_add_entities(entities)

    pass
