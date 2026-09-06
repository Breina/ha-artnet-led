"""Pure migration logic: artnet_led (old) → dmx (new) configuration format.

No Home Assistant or I/O dependencies — all functions here are safe to call
from tests, from tools/migrate.py, or via hass.async_add_executor_job().
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

OFL_SCHEMA = (
    "https://raw.githubusercontent.com/OpenLightingProject/open-fixture-library"
    "/schema-12.5.0/schemas/fixture.json"
)

DEFAULT_CHANNEL_SETUP: dict[str, str | list] = {
    "dimmer": "d",
    "binary": "d",
    "color_temp": "ch",
    "rgb": "rgb",
    "rgbw": "rgbw",
    "rgbww": "rgbch",
    "xy": "dxy",
    "fixed": [255],
}

LETTER_CHANNEL_NAME: dict[str, str] = {
    "d": "Intensity",
    "r": "Red", "R": "Red",
    "g": "Green", "G": "Green",
    "b": "Blue", "B": "Blue",
    "w": "White", "W": "White",
    "c": "Cold White", "C": "Cold White",
    "h": "Warm White", "H": "Warm White",
    "t": "Color Temperature", "T": "Color Temperature",
    "u": "Hue", "U": "Saturation",
    "x": "CIE X", "y": "CIE Y",
}

LETTER_CAPABILITY: dict[str, dict] = {
    "d": {"type": "Intensity"},
    "r": {"type": "ColorIntensity", "color": "Red"},
    "R": {"type": "ColorIntensity", "color": "Red"},
    "g": {"type": "ColorIntensity", "color": "Green"},
    "G": {"type": "ColorIntensity", "color": "Green"},
    "b": {"type": "ColorIntensity", "color": "Blue"},
    "B": {"type": "ColorIntensity", "color": "Blue"},
    "w": {"type": "ColorIntensity", "color": "White"},
    "W": {"type": "ColorIntensity", "color": "White"},
    "c": {"type": "ColorIntensity", "color": "Cold White"},
    "C": {"type": "ColorIntensity", "color": "Cold White"},
    "h": {"type": "ColorIntensity", "color": "Warm White"},
    "H": {"type": "ColorIntensity", "color": "Warm White"},
    # t/T are built dynamically with kelvin values
    "u": {"type": "Generic", "comment": "Hue (migrated from channel_setup 'u')"},
    "U": {"type": "Generic", "comment": "Saturation (migrated from channel_setup 'U')"},
    "x": {"type": "Generic", "comment": "CIE 1931 XY color space -- X coordinate"},
    "y": {"type": "Generic", "comment": "CIE 1931 XY color space -- Y coordinate"},
}

FINE_ALIASES = {
    "8bit": [],
    "16bit": ["{name} fine"],
    "24bit": ["{name} fine", "{name} fine^2"],
    "32bit": ["{name} fine", "{name} fine^2", "{name} fine^3"],
}


# ---------------------------------------------------------------------------
# Fixture signature & generation
# ---------------------------------------------------------------------------

def _normalise_setup(setup: str | list | None, device_type: str) -> str | list:
    """Return a canonical channel_setup value."""
    if setup is None:
        return DEFAULT_CHANNEL_SETUP[device_type]
    if isinstance(setup, list):
        return setup
    return str(setup)


def _normalise_setup_for_sig(setup: str | list) -> str | tuple:
    """
    Normalise a channel_setup for use as a deduplication key.
    Upper/lowercase letters map to the same OFL capability EXCEPT t vs T
    (which differ in temperature direction), so we lowercase everything else.
    Integer lists are returned as-is as tuples.
    """
    if isinstance(setup, list):
        if all(isinstance(v, int) for v in setup):
            return tuple(setup)
        # list of strings — normalise same as a string
        return "".join(c.lower() if c not in "tT" else c for c in setup)
    return "".join(c.lower() if c not in "tT" else c for c in setup)


def device_fixture_signature(device: dict) -> tuple:
    """Return a deduplication key for fixture generation."""
    dtype = device.get("type", "dimmer")
    setup = _normalise_setup(device.get("channel_setup"), dtype)
    setup_key = _normalise_setup_for_sig(setup)
    return (
        dtype,
        setup_key,
        device.get("channel_size", "8bit"),
        device.get("byte_order", "big"),
        device.get("min_temp", "2700K"),
        device.get("max_temp", "6500K"),
    )


def _parse_kelvin(value: str) -> int:
    return int(re.sub(r"[kK]", "", value))


def _fine_alias_names(base_name: str, channel_size: str) -> list[str]:
    templates = FINE_ALIASES.get(channel_size, [])
    return [t.format(name=base_name) for t in templates]


def _channel_order_for_mode(base_name: str, channel_size: str, byte_order: str) -> list[str]:
    """Return the mode channel list for one logical channel (coarse + fine aliases)."""
    aliases = _fine_alias_names(base_name, channel_size)
    if byte_order == "little":
        # Most-significant fine alias first, then coarse last
        return list(reversed(aliases)) + [base_name]
    # big-endian (default): coarse first
    return [base_name] + aliases


def channel_setup_to_channels(
    setup: str | list,
    channel_size: str,
    byte_order: str,
    min_temp: str,
    max_temp: str,
) -> tuple[dict, list[str]]:
    """
    Build availableChannels dict and mode channel list from a channel_setup.
    Returns (available_channels, mode_channels).
    """
    available: dict[str, Any] = {}
    mode_channels: list[str] = []

    min_k = _parse_kelvin(min_temp)
    max_k = _parse_kelvin(max_temp)

    # fixed type: list of integers
    if isinstance(setup, list) and all(isinstance(v, int) for v in setup):
        for i, value in enumerate(setup):
            ch_name = f"Channel {i + 1}"
            available[ch_name] = {
                "constant": True,
                "defaultValue": value,
                "capability": {"type": "NoFunction"},
            }
            mode_channels.append(ch_name)
        return available, mode_channels

    # string or list-of-strings setup
    letters: list[str] = list(setup) if isinstance(setup, str) else [str(s) for s in setup]

    # Deduplicate channel names: if the same name appears twice (e.g. "rr"),
    # suffix with an index to keep them distinct.
    name_count: dict[str, int] = {}
    for letter in letters:
        base = LETTER_CHANNEL_NAME.get(letter, f"Unknown ({letter})")
        name_count[base] = name_count.get(base, 0) + 1
    name_seen: dict[str, int] = {}

    for letter in letters:
        base = LETTER_CHANNEL_NAME.get(letter, f"Unknown ({letter})")
        if name_count[base] > 1:
            name_seen[base] = name_seen.get(base, 0) + 1
            ch_name = f"{base} {name_seen[base]}"
        else:
            ch_name = base

        if letter in ("t", "T"):
            if letter == "t":
                cap = {
                    "type": "ColorTemperature",
                    "colorTemperatureStart": f"{min_k}K",
                    "colorTemperatureEnd": f"{max_k}K",
                }
            else:
                cap = {
                    "type": "ColorTemperature",
                    "colorTemperatureStart": f"{max_k}K",
                    "colorTemperatureEnd": f"{min_k}K",
                }
        elif letter in LETTER_CAPABILITY:
            cap = dict(LETTER_CAPABILITY[letter])
        else:
            cap = {"type": "Generic", "comment": f"Unknown channel_setup letter '{letter}'"}

        ch_def: dict[str, Any] = {"capability": cap}

        aliases = _fine_alias_names(ch_name, channel_size)
        if aliases:
            ch_def["fineChannelAliases"] = aliases

        available[ch_name] = ch_def
        mode_channels.extend(_channel_order_for_mode(ch_name, channel_size, byte_order))

    return available, mode_channels


def _fixture_name_for_sig(sig: tuple) -> str:
    dtype, setup_key, channel_size, byte_order, min_temp, max_temp = sig
    if isinstance(setup_key, tuple):
        # fixed type with integer values
        vals = "-".join(str(v) for v in setup_key)
        base = f"migrated-fixed-{vals}"
    else:
        default_setup = DEFAULT_CHANNEL_SETUP.get(dtype, "")
        default_key = tuple(default_setup) if isinstance(default_setup, list) else default_setup
        if setup_key == default_key:
            base = f"migrated-{dtype}"
        else:
            slug = re.sub(r"[^a-zA-Z0-9]", "", str(setup_key)).lower()
            base = f"migrated-{dtype}-{slug}"
    if channel_size != "8bit":
        base += f"-{channel_size}"
    if byte_order != "big":
        base += "-le"
    return base


def generate_fixture(sig: tuple) -> dict:
    """Build an OFL-compatible fixture dict from a device signature."""
    dtype, setup_key, channel_size, byte_order, min_temp, max_temp = sig

    setup: str | list = list(setup_key) if isinstance(setup_key, tuple) else setup_key
    available, mode_channels = channel_setup_to_channels(
        setup, channel_size, byte_order, min_temp, max_temp
    )

    fixture_name = _fixture_name_for_sig(sig).replace("-", " ").title()

    category_map = {
        "dimmer": ["Dimmer"],
        "binary": ["Dimmer"],
        "color_temp": ["Color Changer"],
        "rgb": ["Color Changer"],
        "rgbw": ["Color Changer"],
        "rgbww": ["Color Changer"],
        "xy": ["Color Changer"],
        "fixed": ["Other"],
    }
    categories = category_map.get(dtype, ["Other"])

    fixture: dict[str, Any] = {
        "$schema": OFL_SCHEMA,
        "name": fixture_name,
        # The fixture registry indexes by shortName / name only -- never by filename --
        # and the generated config references fixtures by their slug, so the slug has to
        # be the shortName. run_migration() overwrites this with the de-duplicated key.
        "shortName": _fixture_name_for_sig(sig),
        "categories": categories,
        "comment": f"Auto-generated by migrate.py from artnet_led type '{dtype}'",
        "availableChannels": available,
        "modes": [
            {
                "name": "Default",
                "shortName": "default",
                "channels": mode_channels,
            }
        ],
    }

    return fixture


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------

def _correction_value(correction: str | None) -> str | None:
    if correction in (None, "linear"):
        return None
    return correction


def _build_universe_devices(universe_cfg: dict, fixture_key_map: dict) -> list[dict]:
    """Build the devices list for one universe."""
    devices = []
    universe_correction = universe_cfg.get("output_correction")

    for device in universe_cfg.get("devices", []):
        channel = device["channel"]
        name = device["name"]
        sig = device_fixture_signature(device)
        fixture_key = fixture_key_map[sig]

        device_entry: dict[str, Any] = {
            # Both formats are 1-based: the old `channel: 1` and the new
            # `start_address: 1` both mean the first slot of the universe.
            # DmxUniverse.send_universe_data() writes data[channel - 1], and the docs'
            # examples place a 10-channel fixture at 1 and the next one at 11.
            "start_address": channel,
            "fixture": fixture_key,
        }

        # Effective output correction: device-level overrides universe-level
        effective_correction = device.get("output_correction") or universe_correction
        corrval = _correction_value(effective_correction)
        if corrval:
            device_entry["output_correction"] = corrval

        # No entity_id_prefix: the device name alone already reproduces the old
        # integration's light.{slugify(name)}. friendly_name is deliberately NOT mapped
        # here -- it only ever set the display name, so using it would change entity_ids.

        devices.append({name: device_entry})

    return devices


def generate_dmx_config(
    entries: list[dict],
    fixture_key_map: dict,
    warnings: list[str],
) -> dict:
    """Build the full dmx: config dict from all old platform entries."""

    artnet_universes_map: dict[int, dict] = {}
    sacn_universes_map: dict[int, dict] = {}

    artnet_max_fps: int | None = None
    artnet_refresh: float | None = None
    sacn_refresh: float | None = None

    warned_transition = False
    warned_friendly = False

    for entry in entries:
        node_type = entry.get("node_type", "artnet-direct")
        max_fps = entry.get("max_fps", 25)
        refresh = entry.get("refresh_every", 120)

        if node_type == "kinet":
            warnings.append(
                f"SKIPPED: A '{node_type}' entry was found. KiNet is not supported "
                "in the new dmx integration and has been omitted."
            )
            continue

        if max_fps and max_fps != 25:
            artnet_max_fps = max_fps

        if node_type in ("artnet-direct", "artnet-controller"):
            if artnet_refresh is None:
                artnet_refresh = float(refresh)
                if refresh == 120:
                    warnings.append(
                        "NOTE: refresh_every was 120 s (old default). The new default is 0.8 s. "
                        "Your generated config preserves the old value (120 s). "
                        "Consider lowering it if you want faster re-transmission."
                    )
        elif node_type == "sacn":
            if sacn_refresh is None:
                sacn_refresh = float(refresh)
                if refresh == 120:
                    warnings.append(
                        "NOTE: refresh_every was 120 s (old default) for sACN. "
                        "The new default is 0.8 s. Your generated config preserves 120 s."
                    )

        for universe_nr, universe_cfg in entry.get("universes", {}).items():
            universe_correction = universe_cfg.get("output_correction")
            if universe_correction and universe_correction != "linear":
                warnings.append(
                    f"NOTE: Universe {universe_nr} had output_correction='{universe_correction}'. "
                    "Universe-level correction is not supported in the new format; "
                    "it has been applied to each device in that universe."
                )

            send_partial = universe_cfg.get("send_partial_universe", True)
            devices = _build_universe_devices(universe_cfg, fixture_key_map)

            if node_type in ("artnet-direct", "artnet-controller"):
                existing = artnet_universes_map.setdefault(universe_nr, {
                    "devices": [],
                    "send_partial": send_partial,
                    "manual_nodes": [],
                })
                existing["devices"].extend(devices)

                if node_type == "artnet-direct":
                    host = entry.get("host_override") or entry.get("host", "")
                    port = entry.get("port_override") or entry.get("port", 6454)

                    if entry.get("host_override"):
                        warnings.append(
                            f"NOTE: host_override ('{entry['host_override']}') was used "
                            f"in place of host ('{entry.get('host', '')}') for manual_nodes."
                        )

                    node_entry: dict[str, Any] = {"host": host}
                    if port != 6454:
                        node_entry["port"] = port
                    if node_entry not in existing["manual_nodes"]:
                        existing["manual_nodes"].append(node_entry)

            elif node_type == "sacn":
                if not send_partial:
                    warnings.append(
                        f"NOTE: sACN universe {universe_nr} had send_partial_universe=False. "
                        "sACN always transmits full universes in the new format."
                    )

                host_override = entry.get("host_override")
                unicast = None
                if host_override:
                    port = entry.get("port_override") or entry.get("port", 5568)
                    unicast = {"host": host_override, "port": port}

                existing_sacn = sacn_universes_map.setdefault(universe_nr, {
                    "devices": [],
                    "unicast_addresses": [],
                })
                existing_sacn["devices"].extend(devices)
                if unicast and unicast not in existing_sacn["unicast_addresses"]:
                    existing_sacn["unicast_addresses"].append(unicast)

        # Warn about per-device transition (once)
        if not warned_transition:
            for universe_cfg in entry.get("universes", {}).values():
                for device in universe_cfg.get("devices", []):
                    if device.get("transition", 0) != 0:
                        warnings.append(
                            f"NOTE: Device '{device.get('name')}' had "
                            f"transition={device['transition']}. "
                            "Per-device transition time is not supported in the new format; "
                            "use the global rate_limit setting instead."
                        )
                        warned_transition = True
                        break

        # Warn about friendly_name (once)
        if not warned_friendly:
            for universe_cfg in entry.get("universes", {}).values():
                for device in universe_cfg.get("devices", []):
                    if device.get("friendly_name"):
                        warnings.append(
                            "NOTE: friendly_name is not supported in the new format and has "
                            "been dropped. It only ever set the display name -- entity IDs "
                            "came from `name` and are preserved via entity_id_prefix -- so "
                            "automations keep working, but you may want to rename the "
                            "affected entities in the UI."
                        )
                        warned_friendly = True
                        break

    # Build artnet universes list
    artnet_universes: list[dict] = []
    for universe_nr, data in artnet_universes_map.items():
        universe_entry: dict[str, Any] = {"devices": data["devices"]}
        compat: dict[str, Any] = {}
        if not data["send_partial"]:
            compat["send_partial_universe"] = False
        if data["manual_nodes"]:
            compat["manual_nodes"] = data["manual_nodes"]
        if compat:
            universe_entry["compatibility"] = compat
        artnet_universes.append({universe_nr: universe_entry})

    # Build sACN universes list
    sacn_universes: list[dict] = []
    for universe_nr, data in sacn_universes_map.items():
        universe_entry = {"devices": data["devices"]}
        compat = {}
        if data["unicast_addresses"]:
            compat["unicast_addresses"] = data["unicast_addresses"]
        if compat:
            universe_entry["compatibility"] = compat
        sacn_universes.append({universe_nr: universe_entry})

    dmx: dict[str, Any] = {}

    if artnet_max_fps:
        dmx["animation"] = {"max_fps": artnet_max_fps}

    if artnet_universes:
        artnet_section: dict[str, Any] = {}
        if artnet_refresh is not None:
            artnet_section["refresh_every"] = artnet_refresh
        artnet_section["universes"] = artnet_universes
        dmx["artnet"] = artnet_section

    if sacn_universes:
        sacn_section: dict[str, Any] = {}
        if sacn_refresh is not None:
            sacn_section["refresh_every"] = sacn_refresh
        sacn_section["universes"] = sacn_universes
        dmx["sacn"] = sacn_section

    return {"dmx": dmx}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def to_plain_types(value: Any) -> Any:
    """Recursively convert a value to plain Python types.

    Home Assistant parses configuration.yaml with annotatedyaml, which returns
    str/dict/list *subclasses* that carry __config_file__ / __line__ metadata.
    PyYAML has no representer for those, so dumping them emits
    `!!python/object/new:annotatedyaml.objects.NodeStrClass` tags instead of
    plain scalars -- a file no safe YAML loader (including HA's own) can read.
    Old-config values flow straight into the generated config, so they have to
    be flattened before they are written out.
    """
    if isinstance(value, dict):
        return {to_plain_types(k): to_plain_types(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain_types(v) for v in value]
    if isinstance(value, bool):  # bool before int: bool is a subclass of int
        return bool(value)
    if isinstance(value, str):
        return str(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    return value


@dataclass
class MigrationResult:
    dmx_config: dict
    fixture_map: dict[tuple, dict]
    fixture_key_map: dict[tuple, str]
    warnings: list[str] = field(default_factory=list)


def extract_old_entries(config: dict) -> list[dict]:
    """Filter a full HA config dict for artnet_led / ha_artnet_led platform entries."""
    light_section = config.get("light", [])
    if isinstance(light_section, dict):
        light_section = [light_section]
    if not isinstance(light_section, list):
        return []
    return [
        e for e in light_section
        if isinstance(e, dict) and e.get("platform", "") in ("artnet_led", "ha_artnet_led")
    ]


def run_migration(entries: list[dict]) -> MigrationResult:
    """Full migration pipeline — pure, no I/O. Safe to call via async_add_executor_job."""
    warnings: list[str] = []
    all_sigs: dict[tuple, dict] = {}

    for entry in entries:
        for universe_cfg in entry.get("universes", {}).values():
            for device in universe_cfg.get("devices", []):
                sig = device_fixture_signature(device)
                if sig not in all_sigs:
                    if sig[2] == "32bit":
                        warnings.append(
                            f"NOTE: Device '{device.get('name')}' uses channel_size=32bit. "
                            "OFL supports at most 24bit (3 fine channel aliases). "
                            "The fixture has been generated with 3 fine aliases; "
                            "the 4th byte will be ignored."
                        )
                    if sig[0] == "color_temp":
                        setup = sig[1]
                        has_temp_channel = "t" in setup or "T" in setup
                        if not has_temp_channel:
                            min_k, max_k = sig[4], sig[5]
                            if min_k != "2000K" or max_k != "6500K":
                                warnings.append(
                                    f"NOTE: Device '{device.get('name')}' is color_temp with "
                                    f"min_temp={min_k}, max_temp={max_k} but no 't'/'T' channel "
                                    "in channel_setup. The kelvin range cannot be expressed in the "
                                    "OFL fixture format for CW/WW-only setups. The new integration "
                                    "will default to 2000K-6500K. "
                                    "See https://github.com/OpenLightingProject/open-fixture-library/issues/4922"
                                )
                    all_sigs[sig] = generate_fixture(sig)

    fixture_key_map: dict[tuple, str] = {}
    used_keys: set[str] = set()
    for sig in all_sigs:
        base_key = _fixture_name_for_sig(sig)
        key = base_key
        counter = 2
        while key in used_keys:
            key = f"{base_key}-{counter}"
            counter += 1
        used_keys.add(key)
        fixture_key_map[sig] = key
        # Keep shortName identical to the key the config and the filename use.
        all_sigs[sig]["shortName"] = key

    dmx_config = generate_dmx_config(entries, fixture_key_map, warnings)

    # Signature tuples stay as-is: they are only ever dict keys, never serialised.
    return MigrationResult(
        dmx_config=to_plain_types(dmx_config),
        fixture_map={sig: to_plain_types(fixture) for sig, fixture in all_sigs.items()},
        fixture_key_map=fixture_key_map,
        warnings=warnings,
    )
