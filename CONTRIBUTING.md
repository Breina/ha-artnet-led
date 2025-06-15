## Update docs

`pip install mkdocs mkdocs-material mkdocs-mermaid2-plugin mkdocs-awesome-pages-plugin mkdocstrings[python]`

Serve:
```shell
mkdocs serve
```

Deploy:
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