# External Art-Net Controller Communication

This documentation covers how your Home Assistant ArtNet integration communicates with external ArtNet controllers.

## Overview

The ArtNet integration in Home Assistant sets up a software-based ArtNet controller that can be discovered by other ArtNet controllers.

The OEM code of integration is `0x2BE9`, which is [registered with Art-Net](https://art-net.org.uk/oem-code-zone/). 

## Auto-Discovery

ArtNet controllers are typically auto-discovered through ArtNet's built-in discovery mechanism:

1. When your integration receives an **ArtPoll** request from external controllers, it evaluates whether to respond.
2. If the targeted mode on the external controller is disabled, the integration will always respond.
3. Otherwise, your controller checks if its universes match what the external controller is looking for and only responds if an overlap is found.
4. If no matching universes exist, the request is ignored (debug log: `Received ArtPoll, but ignoring it since none of its universes overlap with our universes.`)

## Receiving Data from External Controllers

### DMX Data

External controllers can send DMX data to universes configured in your Home Assistant controller. When received:

- The integration updates the corresponding entity values
- Entity updates are limited to 2 updates per second to not flood HomeAssistant with updates.

### ArtTrigger Events

External controllers can send **ArtTrigger** messages which are converted to Home Assistant events:

- Event type: `artnet_trigger`
- Payload must be a null-terminated string (`UTF-8` preferred, maximum 512 bytes)
- The event contains metadata about the trigger source

Example event structure in Home Assistant:

```yaml
event_type: artnet_trigger
data:
  oem: 11241 # Decimal representation of OEM code
  key: 1
  sub_key: 4
  payload: Test 123 This is a system test
origin: LOCAL
time_fired: "2025-06-09T12:34:44.691947+00:00"
context:
  id: 01JXAAZ7AKF1BE86A78RWME2KY
  parent_id: null
  user_id: null
```

## Subscriber Mechanism

The integration implements a subscriber mechanism to manage communication with other ArtNet nodes, ensuring they receive timely updates when changes occur in Home Assistant.

### How Subscribers Work

When an external controller sends an ArtPoll request with the `notify_on_change` flag set to true, it is automatically added to a subscriber pool:

These subscribers receive automatic updates whenever relevant changes occur in your controller, without needing to continuously poll for changes.

### When Updates Are Sent to Subscribers

Updates are sent to all subscribers in the following scenarios:

1. **Configuration Changes**: When universes or ports are added or removed from your controller
2. **Status Changes**: When the status of a port changes (e.g., data transmission begins or ends)
3. **Input Activity**: When data is received on an input port, and the flag changes

### Removing Subscribers

A background task periodically checks for nodes that haven't been seen in 10 seconds.
When a stale node is found, they are removed from the subscriber pool.

### Diagnostic Messages

To aid in troubleshooting, the integration logs activity when subscribers are added or removed:

- When a node is added: `Discovered new node at X.X.X.X@Y with Z/W/[universe list]`
- When a node hasn't been seen for a while: `Haven't seen node X.X.X.X#Y for Z seconds; removing it.`

---

*Art-Net™ Designed by and Copyright Artistic Licence*