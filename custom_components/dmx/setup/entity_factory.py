"""Entity creation and management for DMX integration."""

import logging
from typing import Any

from homeassistant.const import CONF_MODE
from homeassistant.helpers.entity import DeviceInfo, Entity

from custom_components.dmx.const import DOMAIN
from custom_components.dmx.fixture.delegator import create_entities
from custom_components.dmx.fixture.fixture import Fixture
from custom_components.dmx.io.dmx_io import DmxUniverse
from custom_components.dmx.server import PortAddress
from custom_components.dmx.setup.config_processor import (
    CONF_DEVICES,
    CONF_ENTITY_ID_PREFIX,
    CONF_FIXTURE,
    CONF_START_ADDRESS,
)
from custom_components.dmx.util.fixture_fingerprint import generate_fixture_fingerprint

log = logging.getLogger(__name__)


class EntityFactory:
    """Factory for creating DMX entities from configuration."""

    def __init__(self, processed_fixtures: dict[str, Fixture]):
        self.processed_fixtures = processed_fixtures

    def create_entities_for_universe(
        self,
        universe_yaml: dict[str, Any],
        universe: DmxUniverse,
        device_fingerprints: dict[str, str],
    ) -> list[Entity]:
        """Create entities for all devices in a universe."""
        entities: list[Entity] = []

        devices_yaml = universe_yaml[CONF_DEVICES]
        for device_dict in devices_yaml:
            ((device_name, device_yaml),) = device_dict.items()

            start_address = device_yaml[CONF_START_ADDRESS]
            fixture_name = device_yaml[CONF_FIXTURE]
            mode = device_yaml.get(CONF_MODE)
            entity_id_prefix = device_yaml.get(CONF_ENTITY_ID_PREFIX)

            if fixture_name not in self.processed_fixtures:
                log.warning("Could not find fixture '%s'. Ignoring device %s", fixture_name, device_name)
                continue

            fixture = self.processed_fixtures[fixture_name]
            if not mode:
                assert len(fixture.modes) > 0
                mode = next(iter(fixture.modes.keys()))

            channels = fixture.select_mode(mode)

            fixture_fingerprint = generate_fixture_fingerprint(fixture_name, mode, channels)
            device_fingerprints[device_name] = fixture_fingerprint

            identifiers = {(DOMAIN, device_name)}
            if entity_id_prefix is not None:
                identifiers.add((DOMAIN, f"{entity_id_prefix}_{device_name}"))

            device = DeviceInfo(
                configuration_url=fixture.config_url,
                model=fixture.name,
                identifiers=identifiers,
                name=device_name,
            )

            entities.extend(
                create_entities(
                    device_name, start_address, channels, device, universe, entity_id_prefix, fixture_name, mode
                )
            )

        return entities

    def create_entities_for_protocol(
        self,
        protocol_yaml: dict[str, Any],
        universes: dict[PortAddress, DmxUniverse],
        device_fingerprints: dict[str, str],
        protocol_name: str = "unknown",
    ) -> list[Entity]:
        """Create entities for all universes in a protocol configuration."""
        entities: list[Entity] = []

        for universe_dict in protocol_yaml.get("universes", []):
            ((universe_value, universe_yaml),) = universe_dict.items()

            # Find the corresponding universe
            universe = None
            for port_address, dmx_universe in universes.items():
                if protocol_name == "sacn":
                    # For sACN, match by universe ID
                    universe_id = int(universe_value)
                    sacn_universe_id = universe_id if universe_id <= 511 else universe_id % 512
                    if port_address.universe == sacn_universe_id:
                        universe = dmx_universe
                        break
                else:
                    # For Art-Net, match by port address
                    if port_address.port_address == int(universe_value):
                        universe = dmx_universe
                        break

            if universe is None:
                log.warning(f"Could not find universe for {protocol_name} universe {universe_value}")
                continue

            entities.extend(self.create_entities_for_universe(universe_yaml, universe, device_fingerprints))

        return entities
