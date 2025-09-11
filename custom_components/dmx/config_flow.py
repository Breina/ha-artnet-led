"""Config flow to configure DMX."""

from homeassistant import config_entries

from .const import DOMAIN


class ArtNetFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Artnet config flow."""

    VERSION = 1

    def __init__(self):
        """Initialize the Artnet flow."""

    async def async_step_init(self, user_input=None):
        """Handle a flow start."""
        pass

    async def async_step_user(self, user_input=None):
        return self.async_abort(
            reason=(
                "I acknowledge that it's fun to click buttons, but alas, this integration is configured through "
                "`configuration.yaml`. Here's how: https://breina.github.io/ha-artnet-led/config/"
            )
        )

    async def async_step_import(self, user_input=None):
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
                new_data = user_input.copy()
                new_data[CONF_FINGERPRINTS] = fingerprints

                self.hass.config_entries.async_update_entry(entry, data=new_data)
                self._abort_if_unique_id_configured()

        return self.async_create_entry(title=DOMAIN, data=user_input)
