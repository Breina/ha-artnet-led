"""
Entity cleanup utility for handling fixture configuration changes.
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.dmx.const import DOMAIN

log = logging.getLogger(__name__)

CONF_FINGERPRINTS = "fixture_fingerprints"


async def cleanup_obsolete_entities(
    hass: HomeAssistant, config_entry: ConfigEntry, current_fingerprints: dict[str, str]
) -> None:
    """
    Clean up entities from fixtures that have changed configuration.

    Args:
        hass: Home Assistant instance
        config_entry: The config entry for this integration
        current_fingerprints: Dict mapping device_name -> fixture_fingerprint
    """
    log.info("Starting entity cleanup process")

    # Get stored fingerprints from previous configuration
    stored_data = config_entry.data.get(CONF_FINGERPRINTS, {})

    log.debug(f"Stored fingerprints: {stored_data}")
    log.debug(f"Current fingerprints: {current_fingerprints}")

    # Find devices with changed fingerprints
    changed_devices = set()
    for device_name, current_fingerprint in current_fingerprints.items():
        stored_fingerprint = stored_data.get(device_name)
        log.debug(f"Checking device '{device_name}': stored='{stored_fingerprint}' vs current='{current_fingerprint}'")
        if stored_fingerprint and stored_fingerprint != current_fingerprint:
            changed_devices.add(device_name)
            log.warning(
                f"Detected fixture configuration change for device '{device_name}' "
                f"(fingerprint: {stored_fingerprint} -> {current_fingerprint})"
            )
        elif not stored_fingerprint:
            log.debug(f"No stored fingerprint for device '{device_name}' (first run?)")
        else:
            log.debug(f"No change detected for device '{device_name}'")

    if not changed_devices:
        log.debug("No fixture configuration changes detected")
        return

    # Get entity registry
    entity_registry = er.async_get(hass)

    # Find entities that belong to changed devices
    obsolete_entities = []
    for entity in entity_registry.entities.values():
        if entity.platform == DOMAIN and entity.config_entry_id == config_entry.entry_id:
            log.debug(f"Checking entity: {entity.entity_id} (unique_id: {entity.unique_id})")

            # Check if this entity belongs to a changed device
            for device_name in changed_devices:
                old_fingerprint = stored_data.get(device_name)

                # Check if the old fingerprint is in the unique_id and the device name matches
                if old_fingerprint and old_fingerprint in entity.unique_id:
                    # More robust device name matching
                    device_name_lower = device_name.lower()
                    unique_id_lower = entity.unique_id.lower()

                    # Check various patterns for device name in unique_id
                    device_matches = (
                        # For entity_id_prefix case: prefix often contains device name
                        device_name_lower in unique_id_lower
                        or
                        # For auto-generated case: dmx_universe_device_...
                        f"_{device_name_lower}_" in unique_id_lower
                        or
                        # Entity starts with device name (entity_id_prefix case)
                        unique_id_lower.startswith(device_name_lower)
                        or
                        # Contains device name after domain and universe
                        (f"{DOMAIN}_" in unique_id_lower and device_name_lower in unique_id_lower)
                    )

                    if device_matches:
                        log.debug(
                            f"Marking entity for removal: {entity.entity_id} "
                            f"(device: {device_name}, old fingerprint: {old_fingerprint})"
                        )
                        obsolete_entities.append(entity)
                        break

    # Remove obsolete entities
    if obsolete_entities:
        log.info(f"Removing {len(obsolete_entities)} obsolete entities due to fixture changes")
        for entity in obsolete_entities:
            log.info(f"Removing obsolete entity: {entity.entity_id} (unique_id: {entity.unique_id})")
            entity_registry.async_remove(entity.entity_id)
    else:
        log.debug("No obsolete entities found to clean up")


async def store_fixture_fingerprints(
    hass: HomeAssistant, config_entry: ConfigEntry, fingerprints: dict[str, str]
) -> None:
    """
    Store fixture fingerprints in config entry data for future comparison.

    Args:
        hass: Home Assistant instance
        config_entry: The config entry for this integration
        fingerprints: Dict mapping device_name -> fixture_fingerprint
    """
    log.debug(f"Storing fixture fingerprints for {len(fingerprints)} devices: {fingerprints}")

    new_data = config_entry.data.copy()
    new_data[CONF_FINGERPRINTS] = fingerprints

    hass.config_entries.async_update_entry(config_entry, data=new_data)
    log.debug(f"Successfully stored fingerprints for {len(fingerprints)} devices")
