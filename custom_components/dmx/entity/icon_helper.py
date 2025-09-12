from collections import Counter

from custom_components.dmx.fixture.channel import Channel


def determine_icon(channel: Channel) -> str:
    """
    Determine the most appropriate icon for a SelectEntity based on the
    capabilities of its associated channel.

    Args:
        channel: The channel containing capabilities to analyze

    Returns:
        MDI icon string representing the primary function of the channel
    """
    if not channel.capabilities:
        return "mdi:help-circle-outline"

    capability_icons = {
        "ShutterStrobe": "mdi:flash",
        "StrobeSpeed": "mdi:flash",
        "StrobeDuration": "mdi:flash",
        "Intensity": "mdi:brightness-6",
        "ColorIntensity": "mdi:palette",
        "ColorPreset": "mdi:palette",
        "ColorTemperature": "mdi:thermometer",
        "Pan": "mdi:pan-horizontal",
        "PanContinuous": "mdi:pan-horizontal",
        "Tilt": "mdi:pan-vertical",
        "TiltContinuous": "mdi:pan-vertical",
        "PanTiltSpeed": "mdi:speedometer",
        "WheelSlot": "mdi:circle-slice-4",
        "WheelShake": "mdi:vibrate",
        "WheelSlotRotation": "mdi:rotate-right",
        "WheelRotation": "mdi:rotate-right",
        "Rotation": "mdi:rotate-right",
        "Effect": "mdi:star-four-points",
        "EffectSpeed": "mdi:speedometer",
        "EffectDuration": "mdi:timer",
        "EffectParameter": "mdi:tune",
        "BeamAngle": "mdi:angle-acute",
        "BeamPosition": "mdi:crosshairs",
        "Focus": "mdi:focus-field",
        "Zoom": "mdi:magnify",
        "Iris": "mdi:camera-iris",
        "IrisEffect": "mdi:camera-iris",
        "Frost": "mdi:snowflake",
        "FrostEffect": "mdi:snowflake",
        "Fog": "mdi:weather-fog",
        "FogOutput": "mdi:weather-fog",
        "FogType": "mdi:weather-fog",
        "Prism": "mdi:triangle",
        "PrismRotation": "mdi:triangle",
        "BladeInsertion": "mdi:content-cut",
        "BladeRotation": "mdi:content-cut",
        "BladeSystemRotation": "mdi:content-cut",
        "SoundSensitivity": "mdi:microphone",
        "Speed": "mdi:speedometer",
        "Time": "mdi:clock",
        "Maintenance": "mdi:wrench",
        "Generic": "mdi:tune",
        "NoFunction": "mdi:minus-circle-outline",
    }

    capabilities_list = channel.capabilities if isinstance(channel.capabilities, list) else [channel.capabilities]
    capability_types = [type(cap).__name__ for cap in capabilities_list]
    capability_counts = Counter(capability_types)

    priority_order = [
        "ColorPreset",
        "ColorIntensity",
        "ColorTemperature",
        "ShutterStrobe",
        "StrobeSpeed",
        "StrobeDuration",
        "Pan",
        "Tilt",
        "PanContinuous",
        "TiltContinuous",
        "Effect",
        "EffectSpeed",
        "EffectDuration",
        "Intensity",
        "WheelSlot",
        "WheelRotation",
        "Rotation",
        "Focus",
        "Zoom",
        "BeamAngle",
        "Fog",
        "FogOutput",
        "Generic",
        "Maintenance",
    ]

    if capability_counts:
        max_count = max(capability_counts.values())
        most_common = [cap for cap, count in capability_counts.items() if count == max_count]

        for priority_cap in priority_order:
            if priority_cap in most_common:
                return capability_icons.get(priority_cap, "mdi:tune")

        primary_capability = most_common[0]
        return capability_icons.get(primary_capability, "mdi:tune")

    return "mdi:help-circle-outline"
