[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

# Home Assistant component for Art-Net LED (DMX)

Updated integration Supporting the new color mode in Home Assistant. leveraged heavily form [spacemanspiff2007](https://github.com/spacemanspiff2007/home-assistant-artnet) and [jnimmo](https://github.com/jnimmo/hass-dmx)
Now supports 16 bit resolution (also supports 24 bit and 32 bit but I don't know of a DMX controller that would use it)
Use Brightness and RGB value separately to give more resolution to brightness to be able to make use of 16 bit resolution

The DMX integration for Home Assistant allows you to send DMX values to an [Art-Net](http://www.art-net.org.uk) capable DMX interface. This component is a one way integration which sends [Art-Net](https://en.wikipedia.org/wiki/Art-Net) UDP packets to the DMX interface. This integration uses [pyartnet](https://github.com/spacemanspiff2007/PyArtNet) libraries and requires at least Python version 3.8.

## Installation

> **Note**
> 
> This integration requires [HACS](https://hacs.xyz/docs/setup/download/) to be installed

> **Warning**
> 
> When migrating from jnimmo or corb3000's integration: 
> 1. First remove the integration
> 2. Comment or remove the YAML config
> 3. Restart
> 4. Delete the light entities
> 5. Remove all other _Custom_repositories_ that are also named `ha-artnet-led`
> 6. Install this integration and re-introduce the config (also change change `custom_white` to `color_temp`)

1. Open HACS
2. Open the options in the top right and select _Custom repositories_
3. Enter this repository's URL (`https://github.com/Breina/ha-artnet-led`) under the Category _Integration_.
4. Press _Add_
5. _+ EXPLORE & DOWNLOAD REPOSITORIES_
6. Find _Art-net LED Lighting for DMX_ in this list
7. _DOWNLOAD THIS REPOSITORY WITH HACS_
8. _DOWNLOAD_
9. Restart Home Assistant (_Settings_ > _System_ >  _RESTART_)

## Configuration

hass-dmx is a community supported Home Assistant integration, if you have any questions you can discuss with the [Home Assistant DMX Community](https://community.home-assistant.io/t/dmx-lighting/2248).

artnet-led lighting is configured in the `configuration.yaml` file under the *light* domain.


Example:

```yaml
light:
- platform: artnet_led
  host: IP                              # IP of Art-Net Node
  max_fps: 25                           # Max 40 per second
  refresh_every: 0                      # Resend values if no fades are running every x seconds, 0 disables automatic refresh
  node_type: artnet-direct              # Which protocol to use
  universes:                            # Support for multiple universes
    0:                                  # Nr of Universe (see configuration of your Art-Net Node)
      send_partial_universe: True       # Only send the universe which contains data
      output_correction: quadratic      # optional: output correction for the whole universe, will be used as default if nothing is set for the channel
      devices:
        # Dimmer
        - channel: 1                    # first channel of dmx dimmer
          name: my_dimmer               # name
          type: dimmer                  # type
          transition: 1                 # default duration of fades in sec. Will be overridden by Transition sent from HA
          output_correction: quadratic  # optional: quadratic, cubic or quadruple. Apply different dimming curves to the output. Default is None which means linear dimming
          channel_size: 16bit           # width of the channel sent to DMX device, default "8bit", "16bit", "24bit" and "32bit" available.
        - channel: 3
          name: my_rgb_lamp
          type: rgb
          transition: 1
          channel_size: 16bit
          output_correction: quadratic
          channel_setup: rbgw           # Auto-calculated white channel
        - channel: 125
          type: color_temp
          name: "my_color_temp_lamp"
          min_temp: 2500K
          max_temp: 6500K
          channel_setup: ch
        - channel: 41
          type: rgbww
          name: my_rgbww_lamp
          transition: 10
        - channel: 50
          name: sp4led_1_dimmer
          type: fixed
          channel_setup:
            - 255
```

### Configuration variables
- **host** (*Required*): Art-Net/DMX gateway address
- **port** (*Optional; default=6454*): Art-Net/DMX gateway port
- **max-fps** (*Optional; default=25*): frame rate for fade update (1 to 40 FPS)
- **refresh_every** (*Optional; default=120*): Seconds to resend values if no fades are running, 0 disables.
- **node_type** (*Optional; default=artnet-direct*): the protocol to use
  - **'artnet-direct'**: Directly sends DMX packets to a single node's IP.
  - **'artnet-controller'**: Auto-discovers ArtNet nodes and other controllers, can be picked up by other controllers. Will allow Home Assistant lights to be updated through DMX input.
  - **'sacn'**: The E1.31 sACN protocol, directly sending to a node's IP.
  - **'kinet'**: The KiNET, directly sending to a node's IP.
- **universe** (*Required*): Art-Net universe for following DMX channels.
  - **send_partial_universe** (*Optional; default=True*): Some controllers only accept full DMX frames. Set to `False` 
    to always send the full 512 channels to every universe.
  - **output_correction** (*Optional; default=linear*): applied to whole universe
    - **'linear'**
    - **'quadratic'** (see Graph)
    - **'cubic'** (see Graph)
    - **'quadruple'** (see Graph)

### Device configuration variables
  - **channel** (*Required*): The DMX channel for the light (1-512)
  - **name** (*Required*): Friendly name for the light 
  - **type** (*Optional; default=dimmer*): 
    - **'fixed'** (fixed single channel)
    - **'binary'** (single channel)
    - **'dimmer'** (single channel)
    - **'rgb'** (red, green, blue)
    - **'rgbw'** (red, green, blue, white)
    - **'rgbww'** (red, green, blue, cool-white, warm-white)
    - **'color_temp'** (cool-white, warm-white)
  - **transition** (*Optional; default=0*): Duration in seconds of the fading animation
  - **output_correction** (*Optional; default=linear*): applied to each channel, overrides universe setting.
    - **'linear'**
    - **'quadratic'** (see Graph)
    - **'cubic'** (see Graph)
    - **'quadruple'** (see Graph)
  - **channel_size** (*Optional; default= 8bit*): width of the channel sent to DMX device.
    - **'8bit'** (255 steps)
    - **'16bit'** (65k steps)
    - **'24bit'** (too many steps)
    - **'32bit'** (don't ask steps)
  - **byte_order** (*Optional; default=big*): For multi-byte channels, the bytes can be little-endian or big-endian. 
  - **min_temp** (Optional; default=2700K): Only applies for types 'color_temp' and 'rgbww'
  - **max_temp** (Optional; default=6500K): Only applies for types 'color_temp' and 'rgbww'
  - **channel_setup** (Optional; see [channel_setup](#channel_setup))

### channel_setup

A string or list to customize the channel layout of your light.
If a list is provided, fixed numeric values may be included.

#### Examples

```yaml
channel_setup: Wrgb
```
_White unscaled, red, green, blue_

```yaml
channel_setup:
  - W
  - r
  - g
  - b 
```
_Same as above_

```yaml
channel_setup:
  - W
  - r
  - 128
  - b 
```
_Staticly sets the green channel on 50% brightness_



#### Definition

- `d` = dimmer (brightness 0 to 255)
- `c` = cool white value, scaled for brightness
- `C` = cool white value, unscaled
- `h` = warm white value, scaled for brightness
- `H` = warm white value, unscaled
- `t` = temperature (0 = warm, 255 = cold)
- `T` = temperature (255 = warm, 0 = cold)
- `r` = red, scaled for brightness
- `R` = red, unscaled
- `g` = green, scaled for brightness
- `G` = green unscaled
- `b` = blue, scaled for brightness
- `B` = blue, unscaled
- `w` = white, scaled for brightness
- `W` = white, unscaled
- [`0`, `255`] = static value between the range [0, 255] 


#### Compatibility

| Type       |     |     |     |     |     |     |     |     |     |     |     |     |     |       |       |           | Default value |
|------------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-------|-------|-----------|---------------|
| fixed      |     |     |     |     |     |     |     |     |     |     |     |     |     |       |       | `[0,255]` | `0`           |
| binary     |     |     |     |     |     |     |     |     |     |     |     |     |     |       |       | `[0,255]` | `0`           |
| dimmer     |     |     |     |     |     |     |     |     |     |     |     |     |     |       |       | `[0,255]` | `0`           |
| color_temp | `d` | `c` | `C` | `h` | `H` | `t` | `T` |     |     |     |     |     |     |       |       | `[0,255]` | `ch`          |
| rgb        | `d` |     |     |     |     |     |     | `r` | `R` | `g` | `G` | `b` | `B` | `w`\* | `W`\* | `[0,255]` | `rgb`         |
| rgbw       | `d` |     |     |     |     |     |     | `r` | `R` | `g` | `G` | `b` | `B` | `w`   | `W`   | `[0,255]` | `rgbw`        |
| rgbww      | `d` | `c` | `C` | `h` | `H` | `t` | `T` | `r` | `R` | `g` | `G` | `b` | `B` |       |       | `[0,255]` | `rgbch`       |

\* In the case of a white channel being used in an RGB light fixture, the white channel is automatically calculated.


## Supported features

- Color-Mode. 
    This allows full independent control over: RGB setting, RGB brightness, Cool White brightness and Warm white brightness. with a separate over all brightness control. This allows you to sent the color and white levels to any value independently and then adjust the brightness of the whole light without affecting the color of the light.
- 16 bit DMX output.
    taking advantage of the separate brightness settings and the overall brightness allows lights to be dimmed to very low levels and still have a smooth fade due to the 65K steps you get from 16 bit
- Transition time can be specified through services to fade to a color (for RGB fixtures) or value. This currently is set to run at 25 frames per second. 
- Brightness: Once a channel is turned on brightness can be controlled through the Home Assistant interface.
- Color temperature: For dual channel warm white/cool white fixtures this tunes the white temperature.

### Output correction

- The graph shows different output depending on the output correction.

- Quadratic or cubic results in much smoother and more pleasant fades when using LED Strips.
The graph shows different output depending on the output correction.

From left to right:
linear (default when nothing is set), quadratic, cubic then quadruple
<img src='curves.svg'>

#### Limitations

- LEDS must be in same order as shown in channel

- Notes DMX king eDMX4 Pro does not seem to work if you have send less than 16 channels. Work around just add a dummy light at channel 16 or higher

#### Future improvements

- Lights are assigned a unique ID generated from the IP addreess, Port, Universe and Channel.


#### Supported hardware

- Should work with any Art-Net, KiNet or e1.31 sACN enabled DMX interface.
- Artnet interface tested on DMX King eDMX4 and ENTTEC DIN Ethergate 2.
- e1.31 sACN interface tested on esPixelStick and Falcon F16v2


## See Also

* [Art-Net Wikipedia](https://en.wikipedia.org/wiki/Art-Net)
* [Art-Net](https://art-net.org.uk/)
* [Community support for Home Assistant DMX](https://community.home-assistant.io/t/dmx-lighting/2248)

**Art-Net™ Designed by and Copyright Artistic Licence Holdings Ltd**


To enable debug logging for this component:

```yaml
logger:
  logs:
    custom_components.artnet_led: debug
```
# Legal

Art-Net™ Designed by and Copyright Artistic Licence
