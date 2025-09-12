import socket

from netifaces import AF_INET, gateways


def get_default_gateway() -> str:
    return str(gateways()["default"][AF_INET][0])


def get_private_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(("10.254.254.254", 1))
        addr: tuple[str, int] = s.getsockname()
        return addr[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()
