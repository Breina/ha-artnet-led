import logging
import os

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import DiscoveryInfoType, ConfigType

from custom_components.dmx import DOMAIN
from custom_components.dmx.const import HASS_DATA_ENTITIES
from custom_components.dmx.fixture.parser import parse
from custom_components.dmx.fixture_delegator.delegator import create_entities

log = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
):
    current_working_directory = os.getcwd()
    # log.error(f"CURRENT WORKING DIRECTORY: {current_working_directory}")

    fixture = parse("fixtures/hydrabeam-300-rgbw.json")
    channels = fixture.select_mode("42-channel")

    entities = create_entities(100, channels)

    log.info(f"Adding {len(entities)} entities...")
    async_add_entities(entities)

    pass

# async def async_setup_platform(
#         hass: HomeAssistant,
#         config: ConfigType,
#         add_entities: AddEntitiesCallback,
#         discovery_info: DiscoveryInfoType | None = None
# ) -> None:
#     """Set up the sensor platform."""
#
#     entities = hass.data[DOMAIN][HASS_DATA_ENTITIES]
#     number_entities = list(filter(lambda e: isinstance(e, NumberEntity), entities))
#
#     log.info(f"Adding {len(number_entities)} number entities")
#
#     add_entities(number_entities)
#
