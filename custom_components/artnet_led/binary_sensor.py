import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.artnet_led import DOMAIN
from custom_components.artnet_led.const import CONF_FIXTURE_ENTITIES

log = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
):
    entities = [e
                for e
                in hass.data[DOMAIN][config_entry.entry_id][CONF_FIXTURE_ENTITIES]
                if isinstance(e, BinarySensorEntity)
                ]

    log.info(f"Adding {len(entities)} entities...")
    async_add_entities(entities)

    pass
