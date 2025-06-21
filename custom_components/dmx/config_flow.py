"""Config flow to configure Philips Hue."""
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

    async def async_step_import(self, user_input=None):
        """Handle configuration by YAML file."""
        await self.async_set_unique_id(DOMAIN)

        data = self.hass.data.setdefault(DOMAIN, {})
        data.setdefault("__yaml__", set()).add(self.unique_id)

        for entry in self._async_current_entries():
            if entry.unique_id == DOMAIN:
                self.hass.config_entries.async_update_entry(entry, data=user_input)
                self._abort_if_unique_id_configured()

        return self.async_create_entry(title=DOMAIN, data=user_input)
