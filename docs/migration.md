# How to migrate from the old `artnet_led` integration?

Your old configuration converts automatically, and your lights keep their entity IDs.

## Installing

Download the [source code](https://github.com/Breina/ha-artnet-led/archive/refs/tags/v1.0.0-BETA.13.zip) of [the latest release](https://github.com/Breina/ha-artnet-led/releases/tag/v1.0.0-BETA.13), and copy its `custom_components/dmx` folder into your Home Assistant's `custom_components` folder.

Once 1.0.0 is released, you'll be able to install it through HACS instead.

## Migrating

1. Add `dmx: {}` to your `configuration.yaml` and restart.
2. Under **Settings → System → Repairs**, fix **Old artnet_led configuration detected**. This writes your fixtures to `fixtures/` and your new configuration to `dmx_migration.yaml`.
3. Remove the old `light: - platform: artnet_led` block, keep `dmx: {}`, and restart.
4. Under **Settings → Devices & services → Entities**, delete the old lights. Their areas and icons don't carry over.
    * If it says 0 can be deleted, Home Assistant is still starting: wait a minute and refresh.
    * Old lights you had disabled are hidden there and can't be deleted. Remove them from `dmx_migration.yaml`, or they come back with a `_2` suffix.
5. Replace `dmx: {}` with the contents of `dmx_migration.yaml` and restart.
6. Delete the `custom_components/artnet_led` folder and `dmx_migration.yaml`.

Do these in order: if the new lights appear before the old ones are deleted, they get a `_2` suffix.

## Converting fixtures by hand

Rather use real fixture definitions than the generated ones? Most of the previously supported fixtures already have a [generic fixture variant](https://open-fixture-library.org/search?q=generic) for you to download.

Download as: **Open Fixture Library JSON**

Examples:

* [Single dimmer](https://open-fixture-library.org/generic/desk-channel.ofl)
* [CW/WW](https://open-fixture-library.org/generic/cw-ww-fader.ofl)
* [Dimmer/color temperature](https://open-fixture-library.org/generic/color-temperature-fader.ofl)
* [RGB](https://open-fixture-library.org/generic/rgb-fader.ofl)
* [Dimmer/RGB](https://open-fixture-library.org/generic/drgb-fader.ofl)
* [RGBWW](https://open-fixture-library.org/generic/rgbww-fader.ofl)

This downloads a ZIP, inside this ZIP **ignore** the `manufacturers.json` and copy the JSON file of fixture itself into your HomeAssistants `config/fixtures` folder, which you will need to create.

This fixture format is extremely flexible and contains templating, channel switching, matrixes, and many other crazy things, and we're compatible with **all** of it. :)

You can go ahead and [use the editor](https://open-fixture-library.org/fixture-editor) or [write a JSON by hand](https://github.com/OpenLightingProject/open-fixture-library/blob/master/docs/fixture-format.md#fixture).

Note down the `shortName` of your fixtures, or `name` if it has no `shortName`, then add them to your house as explained in [Configuration](config.md).
