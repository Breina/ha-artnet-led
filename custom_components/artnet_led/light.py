from __future__ import annotations

import asyncio
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
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_RGBWW_COLOR,
    ATTR_XY_COLOR,
    ATTR_TRANSITION,
    PLATFORM_SCHEMA,
    LightEntity, ATTR_WHITE, ATTR_COLOR_TEMP_KELVIN, ATTR_FLASH,
    FLASH_SHORT, FLASH_LONG, ATTR_HS_COLOR, LightEntityFeature, ColorMode)
from homeassistant.const import CONF_DEVICES, STATE_OFF, STATE_ON
from homeassistant.const import CONF_FRIENDLY_NAME as CONF_DEVICE_FRIENDLY_NAME
from homeassistant.const import CONF_HOST as CONF_NODE_HOST
from homeassistant.const import CONF_NAME as CONF_DEVICE_NAME
from homeassistant.const import CONF_PORT as CONF_NODE_PORT
from homeassistant.const import CONF_TYPE as CONF_DEVICE_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
from homeassistant.helpers.entity_registry import async_get
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util.color import color_rgb_to_rgbw
from pyartnet import BaseUniverse, Channel
from pyartnet.errors import UniverseNotFoundError

from custom_components.artnet_led.bridge.artnet_controller import ArtNetController
from custom_components.artnet_led.bridge.channel_bridge import ChannelBridge
from custom_components.artnet_led.util.channel_switch import validate, to_values, from_values

ARTNET_DEFAULT_PORT = 6454
SACN_DEFAULT_PORT = 5568
KINET_DEFAULT_PORT = 6038

CONF_DEVICE_TRANSITION = ATTR_TRANSITION

CONF_SEND_PARTIAL_UNIVERSE = "send_partial_universe"

log = logging.getLogger(__name__)

CONF_NODE_HOST_OVERRIDE = "host_override"
CONF_NODE_PORT_OVERRIDE = "port_override"

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

type LogicalChannelSize = int
type LogicalChannelNumBytes = int
type ChannelSize = tuple[LogicalChannelSize, LogicalChannelNumBytes]

CHANNEL_SIZE: dict[str, ChannelSize] = {
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

    real_host = config.get(CONF_NODE_HOST_OVERRIDE)
    if len(real_host) == 0:
        real_host = host
    real_port = config.get(CONF_NODE_PORT_OVERRIDE)
    if real_port == None:
        real_port = port

    # setup Node
    node: pyartnet.base.BaseNode
    if client_type == "artnet-direct":
        if real_port is None:
            real_port = ARTNET_DEFAULT_PORT

        __id = f"{host}:{port}"
        if __id not in NODES:
            __node = pyartnet.ArtNetNode(
                real_host,
                real_port,
                max_fps=max_fps,
                refresh_every=refresh_interval,
                start_refresh_task=(refresh_interval > 0),
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
        if real_port is None:
            real_port = SACN_DEFAULT_PORT

        __id = f"{host}:{port}"
        if __id not in NODES:
            __node = pyartnet.SacnNode(
                real_host,
                real_port,
                max_fps=max_fps,
                refresh_every=refresh_interval,
                start_refresh_task=(refresh_interval > 0),
                source_name="ha-artnet-led"
            )
            NODES[id] = __node

        node = NODES[id]
    elif client_type == "kinet":
        if real_port is None:
            real_port = KINET_DEFAULT_PORT

        __id = f"{host}:{port}"
        if __id not in NODES:
            __node = pyartnet.KiNetNode(
                real_host,
                real_port,
                max_fps=max_fps,
                refresh_every=refresh_interval,
                start_refresh_task=(refresh_interval > 0),
            )
            NODES[id] = __node

        node = NODES[id]

    else:
        raise NotImplementedError(f"Unknown client type '{client_type}'")

    entity_registry = async_get(hass)

    device_list = []
    button_configs = []
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
            device_type = device[CONF_DEVICE_TYPE]

            channel = device[CONF_DEVICE_CHANNEL]
            unique_id = f"{DOMAIN}:{host}/{universe_nr}/{channel}"

            name: str = device[CONF_DEVICE_NAME]
            byte_size = CHANNEL_SIZE[device[CONF_CHANNEL_SIZE]][0]
            byte_order = device[CONF_BYTE_ORDER]

            # Handle "trigger" type as a button instead of a light
            if device_type == "trigger":
                entity_id = f"button.{name.replace(' ', '_').lower()}"
                entity = entity_registry.async_get(entity_id)
                if entity:
                    log.info(f"Found existing entity for name {entity_id}, using unique id {unique_id}")
                    if entity.unique_id is not None and entity.unique_id not in used_unique_ids:
                        unique_id = entity.unique_id
                used_unique_ids.append(unique_id)

                channel_setup = device.get(CONF_CHANNEL_SETUP) or [255]
                channel_width = len(channel_setup)

                dmx_channel = universe.add_channel(
                    start=channel,
                    width=channel_width,
                    channel_name=name,
                    byte_size=byte_size,
                    byte_order=byte_order,
                )
                dmx_channel.output_correction = AVAILABLE_CORRECTIONS.get(
                    device[CONF_OUTPUT_CORRECTION]
                )

                button_configs.append({
                    "name": name,
                    "unique_id": unique_id,
                    "channel": dmx_channel,
                    "channel_setup": channel_setup,
                    "channel_size": CHANNEL_SIZE[device[CONF_CHANNEL_SIZE]],
                    "fade_time": device[CONF_DEVICE_TRANSITION],
                })

                send_partial_universe = universe_cfg[CONF_SEND_PARTIAL_UNIVERSE]
                if not send_partial_universe:
                    universe._resize_universe(512)
                continue

            cls = __CLASS_TYPE[device_type]

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

    # Forward fixed type devices to the button platform
    if button_configs:
        hass.async_create_task(
            discovery.async_load_platform(
                hass,
                "button",
                "artnet_led",
                {"buttons": button_configs},
                config,
            )
        )

    return True


def convert_to_kelvin(kelvin_string) -> int:
    return int(kelvin_string[:-1])


class DmxBaseLight(LightEntity, RestoreEntity):
    def __init__(self, name, unique_id: str, **kwargs):
        self._name = name
        self._channel: Union[Channel, ChannelBridge] = kwargs[CONF_DEVICE_CHANNEL]

        self._unique_id = unique_id

        self.entity_id = f"light.{name.replace(' ', '_').lower()}"
        self._attr_brightness = 255
        self._fade_time = kwargs[CONF_DEVICE_TRANSITION]
        self._state = False
        self._channel_size = CHANNEL_SIZE[kwargs[CONF_CHANNEL_SIZE]]
        self._color_mode = kwargs[CONF_DEVICE_TYPE]
        self._vals = []
        self._features = 0
        self._supported_color_modes = set()
        self._channel_last_update = 0
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
                "bright": self._attr_brightness
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

    async def flash(self, old_values, old_brightness, **kwargs):
        transition = kwargs.get(ATTR_TRANSITION, self._fade_time)
        if transition == 0:
            transition = 1

        old_state = self._state
        self._state = True

        flash_time = kwargs.get(ATTR_FLASH)

        if old_state and old_values == self._vals and old_brightness == self._attr_brightness:
            if self._attr_brightness < 128:
                self._attr_brightness = 255
            else:
                self._attr_brightness = 0

        if flash_time == FLASH_SHORT:
            self._channel.set_values(self.get_target_values())
            await self._channel
        elif flash_time == FLASH_LONG:
            self._channel.set_fade(self.get_target_values(), transition * 1000)
            await self._channel
        else:
            log.error(f"{flash_time} is not a valid value for attribute {ATTR_FLASH}")
            return

        self._state = old_state
        self._attr_brightness = old_brightness
        self._vals = old_values

        self._channel.set_fade(self.get_target_values(), transition * 1000)

    async def async_create_fade(self, **kwargs):
        """Instruct the light to turn on"""
        self._state = True

        transition = kwargs.get(ATTR_TRANSITION, self._fade_time)

        self._channel.set_fade(
            self.get_target_values(), transition * 1000
        )

        self.async_schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        """
        Instruct the light to turn off. If a transition time has been specified in seconds
        the controller will fade.
        """
        transition = kwargs.get(ATTR_TRANSITION, self._fade_time)

        self._channel.set_fade(
            [0 for _ in range(self._channel._width)],
            transition * 1000
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
        self._color_mode = ColorMode.ONOFF
        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or [255]
        self._channel_width = len(self._channel_setup)

    def get_target_values(self):
        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness)

    def set_channel(self, channel: pyartnet.base.Channel):
        super().set_channel(channel)
        channel.set_values(self.get_target_values())

    async def async_turn_on(self, **kwargs):
        pass  # do nothing, fixed is constant value

    async def async_turn_off(self, **kwargs):
        pass  # do nothing, fixed is constant value

    async def restore_state(self, old_state):
        log.debug("Added fixed to hass. Do nothing to restore state. Fixed is constant value")
        await super().async_create_fade()


class DmxTrigger:
    """Marker class for trigger type - actual implementation is in button.py"""
    CONF_TYPE = "trigger"


class DmxBinary(DmxBaseLight):
    CONF_TYPE = "binary"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._channel_width = 1
        self._features = LightEntityFeature.FLASH
        self._color_mode = ColorMode.ONOFF
        self._supported_color_modes.add(ColorMode.ONOFF)

    def _update_values(self, values: array[int]):
        self._state, _, _, _, _, _, _, color_temp, _, _ = from_values("d", self.channel_size[1], values)

        self._channel_value_change()

    def get_target_values(self):
        return [self.brightness * self._channel_size[1]]

    async def async_turn_on(self, **kwargs):
        if ATTR_FLASH in kwargs:
            flash_time = kwargs[ATTR_FLASH]
            if flash_time == FLASH_SHORT:
                duration = 0.5
            else:
                duration = 2.0

            await self.flash_binary(duration)
            return

        self._state = True
        self._attr_brightness = 255
        self._channel.set_fade(
            self.get_target_values(), 0
        )
        self.async_schedule_update_ha_state()

    async def flash_binary(self, duration: float):
        self._state = not self._state
        self._attr_brightness = 255 if self._state else 0
        self._channel.set_fade(
            self.get_target_values(), 0
        )
        await asyncio.sleep(duration)
        self._state = not self._state
        self._attr_brightness = 255 if self._state else 0
        self._channel.set_fade(
            self.get_target_values(), 0
        )

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
        self._features = LightEntityFeature.TRANSITION | LightEntityFeature.FLASH
        self._color_mode = ColorMode.BRIGHTNESS
        self._supported_color_modes.add(ColorMode.BRIGHTNESS)
        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "d"
        validate(self._channel_setup, self.CONF_TYPE)

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, _, _, _, _, _, _, _, _ = \
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

        self._features = LightEntityFeature.TRANSITION | LightEntityFeature.FLASH

        self._color_mode = ColorMode.COLOR_TEMP
        self._supported_color_modes.add(ColorMode.COLOR_TEMP)
        # Intentionally switching min and max here; it's inverted in the conversion.

        self._min_kelvin = convert_to_kelvin(kwargs[CONF_DEVICE_MIN_TEMP])
        self._max_kelvin = convert_to_kelvin(kwargs[CONF_DEVICE_MAX_TEMP])
        self._vals = int((self._max_kelvin + self._min_kelvin) / 2)

        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "ch"
        validate(self._channel_setup, self.CONF_TYPE)

        self._channel_width = len(self._channel_setup)

    @property
    def color_temp_kelvin(self) -> int | None:
        return self._vals

    @property
    def min_color_temp_kelvin(self) -> int:
        """Return the warmest color_temp_kelvin that this light supports."""
        return self._min_kelvin

    @property
    def max_color_temp_kelvin(self) -> int:
        """Return the coldest color_temp_kelvin that this light supports."""
        return self._max_kelvin

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, _, _, _, _, _, color_temp, _, _ = \
            from_values(self._channel_setup, self.channel_size[1], values, self._min_kelvin, self._max_kelvin)
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

        old_values = self._vals
        old_brightness = self._attr_brightness

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._vals = kwargs[ATTR_COLOR_TEMP_KELVIN]

        elif ATTR_WHITE in kwargs:
            self._vals = (self._max_kelvin + self._min_kelvin) / 2
            self._attr_brightness = kwargs[ATTR_WHITE]

        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

        if ATTR_FLASH in kwargs:
            await super().flash(old_values, old_brightness, **kwargs)
        else:
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
        self._features = LightEntityFeature.TRANSITION | LightEntityFeature.FLASH
        self._color_mode = ColorMode.RGB
        self._supported_color_modes.add(ColorMode.RGB)
        self._supported_color_modes.add(ColorMode.HS)
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
        self._state, self._attr_brightness, red, green, blue, _, _, _, _, _ = \
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

        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness, red, green,
                         blue,
                         white)

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """

        old_values = self._vals
        old_brightness = self._attr_brightness

        # RGB already contains brightness information
        if ATTR_RGB_COLOR in kwargs:
            self._vals = kwargs[ATTR_RGB_COLOR]

        if ATTR_HS_COLOR in kwargs:
            hue, sat = kwargs[ATTR_HS_COLOR]
            self._vals = color_util.color_hs_to_RGB(hue, sat)

        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

        if ATTR_FLASH in kwargs:
            await super().flash(old_values, old_brightness, **kwargs)
        else:
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
        self._features = LightEntityFeature.TRANSITION | LightEntityFeature.FLASH
        self._color_mode = ColorMode.RGBW
        self._supported_color_modes.add(ColorMode.RGBW)
        self._supported_color_modes.add(ColorMode.HS)
        self._vals = [255, 255, 255, 255]

        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "rgbw"
        validate(self._channel_setup, self.CONF_TYPE)

        self._channel_width = len(self._channel_setup)

    @property
    def rgbw_color(self) -> tuple:
        """Return the rgbw color value."""
        return tuple(self._vals)

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, red, green, blue, white, _, _, _, _ = \
            from_values(self._channel_setup, self.channel_size[1], values)

        self._vals = [red, green, blue, white]

        self._channel_value_change()

    def get_target_values(self):
        red = self._vals[0]
        green = self._vals[1]
        blue = self._vals[2]
        white = self._vals[3]

        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness, red, green,
                         blue,
                         white)

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """

        old_values = list(self._vals)
        old_brightness = self._attr_brightness

        # RGB already contains brightness information
        if ATTR_RGBW_COLOR in kwargs:
            self._vals = list(kwargs[ATTR_RGBW_COLOR])

        if ATTR_HS_COLOR in kwargs:
            hue, sat = kwargs[ATTR_HS_COLOR]
            self._vals[0:3] = list(color_util.color_hs_to_RGB(hue, sat))

        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

        if ATTR_FLASH in kwargs:
            await super().flash(old_values, old_brightness, **kwargs)
        else:
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

        self._features = LightEntityFeature.TRANSITION | LightEntityFeature.FLASH
        self._color_mode = ColorMode.RGBWW
        self._supported_color_modes.add(ColorMode.RGBWW)
        self._supported_color_modes.add(ColorMode.COLOR_TEMP)
        self._supported_color_modes.add(ColorMode.HS)

        # Intentionally switching min and max here; it's inverted in the conversion.
        self._min_kelvin = convert_to_kelvin(kwargs[CONF_DEVICE_MIN_TEMP])
        self._max_kelvin = convert_to_kelvin(kwargs[CONF_DEVICE_MAX_TEMP])
        self._vals = [255, 255, 255, 255, 255, (self._max_kelvin - self._min_kelvin) / 2]

        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "rgbch"
        validate(self._channel_setup, self.CONF_TYPE)

        self._channel_width = len(self._channel_setup)

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, red, green, blue, cold_white, warm_white, color_temp, _, _ = \
            from_values(self._channel_setup, self.channel_size[1], values)

        self._vals = (red, green, blue, cold_white, warm_white, color_temp)

        self._channel_value_change()

    @property
    def rgbww_color(self) -> tuple:
        """Return the rgbww color value."""
        return tuple(self._vals[0:5])

    @property
    def min_color_temp_kelvin(self) -> int:
        """Return the warmest color_temp_kelvin that this light supports."""
        return self._min_kelvin

    @property
    def max_color_temp_kelvin(self) -> int:
        """Return the coldest color_temp_kelvin that this light supports."""
        return self._max_kelvin

    @property
    def color_temp_kelvin(self) -> int | None:
        return self._vals[5]

    def get_target_values(self):
        red = self._vals[0]
        green = self._vals[1]
        blue = self._vals[2]
        cold_white = self._vals[3]
        warm_white = self._vals[4]
        color_temperature_kelvin = self._vals[5]

        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness,
                         red, green, blue, cold_white, warm_white,
                         color_temp_kelvin=color_temperature_kelvin,
                         min_kelvin=self.min_color_temp_kelvin,
                         max_kelvin=self.max_color_temp_kelvin)

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """
        old_values = list(self._vals)
        old_brightness = self._attr_brightness

        # RGB already contains brightness information
        if ATTR_RGBWW_COLOR in kwargs:
            self._vals[0:5] = kwargs[ATTR_RGBWW_COLOR]

            if self._vals[3] != old_values[3] or self._vals[4] != old_values[4]:
                self._vals[5], _ = color_util.rgbww_to_color_temperature(
                    (self._vals[0], self._vals[1], self._vals[2], self._vals[3], self._vals[4]),
                    self.min_color_temp_kelvin, self.max_color_temp_kelvin
                )
                self._channel_value_change()

        if ATTR_HS_COLOR in kwargs:
            hue, sat = kwargs[ATTR_HS_COLOR]
            self._vals[0:3] = list(color_util.color_hs_to_RGB(hue, sat))

        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._vals[5] = kwargs[ATTR_COLOR_TEMP_KELVIN]
            _, _, _, self._vals[3], self._vals[4] = color_util.color_temperature_to_rgbww(
                self._vals[5], self._attr_brightness, self.min_color_temp_kelvin, self.max_color_temp_kelvin)
            self._channel_value_change()

        if ATTR_FLASH in kwargs:
            await super().flash(old_values, old_brightness, **kwargs)
        else:
            await super().async_create_fade(**kwargs)

        return None

    async def restore_state(self, old_state):
        log.debug("Added rgbww to hass. Try restoring state.")

        if old_state:
            prev_vals = old_state.attributes.get('values')
            if len(prev_vals) == 6:
                self._vals = prev_vals

            prev_brightness = old_state.attributes.get('bright')
            self._attr_brightness = prev_brightness

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._attr_brightness, rgbww_color=self._vals, transition=0)

class DmxXY(DmxBaseLight):
    CONF_TYPE = "xy"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._features = LightEntityFeature.TRANSITION | LightEntityFeature.FLASH
        self._color_mode = ColorMode.XY
        self._supported_color_modes.add(ColorMode.XY)

        self._vals = [0.0, 0.0]

        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "dxy"
        validate(self._channel_setup, self.CONF_TYPE)

        self._channel_width: LogicalChannelSize = len(self._channel_setup)

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, _, _, _, _, _, _, x, y = \
            from_values(self._channel_setup, self.channel_size[1], values)

        def normalize(value: int) -> float:
            return value / 255.0
        
        self._vals = (normalize(x), normalize(y))

        self._channel_value_change()

    @property
    def xy_color(self) -> tuple:
        """Return the xy color value."""
        return tuple(self._vals[0:2])

    def get_target_values(self):
        x = self._vals[0]
        y = self._vals[1]

        log.debug("get_target_values: x=%s, y=%s, brightness=%s, channel_size=%s", x, y, self._attr_brightness, self._channel_size[1])

        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness,
                         x=x, y=y)

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """
        old_values = list(self._vals)
        old_brightness = self._attr_brightness

        if ATTR_XY_COLOR in kwargs:
            log.debug(kwargs)
            
            self._vals = kwargs[ATTR_XY_COLOR]

            if self._vals[0] != old_values[0] or self._vals[1] != old_values[1]:
                self._channel_value_change()

        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

        if ATTR_FLASH in kwargs:
            await super().flash(old_values, old_brightness, **kwargs)
        else:
            await super().async_create_fade(**kwargs)

        return None

    async def restore_state(self, old_state):
        log.debug("Added xy to hass. Try restoring state.")

        if old_state:
            prev_vals = old_state.attributes.get('values')
            if len(prev_vals) == 2:
                self._vals = prev_vals

            prev_brightness = old_state.attributes.get('bright')
            self._attr_brightness = prev_brightness

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._attr_brightness, xy_color=self._vals, transition=0)


# ------------------------------------------------------------------------------
# conf
# ------------------------------------------------------------------------------

__CLASS_LIST = [DmxDimmer, DmxRGB, DmxWhite, DmxRGBW, DmxRGBWW, DmxBinary, DmxFixed, DmxTrigger, DmxXY]
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
        vol.Optional(CONF_NODE_HOST_OVERRIDE, default=""): cv.string,
        vol.Optional(CONF_NODE_PORT): cv.port,
        vol.Optional(CONF_NODE_PORT_OVERRIDE): cv.port,
        vol.Optional(CONF_NODE_MAX_FPS, default=25): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=50)
        ),
        vol.Optional(CONF_NODE_REFRESH, default=120): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=9999)
        ),
        vol.Optional(CONF_NODE_TYPE, default="artnet-direct"): vol.Any(
            None, vol.In(["artnet-direct", "artnet-controller", "sacn", "kinet"])
        ),
    },
    required=True,
    extra=vol.PREVENT_EXTRA,
)
