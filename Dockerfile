FROM ghcr.io/home-assistant/home-assistant:2023.4.4

# HA
EXPOSE 8123:8123/tcp

# HA Python debugging
EXPOSE 5678:5678/tcp

# Art-Net
EXPOSE 6454:6454/udp

COPY staging/.storage /config/.storage

#COPY staging/configuration.yaml /config/configuration.yaml
COPY staging/platform-configuration.yaml /config/configuration.yaml

COPY custom_components /config/custom_components