import socket

from netifaces import gateways, AF_INET


def get_default_gateway():
    return gateways()['default'][AF_INET][0]


def get_private_ip(target_host: str | None = None):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # Connect towards target_host (or default dummy) to find egress interface IP
        target = target_host if target_host else '10.254.254.254'
        s.connect((target, 1))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()

