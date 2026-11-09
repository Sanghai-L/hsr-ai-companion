"""Only an explicitly selected live test may open external sockets."""
import ipaddress
import socket

import pytest


def pytest_addoption(parser):
    parser.addoption("--run-live", action="store_true", default=False)


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-live"):
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(pytest.mark.skip(reason="live requires explicit --run-live"))


@pytest.fixture(autouse=True)
def network_boundary(request, monkeypatch):
    if request.node.get_closest_marker("live") and request.config.getoption("--run-live"):
        return
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo
    original_sendto = socket.socket.sendto

    def local(host):
        if host in ("localhost", b"localhost", None):
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def check(address):
        if isinstance(address, tuple) and not local(address[0]):
            raise OSError("offline test: external network blocked")

    def connect(sock, address):
        check(address)
        return original_connect(sock, address)

    def connect_ex(sock, address):
        check(address)
        return original_connect_ex(sock, address)

    def getaddrinfo(host, *args, **kwargs):
        if not local(host):
            raise OSError("offline test: external DNS blocked")
        return original_getaddrinfo(host, *args, **kwargs)

    def sendto(sock, data, *args):
        check(args[-1])
        return original_sendto(sock, data, *args)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", sendto)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

