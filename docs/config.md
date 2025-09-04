# Configuration

## Step 1: Download Fixture Definitions

Before configuring the integration, you need fixture definition files from the Open Fixture Library.

1. Visit [open-fixture-library.org](https://open-fixture-library.org/)
2. Search for your specific fixture model
3. For generic fixtures (RGB strips, CW/WW faders, etc.), search for [`generic`](https://open-fixture-library.org/search?q=generic)
4. Download the fixture as **"Open Fixture Library JSON"** format
5. Place the downloaded `.json` files in your `config/fixtures/` directory

## Step 2: YAML Configuration

Add the DMX configuration to your `configuration.yaml`:

### Minimum Configuration

This includes Art-Net and sACN, remove what you don't need.

```yaml
dmx:
  artnet:
    universes:
      - 1:
          devices:
            - Epic triple lights:
                start_address: 11
                fixture: CLHB300RGBW
  sacn:
    universes:
      - 1:
          devices:
            - RGB Strip:
                start_address: 1
                fixture: generic-rgb
```

### Maximum Configuration

```yaml
dmx:
  fixtures:
    folder: fixtures

  animation:
    max_fps: 43

  artnet:
    refresh_every: 1.2
    rate_limit: 0.5

    universes:
      - 1/2/0:
          devices:
            - Epic triple lights:
                start_address: 11
                fixture: CLHB300RGBW
                mode: 42ch
                entity_id_prefix: my_first_entity_id

          compatibility:
            send_partial_universe: False
            manual_nodes:
              - { host: 192.168.1.11, port: 6454 }
              - { host: 192.168.1.12 }

      - 3: # minimal required config
          devices:
            - DJ led:
                start_address: 0
                fixture: DJ Scan LED

  sacn:
    source_name: "Home Assistant sACN"
    priority: 100
    multicast_ttl: 64
    enable_preview_data: false

    universes:
      - 1:
          devices:
            - RGB Strip:
                start_address: 1
                fixture: generic-rgb
                mode: 3ch

          compatibility:
            unicast_addresses:
              - { host: 192.168.1.20, port: 5568 }
              - { host: 192.168.1.21 }

      - 2:
          devices:
            - Moving Head:
                start_address: 10
                fixture: moving-head-spot
                mode: extended
```

### Configuration Options

#### `dmx.fixtures`
- **`folder`** *(optional, default: `fixtures`)*  
  Directory containing fixture JSON files, relative to Home Assistant config directory (where your `configuration.yaml` is located)

#### `dmx.animation`
- **`max_fps`** *(optional, default: `30`)*  
  Maximum frames per second for animations [1, 43], used for transitions.

#### `dmx.artnet`
- **`refresh_every`** *(optional, default: `0.8`)*  
  The interval in seconds in which universe data is retransmitted. This is useful when there are external controllers sending to the same universes. Set to `0` to disable this behavior.
- **`rate_limit`** *(optional, default: `0.5`)*  
  The rate limit in seconds between each entity update when received from an external controller. Increase this value if HomeAssistant slows down too much when receiving updates.

#### `dmx.artnet.universes`
Universe definitions. Each universe can be specified as:

- **Full format**: `Net/Sub-net/Universe` (e.g., `1/2/0`)
- **Short format**: `Universe` only (e.g., `3` - Net and Sub-net default to 0)

#### Universe Configuration
- **`devices`** *(mandatory)*  
  List of fixtures in this universe

#### Device Configuration
- **`start_address`** *(mandatory)*  
  DMX start address [0-511]
- **`fixture`** *(mandatory)*  
  Matches the `shortName` of the fixture JSON, or `name` if no `shortName` is defined.
- **`mode`** *(optional)*  
  Matches the `name` of the desired mode in the `modes` section of the fixture JSON.
  If there is only one mode, this option config option is optional.
- **`entity_id_prefix`** *(optional)*  
  Allows one to configure the entity ID of the created entities, this will then also be used for unique_id instead of universe/channel.
  Thus, when this option is used, this fixture can be moved freely without creating duplicate entities.
- - Number entities: `number.{entity_id_prefix}_{channel_name}` or `nubmer.{entity_id_prefix}_{channel_name}_{capability_name}`
- - Select entities: `select.{entity_id_prefix}_{channel_name}`
- - Light entities: `light.{entity_id_prefix}`
  

#### Compatibility Options
- **`send_partial_universe`** *(optional, default: true)*  
  Art-Net supports updating only part of a universe and leaving the unchanged parts out of its packet.
  Some Art-Net nodes do not support partial universes, so it may help to disable this functionality.
- **`manual_nodes`** *(optional)*  
  Art-Net supports auto-discovery of Art-Net nodes, this works through broadcasting on the network.
  If nodes are not discovered automatically, they may be added manually,
  so that updates for this universe are always sent to this address as well. 
- - **`host`** *(mandatory)*: IP address
- - **`port`** *(optional, default: `6454`)*: Art-Net port

#### `dmx.sacn`
- **`source_name`** *(optional, default: `HA sACN Controller`)*  
  Source name transmitted in sACN packets (max 63 characters)
- **`priority`** *(optional, default: `100`)*  
  sACN data priority [0-200]. Higher values take precedence over lower priority sources.
- **`multicast_ttl`** *(optional, default: `64`)*  
  Time-to-live for multicast packets [1-255]
- **`enable_preview_data`** *(optional, default: `false`)*  
  Mark transmitted data as preview data (non-live)

#### `dmx.sacn.universes`
Universe definitions for sACN. Each universe number [1-63999] maps to multicast address `239.255.X.Y` where X.Y represents the universe number.

#### sACN Universe Configuration
- **`devices`** *(mandatory)*  
  List of fixtures in this universe (same format as Art-Net)

#### sACN Compatibility Options
- **`unicast_addresses`** *(optional)*  
  Send sACN data to specific IP addresses via unicast in addition to multicast.
  Useful for devices that don't support multicast or are on different network segments.
- - **`host`** *(mandatory)*: IP address
- - **`port`** *(optional, default: `5568`)*: sACN port

## Step 3: Restart and Verify

1. **Restart Home Assistant** to load the new configuration
2. Check that your fixtures appear as entities in Home Assistant

## Troubleshooting

### Check Logs
1. Go to **Settings** → **System** → **Logs**
2. Filter logs by typing `dmx` in the search box
3. Look for error messages related to fixture loading or configuration

### Enable Debug Logging
Add this to your `configuration.yaml` for detailed debugging:

```yaml
logger:
  logs:
    custom_components.dmx: debug
```

**Important**: Restart Home Assistant after adding debug logging.

---

*Art-Net™ Designed by and Copyright Artistic Licence*