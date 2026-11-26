"""Covers TRS-105 (TAD §2.2): port auto-detection when the default port is busy."""

import socket

from tarsier.cli.ports import find_free_port, is_port_free


def test_find_free_port_returns_default_when_free():
    port = find_free_port(preferred=38811)
    assert port == 38811


def test_find_free_port_skips_busy_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", 38812))
        blocker.listen(1)
        assert is_port_free(38812) is False
        port = find_free_port(preferred=38812)
        assert port != 38812
        assert is_port_free(port) is True
