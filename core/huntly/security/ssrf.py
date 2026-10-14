"""Outbound HTTP guard.

All network fetches of user- or job-supplied URLs go through :func:`safe_get`.
It permits only http(s), resolves the host and refuses private, loopback,
link-local, multicast and reserved addresses (also after every redirect), caps
response size and enforces timeouts.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from huntly.config import HTTP_TIMEOUT_SECONDS, MAX_HTTP_BYTES, USER_AGENT


class UnsafeURL(ValueError):
    pass


ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {None, 80, 443, 8080, 8443}
MAX_REDIRECTS = 5


def _ip_is_public(ip: ipaddress._BaseAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10"))
    )


def validate_url(url: str, resolve: bool = True) -> str:
    if not isinstance(url, str) or len(url) > 2048:
        raise UnsafeURL("URL missing or too long")
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURL(f"Scheme {parts.scheme!r} not allowed")
    if not parts.hostname:
        raise UnsafeURL("URL has no host")
    if parts.username or parts.password:
        raise UnsafeURL("Credentials in URL are not allowed")
    try:
        port = parts.port
    except ValueError as exc:
        raise UnsafeURL("Invalid port") from exc
    if port not in ALLOWED_PORTS:
        raise UnsafeURL(f"Port {port} not allowed")
    host = parts.hostname.lower()
    if host in {"localhost"} or host.endswith(".localhost") or host.endswith(".local") or host.endswith(".internal"):
        raise UnsafeURL("Local hostnames are not allowed")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _ip_is_public(literal):
            raise UnsafeURL("Private or reserved address not allowed")
    elif resolve:
        try:
            infos = socket.getaddrinfo(host, port or 443, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise UnsafeURL(f"Cannot resolve host {host}") from exc
        for info in infos:
            if not _ip_is_public(ipaddress.ip_address(info[4][0])):
                raise UnsafeURL(f"Host {host} resolves to a non-public address")
    return url.strip()


class FetchResult:
    def __init__(self, url: str, status: int, headers: httpx.Headers, content: bytes):
        self.url = url
        self.status_code = status
        self.headers = headers
        self.content = content

    @property
    def text(self) -> str:
        return self.content.decode(_charset(self.headers), errors="replace")

    def json(self):
        import json

        return json.loads(self.content)


def _charset(headers: httpx.Headers) -> str:
    ctype = headers.get("content-type", "")
    for part in ctype.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            return part.split("=", 1)[1].strip('"') or "utf-8"
    return "utf-8"


def safe_get(
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    client: httpx.Client | None = None,
    max_bytes: int = MAX_HTTP_BYTES,
    resolve: bool = True,
) -> FetchResult:
    own = client is None
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=False)
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    try:
        current = validate_url(url, resolve=resolve)
        for _ in range(MAX_REDIRECTS + 1):
            with client.stream("GET", current, headers=hdrs, params=params) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise UnsafeURL("Redirect without location")
                    current = validate_url(urljoin(str(resp.url), location), resolve=resolve)
                    params = None
                    continue
                buf = bytearray()
                for chunk in resp.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        raise UnsafeURL(f"Response exceeds {max_bytes} bytes")
                return FetchResult(str(resp.url), resp.status_code, resp.headers, bytes(buf))
        raise UnsafeURL("Too many redirects")
    finally:
        if own:
            client.close()
