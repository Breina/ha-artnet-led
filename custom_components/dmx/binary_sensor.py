import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.dmx import DOMAIN

log = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
):
    entities = [e
                for e
                in hass.data[DOMAIN][config_entry.entry_id]['entities']
                if isinstance(e, BinarySensorEntity)
                ]

    log.info(f"Adding {len(entities)} entities...")
    async_add_entities(entities)

    pass
