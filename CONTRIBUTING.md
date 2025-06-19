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

[Capabilities](custom_components/artnet_led/fixture/capability.py) and [wheels](custom_components/artnet_led/fixture/wheel.py) use some magic in the name of expandability and low coupling.
The [parser](custom_components/artnet_led/fixture/parser.py) directly instances these classes.
The mandatory and optional parameters directly match [OpenFixtureLibrary's spec](https://github.com/OpenLightingProject/open-fixture-library/blob/master/docs/capability-types.md).

### Useful tools

* [The ArtNetominator](https://www.lightjams.com/artnetominator/): Discovers ArtNet controllers and shows channel updates
* [DMX-Workshop](https://singularity-uk.com/product/dmx-workshop/): Easy tool to send universe updates and ArtNet triggers to the integration