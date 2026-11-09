"""Bounded HTTPS fetch. No cookies, retries, redirects or alternate services."""
from dataclasses import dataclass
import http.client
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request

from companion.contracts import CompanionError, ErrorCode


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict


def public_url(url, *, hosts=None):
    try:
        parts = urllib.parse.urlsplit(url)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password or
                parts.port not in {None, 443} or "\\" in url or any(ord(c) < 32 for c in url)):
            raise ValueError()
        if hosts is not None and parts.hostname.lower() not in hosts:
            raise ValueError()
        try:
            address = ipaddress.ip_address(parts.hostname)
        except ValueError:
            if parts.hostname.lower() in {"localhost", "localhost.localdomain"} or "." not in parts.hostname:
                raise ValueError()
        else:
            if not address.is_global:
                raise ValueError()
        return urllib.parse.urlunsplit(("https", parts.netloc.lower(), parts.path or "/", parts.query, ""))
    except (TypeError, ValueError):
        raise CompanionError(ErrorCode.INVALID_INPUT, "仅允许无凭据的公开 HTTPS 资料地址")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class PinnedHTTPS(urllib.request.HTTPSHandler):
    """Resolve once, validate every address, connect to that IP with the original TLS name."""
    def __init__(self, address):
        super().__init__()
        self.address = address

    def https_open(self, request):
        address = self.address
        class Connection(http.client.HTTPSConnection):
            def connect(self):
                self.sock = socket.create_connection((address, self.port), self.timeout, self.source_address)
                self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)
        return self.do_open(Connection, request, context=self._context)


def fetch(url, *, timeout=8, max_bytes=2*1024*1024, audit=None, operation="public_source"):
    url = public_url(url)
    host = urllib.parse.urlsplit(url).hostname
    from companion.diagnostics.redaction import network_event
    if audit:
        audit(network_event(url, operation, "attempt"))
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses:
            raise OSError("no address")
        for _, _, _, _, address in addresses:
            if not ipaddress.ip_address(address[0]).is_global:
                raise CompanionError(ErrorCode.INVALID_INPUT, "资料地址解析到非公开网络")
        request = urllib.request.Request(url, headers={"User-Agent": "HSRCompanion/0.2 (local player research)",
                                                       "Accept": "application/json,text/html,text/plain", "Accept-Encoding": "identity"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), PinnedHTTPS(addresses[0][4][0]), NoRedirect())
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            content = response.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise CompanionError(ErrorCode.BUDGET_EXHAUSTED, "来源内容超过读取预算")
            if audit:
                audit(network_event(url, operation, "success" if response.code == 200 else "http_error", status=response.code))
            return Response(response.code, content, dict(response.headers))
    except CompanionError:
        raise
    except (OSError, urllib.error.URLError):
        if audit:
            audit(network_event(url, operation, "failure"))
        raise CompanionError(ErrorCode.NETWORK_FAILURE, "来源请求失败或超时；未自动重试", retryable=True)
