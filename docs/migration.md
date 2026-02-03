# How to migrate from the old fixture definitions?

All your current fixtures are now still supported! Here's the process to get your integration migrated.

## Installing

Our integration name changed from `artnet_led` to `dmx`. HACS doesn't allow this, so we are unable to upgrade this in-place. Therefore a manual release is needed for the beta.

Under [the release](https://github.com/Breina/ha-artnet-led/releases/tag/v1.0.0-BETA.8) download the [source code](https://github.com/Breina/ha-artnet-led/archive/refs/tags/v1.0.0-BETA.8.zip).

In this ZIP, navigate to `custom_components/dmx` and copy this `dmx` folder into your Home Assistant's `custom_components` folder. 

## Find your fixture format

Most of the previously supported fixtures already have a [generic fixture variant](https://open-fixture-library.org/search?q=generic) for you to download.

Download as: **Open Fixture Library JSON**

Examples:

* [Single dimmer](https://open-fixture-library.org/generic/desk-channel.ofl)
* [CW/WW](https://open-fixture-library.org/generic/cw-ww-fader.ofl)
* [Dimmer/color temperature](https://open-fixture-library.org/generic/color-temperature-fader.ofl)
* [RGB](https://open-fixture-library.org/generic/rgb-fader.ofl)
* [Dimmer/RGB](https://open-fixture-library.org/generic/drgb-fader.ofl)
* [RGBWW](https://open-fixture-library.org/generic/rgbww-fader.ofl)

This downloads a ZIP, inside this ZIP **ignore** the `manufacturers.json` and copy the JSON file of fixture itself into your HomeAssistants `config/fixtures` folder, which you will need to create.
The `config` folder is the one that houses your `configuration.yaml`.

This fixture format is extremely flexible and contains templating, channel switching, matrixes, and many other crazy things, and we're compatible with **all** of it. :)

You can go ahead and [use the editor](https://open-fixture-library.org/fixture-editor) or [write a JSON by hand](https://github.com/OpenLightingProject/open-fixture-library/blob/master/docs/fixture-format.md#fixture).

Note down the `shortName` of your fixtures, or `name` if it has no `shortName`, we will use these in the next step.

## Adding the fixtures to your house

Now that you have all the types of lights configured, it's time to add them. This step is explained in detail in [Configuration](config.md).

## Aftercare

If the new light fixtures now work, you may remove the old `artnet_led` folder and remove the old entities from your system.

When the 1.0.0 releases, this integration will be submitted for HACS default repositories, so manual installation won't be needed any more.