FROM ghcr.io/home-assistant/home-assistant:latest

# HA
EXPOSE 8123:8123/tcp

# HA Python debugging
EXPOSE 5678:5678/tcp

# Art-Net
EXPOSE 6454:6454/udp

COPY staging/.storage /config/.storage
COPY staging/fixtures /config/fixtures

#COPY staging/configuration.yaml /config/configuration.yaml
COPY staging/platform-configuration3.yaml /config/configuration.yaml


COPY custom_components /config/custom_components
