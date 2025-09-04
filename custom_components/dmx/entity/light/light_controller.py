import logging
from typing import Dict, Any, Optional, List

from homeassistant.components.light import ATTR_TRANSITION

from custom_components.dmx.entity.light import ChannelType, ChannelMapping
from custom_components.dmx.entity.light.light_state import LightState
from custom_components.dmx.io.dmx_io import DmxUniverse

log = logging.getLogger(__name__)


class LightController:
    def __init__(self, state: LightState, universe: DmxUniverse, channel_mappings: Optional[List[ChannelMapping]] = None, animation_engine = None):
        self.state = state
        self.universe = universe
        self.channel_mappings = channel_mappings
        self.animation_engine = animation_engine
        self.is_updating = False
        self._current_animation_id: Optional[str] = None

    async def turn_on(self, **kwargs):
        self.state.is_on = True
        updates = self._collect_updates_from_kwargs(kwargs)
        if not updates:
            updates = self._restore_previous_state()
        
        transition = kwargs.get(ATTR_TRANSITION)
        await self._apply_updates(updates, transition)

    async def turn_off(self, transition: Optional[float] = None):
        self.state.is_on = False
        preserved = self._capture_current_state()
        updates = {}

        if self.state.has_channel(ChannelType.DIMMER):
            self.state.update_brightness(0)
            updates[ChannelType.DIMMER] = 0
        else:
            self.state.reset()
            for channel in self.state.channels:
                if channel != ChannelType.COLOR_TEMPERATURE:
                    updates[channel] = 0

        await self._apply_updates(updates, transition)
        self._save_last_state(preserved)

    async def _apply_updates(self, updates: Dict[ChannelType, int], transition: Optional[float] = None):
        if self._current_animation_id and self.animation_engine:
            self.animation_engine.cancel_animation(self._current_animation_id)
            self._current_animation_id = None
        
        # If no animation engine, channel mappings, or no transition requested, apply immediately
        if not transition or transition <= 0 or not self.animation_engine or not self.channel_mappings:
            for ct, val in updates.items():
                self.state.apply_channel_update(ct, val)
            dmx_updates = self.state.get_dmx_updates(updates)
            await self.universe.update_multiple_values(dmx_updates)
            return
        
        current_values = {}
        for channel_type in updates.keys():
            current_entity_value = 0
            dmx_values = []
            for mapping in self.channel_mappings:
                if mapping.channel_type == channel_type:
                    # Get all DMX values for this channel (handles multi-byte channels properly)
                    dmx_values = [self.universe.get_channel_value(idx) for idx in mapping.dmx_indexes]
                    
                    # Convert DMX values to entity value using the dynamic entity
                    [dynamic_entity] = mapping.channel.capabilities[0].dynamic_entities
                    normalized_value = dynamic_entity.from_dmx_fine(dmx_values)
                    current_entity_value = dynamic_entity.unnormalize(normalized_value)
                    break
            
            current_values[channel_type] = int(current_entity_value)
        
        relevant_mappings = [mapping for mapping in self.channel_mappings
                           if mapping.channel_type in updates.keys()]
        
        if relevant_mappings:
            log.debug(f"Creating animation with {len(relevant_mappings)} mappings, current: {current_values}, desired: {updates}")
            # Create animation with L*U*V* transitions
            self._current_animation_id = self.animation_engine.create_animation(
                channel_mappings=relevant_mappings,
                current_values=current_values,
                desired_values=updates,
                animation_duration_seconds=transition,
                min_kelvin=getattr(self.state.converter, 'min_kelvin', 2700),
                max_kelvin=getattr(self.state.converter, 'max_kelvin', 6500)
            )
            
            # Update state to target values immediately (for UI consistency)
            for ct, val in updates.items():
                self.state.apply_channel_update(ct, val)

    def _collect_updates_from_kwargs(self, kwargs: Dict[str, Any]) -> Dict[ChannelType, int]:
        updates = {}

        if "brightness" in kwargs:
            brightness = kwargs["brightness"]
            brightness_updates = self.state.get_scaled_brightness_updates(brightness)
            updates.update(brightness_updates)

        if "rgb_color" in kwargs and self.state.has_rgb():
            r, g, b = kwargs["rgb_color"]
            updates.update({ChannelType.RED: r, ChannelType.GREEN: g, ChannelType.BLUE: b})

        if "rgbw_color" in kwargs:
            r, g, b, w = kwargs["rgbw_color"]
            updates.update({ChannelType.RED: r, ChannelType.GREEN: g, ChannelType.BLUE: b, ChannelType.WARM_WHITE: w})

        if "rgbww_color" in kwargs:
            r, g, b, cw, ww = kwargs["rgbww_color"]
            updates.update({ChannelType.RED: r, ChannelType.GREEN: g, ChannelType.BLUE: b,ChannelType.COLD_WHITE: cw, ChannelType.WARM_WHITE: ww})

        if "color_temp_kelvin" in kwargs:
            kelvin = kwargs["color_temp_kelvin"]
            self.state.update_color_temp_kelvin(kelvin)
            brightness = kwargs.get("brightness", self.state.brightness)
            
            if brightness is None:
                brightness = 255

            if self.state.has_channel(ChannelType.COLOR_TEMPERATURE):
                updates[ChannelType.COLOR_TEMPERATURE] = self.state.color_temp_dmx
            elif self.state.has_cw_ww():
                cw, ww = self.state.converter.temp_to_cw_ww(kelvin, brightness)
                updates.update({ChannelType.COLD_WHITE: cw, ChannelType.WARM_WHITE: ww})

        return updates

    def _restore_previous_state(self) -> Dict[ChannelType, int]:
        updates = {}
        if self.state.has_channel(ChannelType.DIMMER):
            updates[ChannelType.DIMMER] = self.state.last_brightness

        if self.state.has_rgb():
            r, g, b = self.state.last_rgb
            updates.update({ChannelType.RED: r, ChannelType.GREEN: g, ChannelType.BLUE: b})

        if self.state.has_channel(ChannelType.COLD_WHITE):
            updates[ChannelType.COLD_WHITE] = self.state.last_cold_white
        if self.state.has_channel(ChannelType.WARM_WHITE):
            updates[ChannelType.WARM_WHITE] = self.state.last_warm_white
        if self.state.has_channel(ChannelType.COLOR_TEMPERATURE):
            updates[ChannelType.COLOR_TEMPERATURE] = self.state.last_color_temp_dmx

        return updates

    def _capture_current_state(self) -> dict:
        return {
            'brightness': self.state.brightness,
            'rgb': self.state.rgb,
            'cold_white': self.state.cold_white,
            'warm_white': self.state.warm_white,
            'color_temp_kelvin': self.state.color_temp_kelvin,
            'color_temp_dmx': self.state.color_temp_dmx
        }

    def _save_last_state(self, s: dict):
        self.state.last_brightness = s['brightness']
        self.state.last_rgb = s['rgb']
        self.state.last_cold_white = s['cold_white']
        self.state.last_warm_white = s['warm_white']
        self.state.last_color_temp_kelvin = s['color_temp_kelvin']
        self.state.last_color_temp_dmx = s['color_temp_dmx']
