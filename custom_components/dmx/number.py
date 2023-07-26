import logging

from homeassistant.components.number import NumberEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import DiscoveryInfoType, ConfigType

from custom_components.dmx import DOMAIN
from custom_components.dmx.const import HASS_DATA_ENTITIES

log = logging.getLogger(__name__)



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
