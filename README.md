# Art-net LED Lighting for DMX

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/Breina/ha-artnet-led/validate.yml)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/Breina/ha-artnet-led/hassfest.yaml)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/Breina/ha-artnet-led/python.yml)
[![Documentation](https://img.shields.io/badge/docs-github%20pages-blue)](https://breina.github.io/ha-artnet-led/)

A Home Assistant integration that transforms your instance into a professional Art-Net lighting controller. Control DMX fixtures, LED strips, and stage lighting directly from Home Assistant with full bidirectional Art-Net communication.

![Integration Entities](docs/Entities.png)

## Features

- **Software Art-Net Controller** - Turn Home Assistant into a fully functional Art-Net node
- **OpenFixtureLibrary Integration** - Use industry-standard fixture definitions
- **Bidirectional Communication** - Send commands and receive updates from other Art-Net controllers
- **Multiple Universe Support** - Control multiple Art-Net universes with flexible addressing
- **Professional Fixture Support** - RGB, RGBW, moving lights, dimmers, and more
- **Network Auto-Discovery** - Automatic Art-Net node discovery via ArtPoll/ArtPollReply

## Quick Start

### Installation

1. Install via HACS as a custom repository:
   - Add `https://github.com/Breina/ha-artnet-led` as a custom repository
   - Search for "Art-net LED Lighting for DMX"
   - Install and restart Home Assistant

2. Download fixture definitions from [Open Fixture Library](https://open-fixture-library.org/)
3. Place fixture JSON files in `config/fixtures/`
4. Configure your setup in `configuration.yaml`

### Basic Configuration

```yaml
dmx:
  artnet:
    universes:
      - 0:
          devices:
            - Living Room Strip:
                start_address: 1
                fixture: Generic RGB
                mode: 3ch
```

## Documentation

📖 **[Complete Documentation](https://breina.github.io/ha-artnet-led/)**

- [Configuration Guide](https://breina.github.io/ha-artnet-led/config/) - Detailed setup instructions

## Works Great With

- **[Adaptive Lighting](https://github.com/basnijholt/adaptive-lighting)** - Automatic color temperature adjustment
- **[Emulated Hue](https://github.com/hass-emulated-hue/core)** - Real-time ambilight effects to Art-Net fixtures

## Architecture

```mermaid
graph LR
    HA[Home Assistant] <--> ARTNET[Art-Net Integration]
    ARTNET <--> NETWORK[Art-Net Network]
    NETWORK --> NODE[Art-Net Node]
    NODE --> FIXTURES[DMX Fixtures]
    CONTROLLER[Art-Net Controller] <--> NETWORK
```

## Support

- 🐛 **Issues**: [GitHub Issues](https://github.com/Breina/ha-artnet-led/issues)
- 📖 **Documentation**: [GitHub Pages](https://breina.github.io/ha-artnet-led/)
- 💬 **Discussions**: [Home Assistant community](https://community.home-assistant.io/t/dmx-lighting/2248)

## Contributing

Contributions are welcome! Please read our [contributing guidelines](CONTRIBUTING.md) and submit pull requests for any improvements.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

*Art-Net™ Designed by and Copyright Artistic Licence*