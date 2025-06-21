## Update docs

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

## Run tests

```shell
cd tests
```

```shell
pytest
```

## Development

### Magic code

[Capabilities](custom_components/dmx/fixture/capability.py) and [wheels](custom_components/dmx/fixture/wheel.py) use some magic in the name of expandability and low coupling.
The [parser](custom_components/dmx/fixture/parser.py) directly instances these classes.
The mandatory and optional parameters directly match [OpenFixtureLibrary's spec](https://github.com/OpenLightingProject/open-fixture-library/blob/master/docs/capability-types.md).

### Entities

There are currently 3 types of entities;

* [DmxNumberEntity](custom_components/dmx/entity/number.py): These are created for every entity that has a DMX range.
* [DmxSelectEntity](custom_components/dmx/entity/select.py): Created for channels that have multiple capabilities.
* [DmxLightEntity](custom_components/dmx/entity/light/light_entity.py): A best effort light fixture is configured based on the light channels it can find.

### Design decisions

* We are fully compatible with OpenFixtureLibrary. When requiring features that are not yet supported in their format, open a GitHub issue or create a PR on their end. Do not deviate from the spec.
* Don't change the unique entity ID, this will cause mayhem.

Other than that, we're open to changes, improvements and refactorings.

### Useful tools

* [The ArtNetominator](https://www.lightjams.com/artnetominator/): Discovers ArtNet controllers and shows channel updates
* [DMX-Workshop](https://singularity-uk.com/product/dmx-workshop/): Easy tool to send universe updates and ArtNet triggers to the integration