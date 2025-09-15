"""ARTNET LED"""

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components.light import ATTR_TRANSITION
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry, ConfigFlowContext
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import IntegrationError
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.typing import ConfigType

from custom_components.dmx.const import CONF_FIXTURE_ENTITIES, DOMAIN
from custom_components.dmx.setup.config_processor import (
    CONF_FIXTURES,
    CONF_FOLDER,
    CONF_FOLDER_DEFAULT,
    CONF_NODE_TYPE_ARTNET,
    CONF_NODE_TYPE_SACN,
    CONFIG_SCHEMA,
    process_fixtures,
)
from custom_components.dmx.setup.entity_factory import EntityFactory
from custom_components.dmx.setup.server_manager import ServerManager
from custom_components.dmx.util.entity_cleanup import cleanup_obsolete_entities, store_fixture_fingerprints

log = logging.getLogger(__name__)

CONF_TRANSITION = ATTR_TRANSITION

PLATFORMS = [Platform.NUMBER, Platform.SELECT, Platform.LIGHT, Platform.SWITCH, Platform.BINARY_SENSOR, Platform.SENSOR]

FIXTURES: dict[str, Any] = {}


class UnknownFixtureError(IntegrationError):
    """Exception raised when a requested fixture cannot be found."""

    def __init__(self, desired_fixture: str, discovered_fixtures: list[str], *args: object) -> None:
        super().__init__(*args)
        self._fixture = desired_fixture
        self._discovered_fixtures = discovered_fixtures

    def __str__(self) -> str:
        if not self._discovered_fixtures:
            return (
                "Didn't discover any fixtures. Put them in the fixtures folder as defined by "
                "config `dmx.fixtures.folder`"
            )
        else:
            return (
                f"Could not find any fixture named '{self._fixture}, should be one of {self._discovered_fixtures}'. "
                f"Note that first the fixture's `fixtureKey` is matched, if that's not "
                f"available `shortName`, or finally `name`."
            )


async def reload_configuration_yaml(event: dict[str, Any], hass: HomeAssistant) -> None:
    """Reload configuration.yaml."""
    await hass.services.async_call("homeassistant", "check_config", {})


async def async_update_options(hass: HomeAssistant, config_entry: ConfigEntry[dict[str, Any]]) -> None:
    """Update options."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Your controller/hub specific code."""

    if DOMAIN not in config:
        return True

    discovery_flow.async_create_flow(hass, DOMAIN, context=ConfigFlowContext(source=SOURCE_IMPORT), data=config)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry[dict[str, Any]]) -> bool:
    """Set up the component."""

    hass.data.setdefault(DOMAIN, {})

    dmx_yaml = entry.data[DOMAIN]

    fixtures_yaml = dmx_yaml[CONF_FIXTURES]
    fixture_folder = fixtures_yaml.get(CONF_FOLDER, CONF_FOLDER_DEFAULT)

    log.debug("Processing fixtures folder: %s/...", str(Path(fixture_folder).absolute()))
    processed_fixtures = await process_fixtures(hass, fixture_folder)
    log.debug("Found %d fixtures", len(processed_fixtures))

    # Track fixture fingerprints for change detection
    device_fingerprints: dict[str, str] = {}

    server_manager = ServerManager(hass, entry)
    await server_manager.setup_protocols(dmx_yaml)
    universes = server_manager.get_universes()

    entity_factory = EntityFactory(processed_fixtures)
    entities = []

    if (sacn_yaml := dmx_yaml.get(CONF_NODE_TYPE_SACN)) is not None:
        entities.extend(entity_factory.create_entities_for_protocol(sacn_yaml, universes, device_fingerprints, "sacn"))

    if (artnet_yaml := dmx_yaml.get(CONF_NODE_TYPE_ARTNET)) is not None:
        entities.extend(
            entity_factory.create_entities_for_protocol(artnet_yaml, universes, device_fingerprints, "artnet")
        )

    await cleanup_obsolete_entities(hass, entry, device_fingerprints)

    hass.data[DOMAIN][entry.entry_id] = {CONF_FIXTURE_ENTITIES: entities, "universes": universes}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await store_fixture_fingerprints(hass, entry, device_fingerprints)

    return True


CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: CONFIG_SCHEMA},
    extra=vol.ALLOW_EXTRA,
)
