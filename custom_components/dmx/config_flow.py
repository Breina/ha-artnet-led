"""Config flow to configure Philips Hue."""
import voluptuous
from homeassistant import config_entries, data_entry_flow
import voluptuous as vol

from .const import DOMAIN


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

        return self.async_show_form(
            step_id="discovery", data_schema=vol.Schema({})
        )

        # return await self.async_step_edit()
        # return self.async_abort(
        #     reason='LOL!!'
        # )

    async def async_step_import(self, import_info):
        """Import a new bridge as a config entry.

        Will read authentication from Phue config file if available.

        This flow is triggered by `async_setup` for both configured and
        discovered bridges. Triggered for any bridge that does not have a
        config entry yet (based on host).

        This flow is also triggered by `async_step_discovery`.

        If an existing config file is found, we will validate the credentials
        and create an entry. Otherwise we will delegate to `link` step which
        will ask user to link the bridge.
        """

        print("async_step_import: " + str(import_info))
        return self.async_abort(
            reason='LOL!!'
        )
