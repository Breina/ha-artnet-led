from __future__ import annotations

import logging
import time
import functools

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
    LightEntity, COLOR_MODE_ONOFF, COLOR_MODE_WHITE,
)
from homeassistant.util.color import color_rgb_to_rgbw
from homeassistant.const import CONF_DEVICES, STATE_OFF, STATE_ON
from homeassistant.const import CONF_FRIENDLY_NAME as CONF_DEVICE_FRIENDLY_NAME
from homeassistant.const import CONF_HOST as CONF_NODE_HOST
from homeassistant.const import CONF_NAME as CONF_DEVICE_NAME
from homeassistant.const import CONF_PORT as CONF_NODE_PORT
from homeassistant.const import CONF_TYPE as CONF_DEVICE_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import async_get, RegistryEntry
from homeassistant.helpers.restore_state import RestoreEntity

CONF_DEVICE_TRANSITION = ATTR_TRANSITION

CONF_INITIAL_VALUES = "initial_values"
CONF_SEND_PARTIAL_UNIVERSE = "send_partial_universe"

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

REQUIREMENTS = ["pyartnet == 0.8.3"]

log.info(f"PyArtNet: {REQUIREMENTS[0]}")
log.info(f"Version : 2021.07.10")

CONF_NODE_MAX_FPS = "max_fps"
CONF_NODE_REFRESH = "refresh_every"
CONF_NODE_UNIVERSES = "universes"

CONF_DEVICE_CHANNEL = "channel"
CONF_DEVICE_VALUE = "value"
CONF_OUTPUT_CORRECTION = "output_correction"
CONF_CHANNEL_SIZE = "channel_size"

CONF_DEVICE_MIN_TEMP = "min_temp"
CONF_DEVICE_MAX_TEMP = "max_temp"
CONF_CHANNEL_SETUP = "channel_setup"

DOMAIN = "dmx"

AVAILABLE_CORRECTIONS = {
    "linear": None,
    "quadratic": None,
    "cubic": None,
    "quadruple": None,
}


def linear_output_correction(val: float, max_val: int = 0xFF):
    return val


AVAILABLE_CORRECTIONS["linear"] = linear_output_correction
AVAILABLE_CORRECTIONS["quadratic"] = pyartnet.output_correction.quadratic
AVAILABLE_CORRECTIONS["cubic"] = pyartnet.output_correction.cubic
AVAILABLE_CORRECTIONS["quadruple"] = pyartnet.output_correction.quadruple

CHANNEL_SIZE = {
    "8bit": (1, pyartnet.DmxChannel, 1),
    "16bit": (2, pyartnet.DmxChannel16Bit, 256),
    "24bit": (3, pyartnet.DmxChannel24Bit, 256 * 256),
    "32bit": (4, pyartnet.DmxChannel32Bit, 256 ** 3),
}

ARTNET_NODES = {}


async def async_setup_platform(hass: HomeAssistant, config, async_add_devices, discovery_info=None):
    import pprint

    for line in pprint.pformat(config).splitlines():
        log.info(line)

    host = config.get(CONF_NODE_HOST)
    port = config.get(CONF_NODE_PORT)

    # setup Node
    __id = f"{host}:{port}"
    if __id not in ARTNET_NODES:
        __node = pyartnet.ArtNetNode(
            host,
            port,
            max_fps=config[CONF_NODE_MAX_FPS],
            refresh_every=config[CONF_NODE_REFRESH],
        )
        await __node.start()
        ARTNET_NODES[id] = __node
    node = ARTNET_NODES[id]
    assert isinstance(node, pyartnet.ArtNetNode), type(node)

    entity_registry = async_get(hass)
    await entity_registry.async_load()

    device_list = []
    used_unique_ids = []
    for universe_nr, universe_cfg in config[CONF_NODE_UNIVERSES].items():
        try:
            universe = node.get_universe(universe_nr)
        except KeyError:
            universe = node.add_universe(universe_nr)
            universe.output_correction = AVAILABLE_CORRECTIONS.get(
                universe_cfg[CONF_OUTPUT_CORRECTION]
            )

        if CONF_INITIAL_VALUES in universe_cfg.keys():
            for _ in universe_cfg[CONF_INITIAL_VALUES]:  # type: dict
                pass

        for device in universe_cfg[CONF_DEVICES]:  # type: dict
            device = device.copy()
            cls = __CLASS_TYPE[device[CONF_DEVICE_TYPE]]

            channel = device[CONF_DEVICE_CHANNEL]
            unique_id = f"{DOMAIN}:{host}/{universe_nr}/{channel}"

            name: str = device[CONF_DEVICE_NAME]

            entity_id = f"light.{name.replace(' ', '_').lower()}"

            # If the entity has another unique ID, use that until it's migrated properly
            entity = entity_registry.async_get(entity_id)
            if entity:
                logging.info(f"Found existing entity for name {entity_id}, using unique id {unique_id}")
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
                    channel_type=d.channel_size[1],
                )
            )

            d.channel.output_correction = AVAILABLE_CORRECTIONS.get(
                device[CONF_OUTPUT_CORRECTION]
            )

            d.set_initial_brightness(device[CONF_DEVICE_VALUE])

            device_list.append(d)

            send_partial_universe = universe_cfg[CONF_SEND_PARTIAL_UNIVERSE]
            if not send_partial_universe and universe.highest_channel != 512:
                universe.add_channel(start=512, width=1, channel_name="Full universe hack")

    async_add_devices(device_list)

    return True


def convert_to_mireds(kelvin_string):
    kelvin_number = int(kelvin_string[:-1])
    return color_util.color_temperature_kelvin_to_mired(kelvin_number)


class DmxBaseLight(LightEntity, RestoreEntity):
    def __init__(self, name, unique_id: str, **kwargs):
        self._name = name
        self._channel = kwargs[CONF_DEVICE_CHANNEL]

        self._unique_id = unique_id

        self.entity_id = f"light.{name.replace(' ', '_').lower()}"
        self._brightness = 255
        self._attr_brightness = self._brightness
        self._fade_time = kwargs[CONF_DEVICE_TRANSITION]
        self._transition = self._fade_time
        self._state = False
        self._channel_size = CHANNEL_SIZE[kwargs[CONF_CHANNEL_SIZE]]
        self._color_mode = kwargs[CONF_DEVICE_TYPE]
        self._vals = 0
        self._features = 0
        self._supported_color_modes = set()
        # channel & notification callbacks
        # noinspection PyTypeHints
        self._channel: self._channel_size[1] = None
        self._channel_last_update = 0
        self._scale_factor = 1
        self._channel_width = 0
        self._type = None

    def set_channel(self, channel):
        """Set the channel & the callbacks"""
        self._channel = channel
        self._channel.callback_value_changed = self._channel_value_change
        self._channel.callback_fade_finished = self._channel_fade_finish

    def set_type(self, type):
        self._type = type

    def set_initial_brightness(self, brightness):
        self._brightness = brightness

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def unique_id(self):
        """Return unique ID for light."""
        return self._unique_id

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return self._brightness

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
        data = {"type": self._type,
                "dmx_channels": [
                    k for k in range(
                        self._channel.start, self._channel.start + self._channel.width, 1
                    )
                ],
                "dmx_values": self._channel.get_channel_values(),
                "values": self._vals,
                "bright": self._brightness,
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

    def _channel_value_change(self, channel):
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

        self._channel.add_fade(
            self.get_target_values(), self._transition * 1000, pyartnet.fades.LinearFade
        )

        self.async_schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        """
        Instruct the light to turn off. If a transition time has been specified in seconds
        the controller will fade.
        """
        self._transition = kwargs.get(ATTR_TRANSITION, self._fade_time)

        logging.debug(
            "Turning off '%s' with transition  %i", self._name, self._transition
        )
        self._channel.add_fade(
            [0 for _ in range(self._channel.width)],
            self._transition * 1000,
            pyartnet.fades.LinearFade,
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
        return [self.brightness * self._channel_size[2]]

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

    def get_target_values(self):
        return [self.brightness * self._channel_size[2]]

    async def async_turn_on(self, **kwargs):
        self._state = True
        self._brightness = 255
        self._channel.add_fade(
            self.get_target_values(), 0, pyartnet.fades.LinearFade
        )
        self.async_schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        self._state = False
        self._brightness = 0
        self._channel.add_fade(
            self.get_target_values(), 0, pyartnet.fades.LinearFade
        )
        self.async_schedule_update_ha_state()

    async def restore_state(self, old_state):
        log.debug("Added binary light to hass. Try restoring state.")
        self._state = old_state.state
        self._brightness = old_state.attributes.get('bright')

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

    def get_target_values(self):
        return [self.brightness * self._channel_size[2]]

    async def async_turn_on(self, **kwargs):

        # Update state from service call
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]

        await super().async_create_fade(**kwargs)

    async def restore_state(self, old_state):
        log.debug("Added dimmer to hass. Try restoring state.")

        if old_state:
            prev_brightness = old_state.attributes.get('bright')
            self._brightness = prev_brightness

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._brightness, transition=0)


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

    def get_target_values(self):
        # d = dimmer
        # c = cool (scaled for brightness)
        # C = cool (not scaled)
        # h = hot (scaled for brightness)
        # H = hot (not scaled)
        # t = temperature (0 = hot, 255 = cold)
        # T = temperature (255 = hot, 0 = cold)

        ww_fraction = (self.color_temp - self.min_mireds) \
                      / (self.max_mireds - self.min_mireds)
        cw_fraction = 1 - ww_fraction
        max_fraction = max(ww_fraction, cw_fraction)

        switcher = {
            "d": lambda: self._brightness,
            "c": lambda: self.is_on * self._brightness * (cw_fraction / max_fraction),
            "C": lambda: self.is_on * cw_fraction * 255 / max_fraction,
            "h": lambda: self.is_on * self._brightness * (ww_fraction / max_fraction),
            "H": lambda: self.is_on * ww_fraction * 255 / max_fraction,
            "t": lambda: 255 - (ww_fraction * 255),
            "T": lambda: ww_fraction * 255
        }

        values = list()
        for channel in self._channel_setup:
            calculation_function = switcher.get(channel, functools.partial(self._default_calculation_function, channel))
            value = calculation_function()
            if value < 0 or value > 256:
                log.warning(f"Value for channel {channel} isn't within bound: {value}")
                value = max(0, min(256, value))
            values.append(int(round(value * self._channel_size[2])))

        return values

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """
        if ATTR_COLOR_TEMP in kwargs:
            self._vals = kwargs[ATTR_COLOR_TEMP]

        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]
            self._scale_factor = self._brightness / 255

        await super().async_create_fade(**kwargs)
        return None

    async def restore_state(self, old_state):
        log.debug("Added color_temp to hass. Try restoring state.")

        if old_state:
            prev_vals = old_state.attributes.get('values')
            self._vals = prev_vals
            prev_brightness = old_state.attributes.get('bright')
            self._brightness = prev_brightness

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._brightness, rgb_color=self._vals, transition=0)


class DmxRGB(DmxBaseLight):
    CONF_TYPE = "rgb"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._supported_color_modes.add(COLOR_MODE_RGB)
        self._features = SUPPORT_TRANSITION
        self._color_mode = COLOR_MODE_RGB
        self._vals = (255, 255, 255)

        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "rgb"
        self._channel_width = len(self._channel_setup)

        self._auto_scale_white = "w" in self._channel_setup or "W" in self._channel_setup

    @property
    def rgb_color(self) -> tuple:
        """Return the rgb color value."""
        return self._vals

    def get_target_values(self):
        # d = dimmer
        # r = red (scaled for brightness)
        # R = red (not scaled)
        # g = green (scaled for brightness)
        # G = green (not scaled)
        # b = blue (scaled for brightness)
        # B = blue (not scaled)
        # w = white (automatically calculated, scaled for brightness)
        # W = white (automatically calculated, not scaled)

        red = self._vals[0]
        green = self._vals[1]
        blue = self._vals[2]

        if self._auto_scale_white:
            red, green, blue, white = color_rgb_to_rgbw(red, green, blue)

        max_color = max(1, max(self._vals))

        switcher = {
            "d": lambda: self._brightness,
            "r": lambda: self.is_on * red * self._brightness / max_color,
            "R": lambda: self.is_on * red * 255 / max_color,
            "g": lambda: self.is_on * green * self._brightness / max_color,
            "G": lambda: self.is_on * green * 255 / max_color,
            "b": lambda: self.is_on * blue * self._brightness / max_color,
            "B": lambda: self.is_on * blue * 255 / max_color,
            "w": lambda: self.is_on * white * self._brightness / max_color,
            "W": lambda: self.is_on * white * 255 / max_color
        }

        values = list()
        for channel in self._channel_setup:
            calculation_function = switcher.get(channel, functools.partial(self._default_calculation_function, channel))
            value = calculation_function()
            if value < 0 or value > 256:
                log.warning(f"Value for channel {channel} isn't within bound: {value}")
                value = max(0, min(256, value))
            values.append(int(round(value * self._channel_size[2])))

        return values

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """

        # RGB already contains brightness information
        if ATTR_RGB_COLOR in kwargs:
            self._vals = kwargs[ATTR_RGB_COLOR]

        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]
            self._scale_factor = self._brightness / 255

        await super().async_create_fade(**kwargs)
        return None

    async def restore_state(self, old_state):
        log.debug("Added rgb to hass. Try restoring state.")

        if old_state:
            prev_vals = old_state.attributes.get('values')
            self._vals = prev_vals
            prev_brightness = old_state.attributes.get('bright')
            self._brightness = prev_brightness

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._brightness, rgb_color=self._vals, transition=0)


class DmxRGBW(DmxBaseLight):
    CONF_TYPE = "rgbw"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._supported_color_modes.add(COLOR_MODE_RGBW)
        self._features = SUPPORT_TRANSITION
        self._color_mode = COLOR_MODE_RGBW
        self._vals = (255, 255, 255, 255)

        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "rgbw"
        self._channel_width = len(self._channel_setup)

    @property
    def rgbw_color(self) -> tuple:
        """Return the rgbw color value."""
        return self._vals

    def get_target_values(self):
        # d = dimmer
        # r = red (scaled for brightness)
        # R = red (not scaled)
        # g = green (scaled for brightness)
        # G = green (not scaled)
        # b = blue (scaled for brightness)
        # B = blue (not scaled)
        # w = white (scaled for brightness)
        # W = white (not scaled)

        red = self._vals[0]
        green = self._vals[1]
        blue = self._vals[2]
        white = self._vals[3]

        max_color = max(1, max(self._vals))

        switcher = {
            "d": lambda: self._brightness,
            "r": lambda: self.is_on * red * self._brightness / max_color,
            "R": lambda: self.is_on * red * 255 / max_color,
            "g": lambda: self.is_on * green * self._brightness / max_color,
            "G": lambda: self.is_on * green * 255 / max_color,
            "b": lambda: self.is_on * blue * self._brightness / max_color,
            "B": lambda: self.is_on * blue * 255 / max_color,
            "w": lambda: self.is_on * white * self._brightness / max_color,
            "W": lambda: self.is_on * white * 255 / max_color,
        }

        values = list()
        for channel in self._channel_setup:
            calculation_function = switcher.get(channel, functools.partial(self._default_calculation_function, channel))
            log.info(f"DEBUGGY for {channel}: {calculation_function()}")
            value = calculation_function()
            if value < 0 or value > 256:
                log.warning(f"Value for channel {channel} isn't within bound: {value}")
                value = max(0, min(256, value))
            values.append(int(round(value * self._channel_size[2])))

        return values

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """
        # RGB already contains brightness information
        if ATTR_RGBW_COLOR in kwargs:
            self._vals = kwargs[ATTR_RGBW_COLOR]
            # self._scale_factor = 1

        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]
            self._scale_factor = self._brightness / 255

        await super().async_create_fade(**kwargs)
        return None

    async def restore_state(self, old_state):
        log.debug("Added rgbw to hass. Try restoring state.")

        if old_state:
            prev_vals = old_state.attributes.get('values')
            self._vals = prev_vals

            prev_brightness = old_state.attributes.get('bright')
            self._brightness = prev_brightness

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._brightness, rgbw_color=self._vals, transition=0)


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
        self._channel_width = len(self._channel_setup)

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
        # d = dimmer
        # r = red (scaled for brightness)
        # R = red (not scaled)
        # g = green (scaled for brightness)
        # G = green (not scaled)
        # b = blue (scaled for brightness)
        # B = blue (not scaled)
        # c = cool (scaled for brightness)
        # C = cool (not scaled)
        # h = hot (scaled for brightness)
        # H = hot (not scaled)
        # t = temperature (0 = hot, 255 = cold)
        # T = temperature (255 = hot, 0 = cold)

        red = self._vals[0]
        green = self._vals[1]
        blue = self._vals[2]
        cold_white = self._vals[3]
        warm_white = self._vals[4]

        max_color = max(1, max(self._vals))

        switcher = {
            "d": lambda: self._brightness,
            "r": lambda: self.is_on * red * self._brightness / max_color,
            "R": lambda: self.is_on * red * 255 / max_color,
            "g": lambda: self.is_on * green * self._brightness / max_color,
            "G": lambda: self.is_on * green * 255 / max_color,
            "b": lambda: self.is_on * blue * self._brightness / max_color,
            "B": lambda: self.is_on * blue * 255 / max_color,
            "c": lambda: self.is_on * cold_white * self._brightness / max_color,
            "C": lambda: self.is_on * cold_white * 255 / max_color,
            "h": lambda: self.is_on * warm_white * self._brightness / max_color,
            "H": lambda: self.is_on * warm_white * 255 / max_color,
            "t": lambda: 255 - ((self.color_temp - self.min_mireds) / (self.max_mireds - self.min_mireds) * 255),
            "T": lambda: (self.color_temp - self.min_mireds) / (self.max_mireds - self.min_mireds) * 255
        }

        values = list()
        for channel in self._channel_setup:
            calculation_function = switcher.get(channel, functools.partial(self._default_calculation_function, channel))
            value = calculation_function()
            if value < 0 or value > 256:
                log.warning(f"Value for channel {channel} isn't within bound: {value}")
                value = max(0, min(256, value))
            values.append(int(round(value * self._channel_size[2])))

        return values

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """

        # RGB already contains brightness information
        if ATTR_RGBWW_COLOR in kwargs:
            self._vals = kwargs[ATTR_RGBWW_COLOR]
            # self._scale_factor = 1

        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]
            self._scale_factor = self._brightness / 255

        await super().async_create_fade(**kwargs)
        return None

    async def restore_state(self, old_state):
        log.debug("Added rgbww to hass. Try restoring state.")

        if old_state:
            prev_vals = old_state.attributes.get('values')
            self._vals = prev_vals

            prev_brightness = old_state.attributes.get('bright')
            self._brightness = prev_brightness
            self._scale_factor = self._brightness / 255

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._brightness, rgbww_color=self._vals, transition=0)


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
                vol.Optional(CONF_OUTPUT_CORRECTION, default=None): vol.Any(
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
                            vol.Optional(CONF_OUTPUT_CORRECTION, default=None): vol.Any(
                                None, vol.In(AVAILABLE_CORRECTIONS)
                            ),
                            vol.Optional(CONF_CHANNEL_SIZE, default="8bit"): vol.Any(
                                None, vol.In(CHANNEL_SIZE)
                            ),
                            vol.Optional(CONF_DEVICE_VALUE, default=0): vol.All(
                                vol.Coerce(int), vol.Range(min=0, max=255)
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
                ),
                vol.Optional(CONF_INITIAL_VALUES): vol.All(
                    cv.ensure_list,
                    [
                        {
                            vol.Required(CONF_DEVICE_CHANNEL): vol.All(
                                vol.Coerce(int), vol.Range(min=1, max=512)
                            ),
                            vol.Required(CONF_DEVICE_VALUE): vol.All(
                                vol.Coerce(int), vol.Range(min=0, max=255)
                            ),
                        }
                    ],
                ),
            },
        },
        vol.Optional(CONF_NODE_PORT, default=6454): cv.port,
        vol.Optional(CONF_NODE_MAX_FPS, default=25): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=50)
        ),
        vol.Optional(CONF_NODE_REFRESH, default=120): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=9999)
        ),
    },
    required=True,
    extra=vol.PREVENT_EXTRA,
)
