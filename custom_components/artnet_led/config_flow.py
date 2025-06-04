"""Config flow to configure Philips Hue."""
from homeassistant import config_entries
from homeassistant.const import CONF_NAME

from .const import DOMAIN, ARTNET_CONTROLLER


# @config_entries.HANDLERS.register(DOMAIN)
# class ArtNetFlowHandler(data_entry_flow.FlowHandler):
class ArtNetFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Artnet config flow."""
    VERSION = 1

    def __init__(self):
        """Initialize the Artnet flow."""

    async def async_step_init(self, user_input=None):
        """Handle a flow start."""
        print("async_step_init")

    async def async_step_integration_discovery(self, discovery_info):
        print("async_step_discovery: " + str(discovery_info))

        discovered_node = discovery_info[ARTNET_CONTROLLER]

        return await self.async_step_onboard()

        # return await self.async_step_edit()
        # return self.async_abort(
        #     reason='LOL!!'
        # )

    async def async_step_onboard(self, user_input=None):
        print("ONBOARD: " + str(user_input))

        return self.async_show_menu()

        # return self.async_show_form(
        #     step_id="onboard",
        #     data_schema=vol.Schema({
        #         vol.Required("username"): str,
        #     })
        # )

    async def async_step_import(self, user_input=None):
        """Handle configuration by YAML file."""
        print(f"async_step_import: {user_input}")
        await self.async_set_unique_id(DOMAIN)

        # Keep a list of switches that are configured via YAML
        data = self.hass.data.setdefault(DOMAIN, {})
        data.setdefault("__yaml__", set()).add(self.unique_id)

        for entry in self._async_current_entries():
            if entry.unique_id == DOMAIN:
                self.hass.config_entries.async_update_entry(entry, data=user_input)
                self._abort_if_unique_id_configured()

        return self.async_create_entry(title=DOMAIN, data=user_input)
