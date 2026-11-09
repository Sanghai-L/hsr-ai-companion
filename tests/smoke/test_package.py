import socket
import subprocess
import sys

import pytest


def test_module_entry():
    result = subprocess.run([sys.executable, "-m", "companion", "--help"], capture_output=True, timeout=10)
    assert result.returncode == 0
    assert b"companion" in result.stdout


def test_external_network_is_blocked():
    with pytest.raises(OSError, match="blocked"):
        socket.create_connection(("203.0.113.1", 443), timeout=0.1)
    with pytest.raises(OSError, match="blocked"):
        socket.getaddrinfo("example.com", 443)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        with pytest.raises(OSError, match="blocked"):
            sock.sendto(b"test", ("203.0.113.1", 53))

