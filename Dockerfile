FROM ghcr.io/home-assistant/home-assistant:2026.5

# Pre-install custom component dependencies (HA 2024.12+ no longer auto-installs them reliably)
RUN pip3 install pyartnet==2.0

# HA
EXPOSE 8123:8123/tcp

# HA Python debugging
EXPOSE 5678:5678/tcp

# Art-Net
EXPOSE 6454:6454/udp

COPY staging/.storage /config/.storage

COPY staging/configuration.yaml /config/configuration.yaml

COPY custom_components /config/custom_components
