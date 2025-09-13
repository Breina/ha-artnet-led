# Contributing to ha-artnet-led

Thank you for your interest in contributing to ha-artnet-led! This document provides guidelines and information for contributors.

## Development Setup

### Prerequisites

- Python 3.13.2 or higher
- Home Assistant development environment
- Git

### Installation

1. Clone the repository:
```bash
git clone https://github.com/your-repo/ha-artnet-led.git
cd ha-artnet-led
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
```

**Windows:**
```bash
.venv\Scripts\activate
```

**macOS/Linux:**
```bash
source .venv/bin/activate
```

3. Install development dependencies:
```bash
pip install -e .[dev]
```

## Code Quality Tools

This project uses several tools to maintain code quality and consistency. All configurations are defined in `pyproject.toml`.

### Ruff (Linting and Import Sorting)

[Ruff](https://docs.astral.sh/ruff/) is an extremely fast Python linter that replaces flake8, isort, and other linting tools.

**Run linting:**
```bash
ruff check .
```

**Auto-fix linting issues:**
```bash
ruff check --fix .
```

### Black (Code Formatting)

[Black](https://black.readthedocs.io/) ensures consistent code formatting across the project.

**Format code:**
```bash
black .
```

**Check formatting:**
```bash
black --check .
```

### MyPy (Type Checking)

[MyPy](https://mypy.readthedocs.io/) provides static type checking to catch type-related errors.

**Run type checking:**
```bash
mypy custom_components/dmx
```

### Pre-commit Integration

We provide a `.pre-commit-config.yaml` file that automatically runs Ruff, Black, and MyPy before each commit.

**Install and setup pre-commit:**
```bash
pip install pre-commit
pre-commit install
```

The pre-commit hooks will now run automatically on every commit. You can also run them manually:

```bash
# Run on all files
pre-commit run --all-files
```
```bash
# Run on staged files only
pre-commit run
```

## Testing

### Running Tests

**Run all tests:**
```bash
cd tests
pytest
```

**Run with coverage:**
```bash
pytest --cov=custom_components.dmx --cov-report=html
```

**Run with JUnit XML output (for CI):**
```bash
pytest --doctest-modules --junitxml=junit/test-results.xml
```

## Documentation

### Update docs

`pip install mkdocs mkdocs-material mkdocs-mermaid2-plugin mkdocs-awesome-pages-plugin mkdocstrings[python]`

### Serve:

Show docs on localhost

```shell
mkdocs serve
```

[Open browser](http://localhost:8000/)

### Deploy

Put it on GitHub

```shell
mkdocs gh-deploy
```

## Testing through Docker

```shell
docker build -f Dockerfile -t ha-artnet-led-staging . && docker run -p 0.0.0.0:8123:8123 -p 0.0.0.0:6454:6454/udp -p 0.0.0.0:5678:5678 -a --name LocalHA --network bridge ha-artnet-led-staging
``` 

[Open browser](http://localhost:8123/)

## Development

### Magic code

[Capabilities](custom_components/dmx/fixture/capability.py) and [wheels](custom_components/dmx/fixture/wheel.py) use some magic in the name of expandability and low coupling.
The [parser](custom_components/dmx/fixture/parser.py) directly instances these classes.
The mandatory and optional parameters directly match [OpenFixtureLibrary's spec](https://github.com/OpenLightingProject/open-fixture-library/blob/master/docs/capability-types.md).

### Entities

There are currently 5 types of entities;

* [DmxNumberEntity](custom_components/dmx/entity/number.py): These are created for every entity that has a DMX range.
* [DmxSelectEntity](custom_components/dmx/entity/select.py): Created for channels that have multiple capabilities.
* [DmxLightEntity](custom_components/dmx/entity/light/light_entity.py): A light fixture is configured based on the best effort channels it can find.
* [ArtNetEntity](custom_components/dmx/entity/node.py): Entities created by a discovered Art-Net node.
* [DmxUniverseSwitch](custom_components/dmx/switch.py): Enables or disables a universe.

### Design decisions

* We are fully compatible with OpenFixtureLibrary. When requiring features that are not yet supported in their format, open a GitHub issue or create a PR on their end. Do not deviate from the spec.
* Don't change the unique entity ID, this will cause mayhem.

Other than that, we're open to changes, improvements and refactorings.

### Useful tools

* [The ArtNetominator](https://www.lightjams.com/artnetominator/): Discovers ArtNet controllers and shows channel updates
* [DMX-Workshop](https://singularity-uk.com/product/dmx-workshop/): Easy tool to send universe updates and ArtNet triggers to the integration