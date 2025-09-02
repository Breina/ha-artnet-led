# Welcome to the beta of the platform refactor!

We're now compatible with the every fixture that can be defined through [Open Fixture Library](https://open-fixture-library.org/).
This means we now support moving heads, strobes, and much more. Since this standard is so expansive, I can use some help with testing this.

## How to use it?

Since the DOMAIN has been renamed from `artnet_led` to `dmx`, HACS might get angry, so for now it will require a manual installation by copying `custom_components/dmx` into your `custom_components` folder on HomeAssistant, then restarting.

For migrating your old fixtures into the new format, I've written up [a migration guide](migration.md).

Part of the beta is to test if my documentation suffices. So head over to [the index](index.md) and see if you can figure out how to use it.

## What's in the box?

* What was previous `node_type: artnet-controller` has now become the standard, with `artnet-direct` being moved to compatibility options.
* Rate limiting when sending DMX data from an external controller to HomeAssistant
* Discovered Art-Net nodes will create new entities
* Art-Net triggers will invoke HomeAssistant events

## What's excluded?

* Transitions: I'd love to support custom animations, but not yet sure how I would have you define them.
* RDM: This is a HUGE standard, won't make it to the full release either.

## Where to report feedback?

All feedback and ideas are greatly welcome!

[Create a GitHub issue](https://github.com/Breina/ha-artnet-led/issues/new) and label it with `platform-refactor`.

## Legal

Since now none of the original code remains, I'm able to upgrade our license to **GPL v3**.
This guarantees that this any derivatives of this work will always remain open source. :)