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

```yaml
dmx:
  fixtures:
    folder: fixtures

  artnet:
    max_fps: 43
    refresh_every: 1.2
    rate_limit: 0.5

    universes:
      - 1/2/0:
          devices:
            - Epic triple lights:
                start_address: 11
                fixture: CLHB300RGBW
                mode: 42ch

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
```

### Configuration Options

#### `dmx.fixtures`
- **`folder`** *(optional, default: `fixtures`)*  
  Directory containing fixture JSON files, relative to Home Assistant config directory (where your `configuration.yaml` is located)

#### `dmx.artnet`
- **`max_fps`** *(optional, default: `30`)*  
  Maximum frames per second for animations [0, 43]
- **`refresh_every`** *(optional, default: `0.8`)*  
  The interval in seconds in which universe data is retransmitted. This is useful when there are external controllers sending to the same universes. Set to `0` to disable this behavior.
- **`refresh_every`** *(optional, default: `0.5`)*  
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

#### Compatibility Options
- **`send_partial_universe`** *(optional, default: true)*  
  Art-Net supports updating only part of a universe and leaving the unchanged parts out of its packet.
  Some Art-Net nodes do not support partial universes, so it may help to disable this functionality.
- **`manual_nodes`** *(optional)*  
  Art-Net supports auto-discovery of Art-Net nodes, this works through broadcasting on the network.
  If nodes are not discovered automatically, they may be added manually,
  so that updates for this universe are always sent to this address as well. 
  - **`host`** *(mandatory)*: IP address
  - **`port`** *(optional, default: `6454`)*: Art-Net port

## Step 3: Restart and Verify

1. **Restart Home Assistant** to load the new configuration
2. Check that your fixtures appear as entities in Home Assistant

## Troubleshooting

If fixtures don't appear after restart:

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