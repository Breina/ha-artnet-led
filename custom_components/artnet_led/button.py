"""DMX Trigger Button Platform for Art-Net LED Integration."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from custom_components.artnet_led.util.channel_switch import to_values

log = logging.getLogger(__name__)

DOMAIN = "artnet_led"


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> bool:
    """Set up the DMX Trigger Button platform."""
    if discovery_info is None:
        return True

    buttons = []
    for button_config in discovery_info.get("buttons", []):
        button = DmxTriggerButton(
            name=button_config["name"],
            unique_id=button_config["unique_id"],
            channel=button_config["channel"],
            channel_setup=button_config["channel_setup"],
            channel_size=button_config["channel_size"],
            fade_time=button_config["fade_time"],
        )
        buttons.append(button)

    async_add_entities(buttons)
    return True


class DmxTriggerButton(ButtonEntity):
    """A button that sends fixed DMX values when pressed."""

    def __init__(
        self,
        name: str,
        unique_id: str,
        channel,
        channel_setup: list,
        channel_size: tuple,
        fade_time: float,
    ):
        """Initialize the DMX Trigger Button."""
        self._name = name
        self._unique_id = unique_id
        self._channel = channel
        self._channel_setup = channel_setup
        self._channel_size = channel_size
        self._fade_time = fade_time

    @property
    def name(self) -> str:
        """Return the display name of this button."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return unique ID for button."""
        return self._unique_id

    async def async_press(self) -> None:
        """Handle the button press - send fixed DMX values."""
        log.debug("DMX Trigger Button '%s' pressed, sending values", self._name)

        # Calculate the target values (always on at full brightness for fixed)
        target_values = to_values(
            self._channel_setup,
            self._channel_size[1],
            True,  # is_on
            255    # brightness
        )

        # Send the values with fade
        self._channel.set_fade(target_values, self._fade_time * 1000)
