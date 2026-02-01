# External sACN Controller Communication

This documentation covers how your Home Assistant sACN integration receives and processes data from external sACN controllers and lighting consoles.

## Overview

The sACN integration in Home Assistant implements a professional ANSI E1.31-2016 compliant sACN receiver. When configured, Home Assistant can receive sACN (Streaming ACN) data from external lighting controllers, professional consoles, and other sACN sources on your network.

Unlike Art-Net which uses broadcast communication, sACN uses **IP multicast** for efficient network distribution, allowing multiple controllers to coexist with automatic priority-based switching.

## Receiving Data from External sACN Sources

### Automatic Controller Discovery

Unlike Art-Net's polling mechanism, sACN uses a **priority-based system** for controller coordination:

1. **Multiple Sources**: Multiple sACN controllers can send data to the same universe
2. **Priority Switching**: Higher priority sources (0-200, higher wins) automatically take control
3. **Automatic Failover**: When a higher-priority source stops transmitting, receivers fall back to the next highest priority
4. **Seamless Switching**: No manual intervention required for controller changes

### DMX Data Reception

When Home Assistant receives sACN data from external controllers:

- **Entity Updates**: The integration updates corresponding entity values in real-time
- **Rate Limiting**: Updates are limited to prevent flooding Home Assistant with rapid changes
- **Priority Handling**: Higher-priority sources override lower-priority ones automatically
- **Stream Monitoring**: Integration tracks active streams and handles timeouts (2.5 seconds)

### Priority System in Action

**Example Setup:**
- **Main Lighting Console**: Priority 100 (normal operation)
- **Home Assistant**: Priority 90 (backup/automated scenes)
- **Emergency Override**: Priority 200 (safety/manual takeover)

When the main console is active, it controls all fixtures. If it goes offline, Home Assistant automatically takes control. Emergency override always wins regardless of other sources.

## Network Requirements for Receiving sACN

### Multicast Networking

sACN uses IP multicast addresses for efficient data distribution:

- **Universe 1**: `239.255.0.1:5568`
- **Universe 2**: `239.255.0.2:5568`
- **Universe N**: `239.255.((N-1) >> 8).((N-1) & 0xFF):5568`

### Network Infrastructure Requirements

!!! warning "Network Configuration Critical"
    Your network infrastructure must support **IP multicast** for sACN to work properly. Many home routers and managed switches disable multicast by default.

**Essential Network Settings:**

1. **IGMP Snooping** - Enable on managed switches to prevent multicast flooding
2. **Multicast routing** - Ensure routers forward multicast traffic between VLANs  
3. **Firewall rules** - Allow UDP traffic on port 5568 and multicast addresses
4. **WiFi multicast** - Enable multicast forwarding on wireless networks (often disabled for power saving)

### Testing Multicast Reception

**Test from Home Assistant host machine:**
```bash
# Test multicast reception (run on HA host)
socat UDP4-RECV:5568,ip-add-membership=239.255.0.1:0.0.0.0 -
```

**Test from lighting console/controller:**
```bash
# Send test data to Home Assistant (run on lighting console)
echo "Test sACN data" | socat - UDP4-DATAGRAM:239.255.0.1:5568
```

**Test from network switch (if manageable):**
```bash
# Check multicast group membership (run on managed switch CLI)
show ip igmp groups
show multicast route 239.255.0.1
```

If multicast fails, configure **unicast addresses** for direct communication.

### Special Considerations

If you have two or more Network Interfaces attached to your Home Assistant host, you will want to specify the specific network that the integration will bind to. Otherwise, the sACN universe to the primary interface as chosen by the operating system.

```yaml
dmx:
  sacn:
    interface_ip: "10.101.97.101"
```

### Unicast Reception

For networks that don't support multicast, configure external controllers to send unicast directly to Home Assistant:

**Home Assistant Configuration:**
```yaml
dmx:
  sacn:
    universes:
      - 1:
          devices:
            - My Fixture: ...
          # No unicast_addresses needed for receiving
```

**External Controller Setup:**
- Configure lighting console to send unicast sACN to Home Assistant's IP address
- Use port 5568 (standard sACN port)
- Set appropriate priority (lower than HA's priority to let HA control, higher to override)

## Understanding sACN Data Flow

### How External Data Reaches Home Assistant

1. **External Controller Transmission**:
   - Lighting console sends sACN data to multicast address `239.255.X.Y:5568`
   - Or sends unicast directly to Home Assistant IP address

2. **Network Delivery**:
   - Managed switches use IGMP snooping to deliver multicast efficiently
   - Only devices subscribed to the multicast group receive the data

3. **Home Assistant Reception**:
   - Integration joins appropriate multicast groups for configured universes
   - Processes incoming sACN packets according to ANSI E1.31-2016 specification
   - Updates entity values based on received DMX channel data

### Priority System

sACN's priority system (0-200, higher wins) enables professional controller coordination:

```yaml
dmx:
  sacn:
    priority: 90  # Lower than external console, higher than backup systems
```

**Typical Priority Hierarchy:**

- **Manual Override Console**: 200 (always wins)
- **Main Lighting Console**: 100 (normal operation)
- **Home Assistant**: 90 (backup/automated control)
- **Backup Systems**: 80 (last resort)

### Universe Synchronization

For complex lighting effects requiring perfect timing, sACN supports universe synchronization:

```yaml
dmx:
  sacn:
    sync_address: 7000  # Sync universe (optional)
```

When sync is enabled:

1. External controllers send DMX data to multiple universes without applying it
2. Controllers send a sync packet to the sync address
3. Home Assistant and other receivers apply all DMX data simultaneously

!!! note "Professional Timing"
    Universe synchronization is critical for pixel mapping, video content, and any effects spanning multiple universes. Without sync, universes update independently causing visible timing differences.

### Data Termination

sACN receivers expect regular data updates. The integration automatically:

- Sends data packets at minimum 1Hz when channels change
- Sends **stream termination packets** when universes are disabled
- Handles receiver timeout detection (2.5 seconds without data)

## Configuration for Receiving External sACN

### Basic Reception Setup

```yaml
dmx:
  fixtures:
    folder: fixtures
    
  sacn:
    source_name: "Home Assistant Receiver"
    priority: 90                     # Lower than external consoles
    universes:
      - 1:
          devices:
            - Main LED Strip:
                fixture: generic-rgbw
                start_address: 1
                mode: 8bit
```

### Professional Multi-Controller Setup

```yaml
dmx:
  sacn:
    source_name: "HA Backup Controller"
    priority: 85                     # Lower than main console (100)
    sync_address: 7000               # Receive universe sync from external controllers
    interface_ip: "10.101.97.101"    # Listen on a specified interface
    refresh_every: 0.5               # Lower retransmit interval to reduce jitter
    
    universes:
      - 1:  # Receives from external lighting console
          devices:
            - Moving Head Bank:
                fixture: generic-moving-head
                start_address: 1
                mode: extended
                
      - 2:  # Receives from pixel mapping controller  
          devices:
            - LED Video Wall:
                fixture: pixel-strip
                start_address: 1
                mode: rgb
```

## Troubleshooting External sACN Reception

### Common Issues

**Home Assistant not receiving sACN data:**

1. **Check multicast groups (run on HA host machine)**:
   ```bash
   netstat -gn | grep 239.255  # Linux: Check if HA joined multicast groups
   netsh interface ip show joins  # Windows: Show multicast memberships
   ```
   **Expected output**: Lines showing `239.255.0.1` and other universe multicast addresses

2. **Test multicast reception (run on HA host machine)**:
   ```bash
   # Listen for sACN traffic on universe 1
   socat UDP4-RECV:5568,ip-add-membership=239.255.0.1:0.0.0.0 -
   ```
   **Expected output**: Raw sACN packet data when external controller transmits

3. **Check firewall (run on HA host machine)**:
   ```bash
   sudo ufw allow 5568/udp               # UFW (Linux)
   sudo firewall-cmd --add-port=5568/udp # firewalld (Linux)
   netsh advfirewall firewall add rule name="sACN" dir=in action=allow protocol=UDP localport=5568  # Windows
   ```
   **Expected output**: Firewall rule added successfully

**External controller not taking control:**

- **Check priority settings**: External controller priority must be higher than Home Assistant's priority
- **Verify source names**: Check logs for multiple source identification
- **Monitor stream status**: Look for timeout/recovery messages in logs

**Priority conflicts between multiple controllers:**

- Review priority hierarchy in all controllers
- Use unique source names for identification
- Monitor equipment displays for active source indication

**The sACN data is being broadcast on the wrong IP**

- Configure the `interface_ip` setting. This defaults to the primary interface as provided by the operating system, due to the potentials of a broadcast storm of providing sACN data to unexpected networks.

### Debug Logging

Enable detailed sACN logging to monitor external data reception:

```yaml
logger:
  logs:
    custom_components.dmx.server.sacn_server: debug
    custom_components.dmx.server.sacn_packet: debug
    custom_components.dmx.io.dmx_io: debug
```

**Useful log patterns for external data:**

- `Received sACN data from [source] on universe X` - External controller sending data
- `Priority switch: [old_source] -> [new_source]` - Controller takeover
- `sACN stream timeout from [source] on universe X` - External controller disconnected
- `Joined multicast group 239.255.X.Y` - Successfully listening for external data
- `Rate limiting updates from external sACN source` - High-frequency external data

### Testing External sACN Controllers

**Software Testing Tools:**

Use **[sACN View](http://www.sacnview.org/)** (free sACN monitoring and transmission tool) to test external controller reception.
