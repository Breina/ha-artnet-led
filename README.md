# Home Assistant component for Art-Net LED (DMX)

Updated integration Supporting the new color mode in Home Assistant. leveraged heavily form [spacemanspiff2007](https://github.com/spacemanspiff2007/home-assistant-artnet) and [jnimmo](https://github.com/jnimmo/hass-dmx)
Now supports 16 bit resolution (also supports 24 bit and 32 bit but I don't know of a DMX controller that would use it)
Use Brightness and RGB value separately to give more resolution to brightness to be able to make use of 16 bit resolution

The DMX integration for Home Assistant allows you to send DMX values to an [Art-Net](http://www.art-net.org.uk) capable DMX interface. This component is a one way integration which sends [Art-Net](https://en.wikipedia.org/wiki/Art-Net) UDP packets to the DMX interface. This integration uses [pyartnet](https://github.com/spacemanspiff2007/PyArtNet) libraries and requires at least Python version 3.8.

## Prerequisites

* [Home Assistant (hass)](https://www.home-assistant.io/) >= 2021.5 for Color_Mode.
* [pyartnet](https://github.com/spacemanspiff2007/PyArtNet) == 0.8.3 will load automatically.

## Installation

This can be easily installed with the [Home Assistant Community Store (HACS)](https://github.com/custom-components/hacs) using the repository: *corb3000/ha-artnet-led*

Alternatively, manual installation by downloading the [custom_components/artnet_led](https://github.com/corb3000/ha-artnet-led) directory to the *custom_components/artnet_led* directory on your Home Assistant instance (generally */config/custom_components/artnet_led*).

## Configuration

hass-dmx is a community supported Home Assistant integration, if you have any questions you can discuss with the [Home Assistant DMX Community](https://community.home-assistant.io/t/dmx-lighting/2248).

artnet-led lighting is configured in the `configuration.yaml` file under the *light* domain.


Artnet-led lighting configuration:

```yaml
light:
- platform: artnet_led
  host: IP                              # IP of Art-Net Node
  max_fps: 25                           # Max 40 per second
  refresh_every: 0                      # Resend values if no fades are running every x seconds, 0 disables automatic refresh
  universes:                            # Support for multiple universes
    0:                                  # Nr of Universe (see configuration of your Art-Net Node)
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
          transition: 1
          channel_size: 16bit
          output_correction: quadratic
        - channel: 125
          type: "color_temp"
          name: "my_color_temp_lamp"
        - channel: 41
          type: rgbww
          name: my_rgbww_lamp
          transition: 10
```

Configuration variables:
- **host** (*Required*): Art-Net/DMX gateway address
- **port** (*Optional; default=6454*): Art-Net/DMX gateway port
- **max-fps** (*Optional; default=25*): frame rate for fade update (1 to 40 FPS)
- **refresh_every** (*Optional; default=120*): Seconds to resend values if no fades are running, 0 disables.
- **universe** (*Required*): Art-Net universe for following DMX channels.
  - **output_correction** (*Optional; default=linear*): applied to whole universe
    - **'linear'**
    - **'quadratic'** (see Graph)
    - **'cubic'** (see Graph)
    - **'quadruple'** (see Graph)

Device configuration variables:
  - **channel** (*Required*): The DMX channel for the light (1-512)
  - **name** (*Required*): Friendly name for the light 
  - **type** (*Optional; default=dimmer*): 
    - **'dimmer'** (single channel)
    - **'rgb'** (red, green, blue)
    - **'rgbw'** (red, green, blue, white)
    - **'rgbww'** (red, green, blue, cool-white, warm-white)
    - **'color_temp'** (cool-white, warm-white)
  - **output_correction** (*Optional; default=linear*): applied to each channel, overrides universe setting.
    - **'linear'**
    - **'quadratic'** (see Graph)
    - **'cubic'** (see Graph)
    - **'quadruple'** (see Graph)
  - **channel_size** (*Optional; default= 8bit): width of the channel sent to DMX device.
    - **'8bit'** (255 steps)
    - **'16bit'** (65k steps)
    - **'24bit'** (too many steps)
    - **'32bit'** (dont ask steps)

#### Supported features

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

- Should work with any Art-Net enabled DMX interface.
- Artnet interface tested on DMX King eDMX4
- 16 bit DMX support tested on 32 Channel 96A RGBW DMX 512 LED Decoder Controller DMX Dimmer DC5-24V RGBW RGB LED Light 8 Bit/16 Bit.
[Learn more: ](https://www.amazon.com/dp/B075FHJM35/ref=cm_sw_em_r_mt_dp_0098GH3MGCYHCYKXR5AQ?_encoding=UTF8&psc=1) 


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
