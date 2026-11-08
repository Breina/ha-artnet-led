"""Config flow to configure DMX."""

from typing import Any

from homeassistant import config_entries
from homeassistant.config import async_hass_config_yaml
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .migration import extract_old_entries

DOCS_URL = "https://breina.github.io/ha-artnet-led"


class ArtNetFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Artnet config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the Artnet flow."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        """Handle a flow start."""
        pass

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        if await self._async_artnet_led_configured():
            return self.async_abort(
                reason="migrate_artnet_led",
                description_placeholders={
                    "dmx_snippet": "dmx: {}",
                    "migration_url": f"{DOCS_URL}/migration/",
                },
            )
        return self.async_abort(
            reason="yaml_only",
            description_placeholders={"config_url": f"{DOCS_URL}/config/"},
        )

    async def _async_artnet_led_configured(self) -> bool:
        """Whether configuration.yaml still has lights of the old artnet_led integration.

        Starting a flow from the UI doesn't run async_setup, which is where the old
        lights are normally found, so the YAML is read here.
        """
        try:
            config = await async_hass_config_yaml(self.hass)
        except HomeAssistantError:
            return False
        return bool(extract_old_entries(config))

    async def async_step_import(self, user_input: dict[str, Any] | None = None) -> Any:
        """Handle configuration by YAML file."""
        await self.async_set_unique_id(DOMAIN)

        data = self.hass.data.setdefault(DOMAIN, {})
        data.setdefault("__yaml__", set()).add(self.unique_id)

        for entry in self._async_current_entries():
            if entry.unique_id == DOMAIN:
                # Preserve existing fingerprints when updating config from YAML
                from custom_components.dmx.util.entity_cleanup import CONF_FINGERPRINTS

                existing_data = entry.data.copy() if entry.data else {}
                fingerprints = existing_data.get(CONF_FINGERPRINTS, {})

                # Update with new YAML data but preserve fingerprints
                new_data = user_input.copy() if user_input else {}
                new_data[CONF_FINGERPRINTS] = fingerprints

                self.hass.config_entries.async_update_entry(entry, data=new_data)
                self._abort_if_unique_id_configured()

        return self.async_create_entry(title=DOMAIN, data=user_input or {})
