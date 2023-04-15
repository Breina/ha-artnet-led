from __future__ import annotations

import logging
import time
from array import array
from typing import Union

import homeassistant.helpers.config_validation as cv
import homeassistant.util.color as color_util
import pyartnet
import voluptuous as vol
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_RGBWW_COLOR,
    ATTR_TRANSITION,
    COLOR_MODE_BRIGHTNESS,
    COLOR_MODE_COLOR_TEMP,
    COLOR_MODE_RGB,
    COLOR_MODE_RGBW,
    COLOR_MODE_RGBWW,
    SUPPORT_TRANSITION,
    PLATFORM_SCHEMA,
    LightEntity, COLOR_MODE_ONOFF, COLOR_MODE_WHITE, ATTR_WHITE)
from homeassistant.const import CONF_DEVICES, STATE_OFF, STATE_ON
from homeassistant.const import CONF_FRIENDLY_NAME as CONF_DEVICE_FRIENDLY_NAME
from homeassistant.const import CONF_HOST as CONF_NODE_HOST
from homeassistant.const import CONF_NAME as CONF_DEVICE_NAME
from homeassistant.const import CONF_PORT as CONF_NODE_PORT
from homeassistant.const import CONF_TYPE as CONF_DEVICE_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import async_get
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util.color import color_rgb_to_rgbw
from pyartnet import BaseUniverse, Channel
from pyartnet.errors import UniverseNotFoundError

from custom_components.dmx.bridge.artnet_controller import ArtNetController
from custom_components.dmx.bridge.channel_bridge import ChannelBridge
from custom_components.dmx.util.channel_switch import validate, to_values, from_values

CONF_DEVICE_TRANSITION = ATTR_TRANSITION

CONF_SEND_PARTIAL_UNIVERSE = "send_partial_universe"

log = logging.getLogger(__name__)

CONF_NODE_TYPE = "node_type"
CONF_NODE_MAX_FPS = "max_fps"
CONF_NODE_REFRESH = "refresh_every"
CONF_NODE_UNIVERSES = "universes"

CONF_DEVICE_CHANNEL = "channel"
CONF_OUTPUT_CORRECTION = "output_correction"
CONF_CHANNEL_SIZE = "channel_size"
CONF_BYTE_ORDER = "byte_order"

CONF_DEVICE_MIN_TEMP = "min_temp"
CONF_DEVICE_MAX_TEMP = "max_temp"
CONF_CHANNEL_SETUP = "channel_setup"

DOMAIN = "dmx"

AVAILABLE_CORRECTIONS = {"linear": pyartnet.output_correction.linear, "quadratic": pyartnet.output_correction.quadratic,
                         "cubic": pyartnet.output_correction.cubic, "quadruple": pyartnet.output_correction.quadruple}

CHANNEL_SIZE = {
    "8bit": (1, 1),
    "16bit": (2, 256),
    "24bit": (3, 256 ** 2),
    "32bit": (4, 256 ** 3),
}

NODES = {}


async def async_setup_platform(hass: HomeAssistant, config, async_add_devices, discovery_info=None):
    pyartnet.base.CREATE_TASK = hass.async_create_task

    client_type = config.get(CONF_NODE_TYPE)
    max_fps = config.get(CONF_NODE_MAX_FPS)
    refresh_interval = config.get(CONF_NODE_REFRESH)

    host = config.get(CONF_NODE_HOST)
    port = config.get(CONF_NODE_PORT)

    # setup Node
    node: pyartnet.base.BaseNode
    if client_type == "artnet-direct":
        __id = f"{host}:{port}"
        if __id not in NODES:
            __node = pyartnet.ArtNetNode(
                host,
                port,
                max_fps=max_fps,
                refresh_every=refresh_interval,
                start_refresh_task=(refresh_interval == 0),
                sequence_counter=True
            )
            NODES[id] = __node

        node = NODES[id]

    elif client_type == "artnet-controller":
        if "server" not in NODES:
            __node = ArtNetController(hass, max_fps=max_fps, refresh_every=refresh_interval)
            NODES["server"] = __node
            __node.start()
        node = NODES["server"]

    elif client_type == "sacn":
        __id = f"{host}:{port}"
        if __id not in NODES:
            __node = pyartnet.SacnNode(
                host,
                port,
                max_fps=max_fps,
                refresh_every=refresh_interval,
                start_refresh_task=(refresh_interval == 0),
                source_name="ha-artnet-led"
            )
            NODES[id] = __node

        node = NODES[id]
    elif client_type == "kinet":
        __id = f"{host}:{port}"
        if __id not in NODES:
            __node = pyartnet.KiNetNode(
                host,
                port,
                max_fps=max_fps,
                refresh_every=refresh_interval,
                start_refresh_task=(refresh_interval == 0),
            )
            NODES[id] = __node

        node = NODES[id]

    else:
        raise NotImplementedError(f"Unknown client type '{client_type}'")

    entity_registry = async_get(hass)
    await entity_registry.async_load()

    device_list = []
    used_unique_ids = []
    for universe_nr, universe_cfg in config[CONF_NODE_UNIVERSES].items():
        try:
            universe = node.get_universe(universe_nr)
        except UniverseNotFoundError:
            universe: BaseUniverse = node.add_universe(universe_nr)
            universe.output_correction = AVAILABLE_CORRECTIONS.get(
                universe_cfg[CONF_OUTPUT_CORRECTION]
            )

        for device in universe_cfg[CONF_DEVICES]:  # type: dict
            device = device.copy()
            cls = __CLASS_TYPE[device[CONF_DEVICE_TYPE]]

            channel = device[CONF_DEVICE_CHANNEL]
            unique_id = f"{DOMAIN}:{host}/{universe_nr}/{channel}"

            name: str = device[CONF_DEVICE_NAME]
            byte_size = CHANNEL_SIZE[device[CONF_CHANNEL_SIZE]][0]
            byte_order = device[CONF_BYTE_ORDER]

            entity_id = f"light.{name.replace(' ', '_').lower()}"

            # If the entity has another unique ID, use that until it's migrated properly
            entity = entity_registry.async_get(entity_id)
            if entity:
                log.info(f"Found existing entity for name {entity_id}, using unique id {unique_id}")
                if entity.unique_id is not None and entity.unique_id not in used_unique_ids:
                    unique_id = entity.unique_id
            used_unique_ids.append(unique_id)

            # create device
            device["unique_id"] = unique_id
            d = cls(**device)  # type: DmxBaseLight
            d.set_type(device[CONF_DEVICE_TYPE])

            d.set_channel(
                universe.add_channel(
                    start=channel,
                    width=d.channel_width,
                    channel_name=d.name,
                    byte_size=byte_size,
                    byte_order=byte_order,
                )
            )

            d.channel.output_correction = AVAILABLE_CORRECTIONS.get(
                device[CONF_OUTPUT_CORRECTION]
            )

            device_list.append(d)

            send_partial_universe = universe_cfg[CONF_SEND_PARTIAL_UNIVERSE]
            if not send_partial_universe:
                universe._resize_universe(512)

    async_add_devices(device_list)

    return True


def convert_to_mireds(kelvin_string):
    kelvin_number = int(kelvin_string[:-1])
    return color_util.color_temperature_kelvin_to_mired(kelvin_number)


class DmxBaseLight(LightEntity, RestoreEntity):
    def __init__(self, name, unique_id: str, **kwargs):
        self._name = name
        self._channel: Union[Channel, ChannelBridge] = kwargs[CONF_DEVICE_CHANNEL]

        self._unique_id = unique_id

        self.entity_id = f"light.{name.replace(' ', '_').lower()}"
        self._attr_brightness = 255
        self._fade_time = kwargs[CONF_DEVICE_TRANSITION]
        self._transition = self._fade_time
        self._state = False
        self._channel_size = CHANNEL_SIZE[kwargs[CONF_CHANNEL_SIZE]]
        self._color_mode = kwargs[CONF_DEVICE_TYPE]
        self._vals = []
        self._features = 0
        self._supported_color_modes = set()
        self._channel_last_update = 0
        self._scale_factor = 1
        self._channel_width = 0
        self._type = None

        self._channel: pyartnet.base.Channel

    def set_channel(self, channel: pyartnet.base.Channel):
        """Set the channel"""
        self._channel = channel
        self._channel.callback_fade_finished = self._channel_fade_finish

        if isinstance(channel, ChannelBridge):
            channel.callback_values_updated = self._update_values

    def set_type(self, type):
        self._type = type

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def unique_id(self):
        """Return unique ID for light."""
        return self._unique_id

    @property
    def color_mode(self) -> str | None:
        """Return the color mode of the light."""
        return self._color_mode

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._features

    @property
    def extra_state_attributes(self):
        # TODO extra_state_attributes really shouldn't have lots of changing values like this, it pollutes the DB
        data = {"type": self._type,
                "dmx_channels": [
                    k for k in range(
                        self._channel._start, self._channel._start + self._channel._width, 1
                    )
                ],
                "dmx_values": self._channel.get_values(),
                "values": self._vals,
                "bright": self._attr_brightness,
                "transition": self._transition
                }
        self._channel_last_update = time.time()
        return data

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._state

    @property
    def should_poll(self):
        return False

    @property
    def supported_color_modes(self) -> set | None:
        """Flag supported color modes."""
        return self._supported_color_modes

    @property
    def fade_time(self):
        return self._fade_time

    @fade_time.setter
    def fade_time(self, value):
        self._fade_time = value

    def _update_values(self, values: array[int]):
        assert len(values) == len(self._vals)
        self._vals = tuple(values)

        self._channel_value_change()

    def _channel_value_change(self):
        """Schedule update while fade is running"""
        if time.time() - self._channel_last_update > 1.1:
            self._channel_last_update = time.time()
        self.async_schedule_update_ha_state()

    def _channel_fade_finish(self, channel):
        """Fade is finished -> schedule update"""
        self._channel_last_update = time.time()
        self.async_schedule_update_ha_state()

    @staticmethod
    def _default_calculation_function(channel_value):
        return channel_value if isinstance(channel_value, int) else 0

    def get_target_values(self) -> list:
        """Return the Target DMX Values"""
        raise NotImplementedError()

    async def async_create_fade(self, **kwargs):
        """Instruct the light to turn on"""
        self._state = True

        self._transition = kwargs.get(ATTR_TRANSITION, self._fade_time)

        self._channel.set_fade(
            self.get_target_values(), self._transition * 1000
        )

        self.async_schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        """
        Instruct the light to turn off. If a transition time has been specified in seconds
        the controller will fade.
        """
        self._transition = kwargs.get(ATTR_TRANSITION, self._fade_time)

        log.debug(
            "Turning off '%s' with transition  %i", self._name, self._transition
        )
        self._channel.set_fade(
            [0 for _ in range(self._channel._width)],
            self._transition * 1000
        )

        self._state = False
        self.async_schedule_update_ha_state()

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        old_state = await self.async_get_last_state()
        if old_state:
            old_type = old_state.attributes.get('type')
            if old_type != self._type:
                log.debug("Channel type changed. Unable to restore state.")
                old_state = None

        if old_state is not None:
            await self.restore_state(old_state)

    async def restore_state(self, old_state):
        log.error("Derived class should implement this. Report this to the repository author.")

    @property
    def channel_width(self):
        return self._channel_width

    @property
    def channel_size(self):
        return self._channel_size

    @property
    def channel(self):
        return self._channel


class DmxFixed(DmxBaseLight):
    CONF_TYPE = "fixed"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._channel_width = 1

    def get_target_values(self):
        return [self.brightness * self._channel_size[1]]

    async def async_turn_on(self, **kwargs):
        pass  # do nothing, fixed is constant value

    async def async_turn_off(self, **kwargs):
        pass  # do nothing, fixed is constant value

    async def restore_state(self, old_state):
        log.debug("Added fixed to hass. Do nothing to restore state. Fixed is constant value")
        await super().async_create_fade()


class DmxBinary(DmxBaseLight):
    CONF_TYPE = "binary"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._channel_width = 1
        self._supported_color_modes.add(COLOR_MODE_ONOFF)
        self._color_mode = COLOR_MODE_ONOFF

    def _update_values(self, values: array[int]):
        self._state, _, _, _, _, _, _, color_temp = from_values("d", self.channel_size[1], values)

        self._channel_value_change()

    def get_target_values(self):
        return [self.brightness * self._channel_size[1]]

    async def async_turn_on(self, **kwargs):
        self._state = True
        self._attr_brightness = 255
        self._channel.set_fade(
            self.get_target_values(), 0
        )
        self.async_schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        self._state = False
        self._attr_brightness = 0
        self._channel.set_fade(
            self.get_target_values(), 0
        )
        self.async_schedule_update_ha_state()

    async def restore_state(self, old_state):
        log.debug("Added binary light to hass. Try restoring state.")
        self._state = old_state.state
        self._attr_brightness = old_state.attributes.get('bright')

        if old_state.state == STATE_ON:
            await self.async_turn_on()
        else:
            await self.async_turn_off()


class DmxDimmer(DmxBaseLight):
    CONF_TYPE = "dimmer"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._channel_width = 1
        self._supported_color_modes.add(COLOR_MODE_BRIGHTNESS)
        self._features = SUPPORT_TRANSITION
        self._color_mode = COLOR_MODE_BRIGHTNESS
        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "d"
        validate(self._channel_setup, self.CONF_TYPE)

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, _, _, _, _, _, _ = \
            from_values(self._channel_setup, self.channel_size[1], values)

        self._channel_value_change()

    def get_target_values(self):
        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness)

    async def async_turn_on(self, **kwargs):

        # Update state from service call
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

        await super().async_create_fade(**kwargs)

    async def restore_state(self, old_state):
        log.debug("Added dimmer to hass. Try restoring state.")

        if old_state:
            prev_brightness = old_state.attributes.get('bright')
            self._attr_brightness = prev_brightness

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._attr_brightness, transition=0)


class DmxWhite(DmxBaseLight):
    CONF_TYPE = "color_temp"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._supported_color_modes.add(COLOR_MODE_COLOR_TEMP)
        self._supported_color_modes.add(COLOR_MODE_WHITE)

        self._features = SUPPORT_TRANSITION

        self._color_mode = COLOR_MODE_COLOR_TEMP
        # Intentionally switching min and max here; it's inverted in the conversion.

        self._min_mireds = convert_to_mireds(kwargs[CONF_DEVICE_MAX_TEMP])
        self._max_mireds = convert_to_mireds(kwargs[CONF_DEVICE_MIN_TEMP])
        self._vals = (self._max_mireds + self._min_mireds) / 2 or 300

        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "ch"
        validate(self._channel_setup, self.CONF_TYPE)

        self._channel_width = len(self._channel_setup)

    @property
    def color_temp(self) -> int:
        """Return the CT color temperature."""
        return self._vals

    @property
    def min_mireds(self) -> int:
        """Return the coldest color_temp that this light supports."""
        return self._min_mireds

    @property
    def max_mireds(self) -> int:
        """Return the warmest color_temp that this light supports."""
        return self._max_mireds

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, _, _, _, _, _, color_temp = from_values(self._channel_setup, self.channel_size[1], values, self._min_mireds, self._max_mireds)
        self._vals = color_temp

        self._channel_value_change()

    def get_target_values(self):
        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness,
                         color_temp_kelvin=self.color_temp_kelvin,
                         min_kelvin=self.min_color_temp_kelvin,
                         max_kelvin=self.max_color_temp_kelvin)

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """
        if ATTR_COLOR_TEMP in kwargs:
            self._vals = kwargs[ATTR_COLOR_TEMP]

        elif ATTR_WHITE in kwargs:
            self._vals = (self._max_mireds + self._min_mireds) / 2
            self._attr_brightness = kwargs[ATTR_WHITE]

        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
            self._scale_factor = self._attr_brightness / 255

        await super().async_create_fade(**kwargs)
        return None

    async def restore_state(self, old_state):
        log.debug("Added color_temp to hass. Try restoring state.")

        if old_state:
            prev_vals = old_state.attributes.get('values')
            self._vals = prev_vals
            prev_brightness = old_state.attributes.get('bright')
            self._attr_brightness = prev_brightness

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._attr_brightness, rgb_color=self._vals, transition=0)


class DmxRGB(DmxBaseLight):
    CONF_TYPE = "rgb"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._supported_color_modes.add(COLOR_MODE_RGB)
        self._features = SUPPORT_TRANSITION
        self._color_mode = COLOR_MODE_RGB
        self._vals = (255, 255, 255)

        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "rgb"
        validate(self._channel_setup, self.CONF_TYPE)

        self._channel_width = len(self._channel_setup)

        self._auto_scale_white = "w" in self._channel_setup or "W" in self._channel_setup

    @property
    def rgb_color(self) -> tuple:
        """Return the rgb color value."""
        return self._vals

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, red, green, blue, _, _, _ = \
            from_values(self._channel_setup, self.channel_size[1], values)

        self._vals = (red, green, blue)

        self._channel_value_change()

    def get_target_values(self):
        red = self._vals[0]
        green = self._vals[1]
        blue = self._vals[2]

        if self._auto_scale_white:
            red, green, blue, white = color_rgb_to_rgbw(red, green, blue)
        else:
            white = -1

        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness, red, green, blue,
                         white)

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """

        # RGB already contains brightness information
        if ATTR_RGB_COLOR in kwargs:
            self._vals = kwargs[ATTR_RGB_COLOR]

        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
            self._scale_factor = self._attr_brightness / 255

        await super().async_create_fade(**kwargs)
        return None

    async def restore_state(self, old_state):
        log.debug("Added rgb to hass. Try restoring state.")

        if old_state:
            prev_vals = old_state.attributes.get('values')
            self._vals = prev_vals
            prev_brightness = old_state.attributes.get('bright')
            self._attr_brightness = prev_brightness

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._attr_brightness, rgb_color=self._vals, transition=0)


class DmxRGBW(DmxBaseLight):
    CONF_TYPE = "rgbw"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._supported_color_modes.add(COLOR_MODE_RGBW)
        self._features = SUPPORT_TRANSITION
        self._color_mode = COLOR_MODE_RGBW
        self._vals = (255, 255, 255, 255)

        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "rgbw"
        validate(self._channel_setup, self.CONF_TYPE)

        self._channel_width = len(self._channel_setup)

    @property
    def rgbw_color(self) -> tuple:
        """Return the rgbw color value."""
        return self._vals

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, red, green, blue, white, _, _ = \
            from_values(self._channel_setup, self.channel_size[1], values)

        self._vals = (red, green, blue, white)

        self._channel_value_change()

    def get_target_values(self):
        red = self._vals[0]
        green = self._vals[1]
        blue = self._vals[2]
        white = self._vals[3]

        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness, red, green, blue,
                         white)

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """
        # RGB already contains brightness information
        if ATTR_RGBW_COLOR in kwargs:
            self._vals = kwargs[ATTR_RGBW_COLOR]
            # self._scale_factor = 1

        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
            self._scale_factor = self._attr_brightness / 255

        await super().async_create_fade(**kwargs)
        return None

    async def restore_state(self, old_state):
        log.debug("Added rgbw to hass. Try restoring state.")

        if old_state:
            prev_vals = old_state.attributes.get('values')
            self._vals = prev_vals

            prev_brightness = old_state.attributes.get('bright')
            self._attr_brightness = prev_brightness

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._attr_brightness, rgbw_color=self._vals, transition=0)


class DmxRGBWW(DmxBaseLight):
    CONF_TYPE = "rgbww"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._supported_color_modes.add(COLOR_MODE_RGBWW)
        self._features = SUPPORT_TRANSITION
        self._color_mode = COLOR_MODE_RGBWW
        # Intentionally switching min and max here; it's inverted in the conversion.
        self._min_mireds = convert_to_mireds(kwargs[CONF_DEVICE_MAX_TEMP])
        self._max_mireds = convert_to_mireds(kwargs[CONF_DEVICE_MIN_TEMP])
        self._vals = (255, 255, 255, 255, 255)

        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "rgbch"
        validate(self._channel_setup, self.CONF_TYPE)

        self._channel_width = len(self._channel_setup)

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, red, green, blue, cold_white, warm_white, _ = \
            from_values(self._channel_setup, self.channel_size[1], values)

        self._vals = (red, green, blue, cold_white, warm_white)

        self._channel_value_change()

    @property
    def rgbww_color(self) -> tuple:
        """Return the rgbww color value."""
        return self._vals

    @property
    def min_mireds(self) -> int:
        """Return the coldest color_temp that this light supports."""
        return self._min_mireds

    @property
    def max_mireds(self) -> int:
        """Return the warmest color_temp that this light supports."""
        return self._max_mireds

    @property
    def color_temp(self) -> int | None:
        return color_util.rgbww_to_color_temperature(self._vals, self.min_mireds, self.max_mireds)[0]

    def get_target_values(self):
        red = self._vals[0]
        green = self._vals[1]
        blue = self._vals[2]
        cold_white = self._vals[3]
        warm_white = self._vals[4]

        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness, red, green, blue,
                         cold_white, warm_white, self.color_temp_kelvin, self.min_color_temp_kelvin,
                         self.max_color_temp_kelvin)

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """

        # RGB already contains brightness information
        if ATTR_RGBWW_COLOR in kwargs:
            self._vals = kwargs[ATTR_RGBWW_COLOR]
            # self._scale_factor = 1

        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
            self._scale_factor = self._attr_brightness / 255

        await super().async_create_fade(**kwargs)
        return None

    async def restore_state(self, old_state):
        log.debug("Added rgbww to hass. Try restoring state.")

        if old_state:
            prev_vals = old_state.attributes.get('values')
            self._vals = prev_vals

            prev_brightness = old_state.attributes.get('bright')
            self._attr_brightness = prev_brightness
            self._scale_factor = self._attr_brightness / 255

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._attr_brightness, rgbww_color=self._vals, transition=0)


# ------------------------------------------------------------------------------
# conf
# ------------------------------------------------------------------------------

__CLASS_LIST = [DmxDimmer, DmxRGB, DmxWhite, DmxRGBW, DmxRGBWW, DmxBinary, DmxFixed]
__CLASS_TYPE = {k.CONF_TYPE: k for k in __CLASS_LIST}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NODE_HOST): cv.string,
        vol.Required(CONF_NODE_UNIVERSES): {
            vol.All(int, vol.Range(min=0, max=1024)): {
                vol.Optional(CONF_SEND_PARTIAL_UNIVERSE, default=True): cv.boolean,
                vol.Optional(CONF_OUTPUT_CORRECTION, default='linear'): vol.Any(
                    None, vol.In(AVAILABLE_CORRECTIONS)
                ),
                CONF_DEVICES: vol.All(
                    cv.ensure_list,
                    [
                        {
                            vol.Required(CONF_DEVICE_CHANNEL): vol.All(
                                vol.Coerce(int), vol.Range(min=1, max=512)
                            ),
                            vol.Required(CONF_DEVICE_NAME): cv.string,
                            vol.Optional(CONF_DEVICE_FRIENDLY_NAME): cv.string,
                            vol.Optional(CONF_DEVICE_TYPE, default='dimmer'): vol.In(
                                [k.CONF_TYPE for k in __CLASS_LIST]
                            ),
                            vol.Optional(CONF_DEVICE_TRANSITION, default=0): vol.All(
                                vol.Coerce(float), vol.Range(min=0, max=999)
                            ),
                            vol.Optional(CONF_OUTPUT_CORRECTION, default='linear'): vol.Any(
                                None, vol.In(AVAILABLE_CORRECTIONS)
                            ),
                            vol.Optional(CONF_CHANNEL_SIZE, default='8bit'): vol.Any(
                                None, vol.In(CHANNEL_SIZE)
                            ),
                            vol.Optional(CONF_BYTE_ORDER, default='big'): vol.Any(
                                None, vol.In(['little', 'big'])
                            ),
                            vol.Optional(CONF_DEVICE_MIN_TEMP, default='2700K'): vol.Match(
                                "\\d+(k|K)"
                            ),
                            vol.Optional(CONF_DEVICE_MAX_TEMP, default='6500K'): vol.Match(
                                "\\d+(k|K)"
                            ),
                            vol.Optional(CONF_CHANNEL_SETUP, default=None): vol.Any(
                                None, cv.string, cv.ensure_list
                            ),
                        }
                    ],
                )
            },
        },
        vol.Optional(CONF_NODE_PORT, default=6454): cv.port,
        vol.Optional(CONF_NODE_MAX_FPS, default=25): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=50)
        ),
        vol.Optional(CONF_NODE_REFRESH, default=120): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=9999)
        ),
        vol.Optional(CONF_NODE_TYPE, default="artnet-direct"): vol.Any(
            None, vol.In(["artnet-direct", "artnet-controller", "sacn", "kinet"])
        ),
    },
    required=True,
    extra=vol.PREVENT_EXTRA,
)
