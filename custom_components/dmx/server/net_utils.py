import socket

LOOPBACK_IP = "127.0.0.1"


def get_private_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(("10.254.254.254", 1))
        addr: tuple[str, int] = s.getsockname()
        return addr[0]
    except Exception:
        return LOOPBACK_IP
    finally:
        s.close()
