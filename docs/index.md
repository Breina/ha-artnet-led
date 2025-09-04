# Art-Net & sACN LED Lighting for DMX

A comprehensive Home Assistant integration that transforms your smart home into a professional lighting control system using both Art-Net and sACN (E1.31) protocols.

## What is this integration?

This integration creates software-based Art-Net and sACN controllers within Home Assistant, allowing you to control professional lighting fixtures, LED strips, and stage equipment directly from your smart home platform. Whether you're setting up residential lighting, home theater ambiance, nightclub installations, or professional stage lighting, this integration bridges the gap between consumer smart home technology and professional lighting control protocols.

## What You Get

Once configured, the integration creates Home Assistant entities for each fixture and channel:

![Integration Entities](img/Entities.png)
*Example: Configured fixtures appear as standard Home Assistant entities with full control capabilities*

## Key Features

### Dual Protocol Support
- **Art-Net Controller** - Software-based Art-Net controller with bi-directional communication and auto-discovery
- **sACN (E1.31) Streaming** - ANSI E1.31-2016 compliant sACN implementation with multicast and unicast support
- **Universe Management** - Control multiple universes across both protocols with flexible addressing
- **Priority System** - sACN priority handling for professional multi-controller setups
- **Network Efficiency** - Art-Net broadcast for simplicity, sACN multicast for large installations

```mermaid
graph TB
    subgraph "Home Assistant Server"
        subgraph "Home Assistant Core"
            HA[Home Assistant Core]
            ENTITIES[Light entities<br/>Switch entities<br/>Number entities]
            AUTO[Automations<br/>Scripts<br/>Scenes]
        end
        
        subgraph "DMX Integration"
            DMX_INT[DMX LED Integration]
            ARTNET_CTRL[Software Art-Net Controller]
            SACN_CTRL[Software sACN Controller]
            FIXTURE_MGR[OpenFixtureLibrary]
        end
    end
    
    subgraph "Network Infrastructure"
        NETWORK[Ethernet/WiFi Network<br/>Art-Net & sACN Protocols]
    end
    
    subgraph "DMX Hardware"
        ARTNET_NODE[Art-Net Node]
        SACN_NODE[sACN Node]
        DMX_OUT[DMX Output]
        FIXTURES[LED Fixtures<br/>Moving Lights<br/>Dimmers]
    end
    
    subgraph "External Controllers"
        EXT_ARTNET[Art-Net Controller<br/>Lighting Console]
        EXT_SACN[sACN Controller<br/>Professional Console]
        FADERS[Physical Faders<br/>Buttons<br/>Encoders]
    end
    
    %% Bidirectional communication within HA
    DMX_INT -->|Events| HA 
    DMX_INT <--> ENTITIES
    HA <--> AUTO
    AUTO <--> ENTITIES
    FIXTURE_MGR -.->|Fixture definitions| DMX_INT
    
    %% Network communication
    NETWORK <--> ARTNET_NODE
    NETWORK <--> SACN_NODE
    EXT_ARTNET <--> NETWORK
    EXT_SACN <--> NETWORK
    NETWORK <--> ARTNET_CTRL
    NETWORK <--> SACN_CTRL
    ARTNET_CTRL <--> DMX_INT
    SACN_CTRL <--> DMX_INT
    
    %% Hardware connections
    ARTNET_NODE --> DMX_OUT
    SACN_NODE --> DMX_OUT
    DMX_OUT --> FIXTURES
    FADERS --> EXT_ARTNET
    FADERS --> EXT_SACN
    
    %% Data flow labels
    
    classDef haCore fill:#41BDF5,stroke:#1976D2,color:#fff
    classDef integration fill:#4CAF50,stroke:#2E7D32,color:#fff
    classDef hardware fill:#FF9800,stroke:#F57C00,color:#fff
    classDef network fill:#9C27B0,stroke:#6A1B9A,color:#fff
    
    class HA,ENTITIES,AUTO haCore
    class DMX_INT,ARTNET_CTRL,SACN_CTRL,FIXTURE_MGR integration
    class ARTNET_NODE,SACN_NODE,EXT_ARTNET,EXT_SACN,FADERS,DMX_OUT,FIXTURES hardware
    class NETWORK network
```

### Professional Fixture Support
- **[OpenFixtureLibrary](https://open-fixture-library.org/) integration** - Use industry-standard fixture definitions for accurate control
- **Multi-mode fixtures** - Support for fixtures with different channel modes (8-bit, 16-bit, RGB, RGBW, etc.)
- **Flexible addressing** - Configure start addresses and channel mappings per fixture
- **Multiple fixture types** - From simple LED strips to complex moving lights

### Network Protocols
- **Art-Net** - Primary protocol support with full universe control and bidirectional communication
- **sACN (E1.31)** - ANSI E1.31-2016 compliant Streaming ACN support with multicast and unicast transmission

## How it works

1. Install through HACS as "Art-net LED Lighting for DMX"
2. Place OpenFixtureLibrary JSON files in your configured fixtures folder
3. Define universes, devices, and addressing in Home Assistant configuration
4. Control fixtures through standard Home Assistant entities and automations

## Works well with

- **[Adaptive Lighting integration](https://github.com/basnijholt/adaptive-lighting)** - Automatically adjusts color temperature to match the sun's position throughout the day
- **[Emulated HUE Add-On](https://github.com/hass-emulated-hue/core)** - Mimics a Hue controller to send real-time lighting data to Art-Net fixtures (e.g., TV ambilight effects to RGBW strips)

## Community

[Home Assistant community](https://community.home-assistant.io/t/dmx-lighting/2248)

## Getting Started

Ready to transform your lighting setup? 

1. **Choose Your Protocol** - Read our [Art-Net vs sACN](artnet-vs-sacn.md) guide to decide which protocol suits your needs
2. **Configure Your Setup** - Follow the [Configuration](config.md) guide to set up your universes and fixtures
3. **Learn Advanced Features** - Explore [Art-Net Communication](artnet-controller-communication.md) and [External sACN Controller](sacn-communication.md) for professional setups

---

*Art-Net™ Designed by and Copyright Artistic Licence*

*This integration brings professional lighting control capabilities to Home Assistant, making it easy to create stunning lighting effects and integrate them with your existing smart home automation.*