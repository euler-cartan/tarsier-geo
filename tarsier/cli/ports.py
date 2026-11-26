"""Port selection for `tarsier-geo start` (TAD §2.2).

Tries the default port first; if it's busy, finds the next free one so the
app always starts rather than failing with "address in use".
"""

import socket

DEFAULT_PORT = 8731
_MAX_SCAN = 50


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
        return True


def find_free_port(preferred: int = DEFAULT_PORT, host: str = "127.0.0.1") -> int:
    for port in range(preferred, preferred + _MAX_SCAN):
        if is_port_free(port, host):
            return port
    raise RuntimeError(
        f"No free port found in range {preferred}-{preferred + _MAX_SCAN - 1}"
    )
