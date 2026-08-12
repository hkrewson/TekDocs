from __future__ import annotations

import ipaddress
import socket
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from urllib3.util import Timeout


class ApprovedEgressError(RuntimeError):
    """A value-free outbound policy failure suitable for retained status codes."""


@dataclass(frozen=True, slots=True)
class ApprovedTarget:
    url: str
    hostname: str
    address: str
    path: str


def is_public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return bool(address.is_global and not address.is_multicast and not address.is_unspecified)


def normalize_public_https_url(
    value: str,
    *,
    label: str = "Outbound",
    allow_query: bool = False,
    max_length: int = 500,
) -> str:
    if len(value) > max_length:
        raise ValidationError(f"{label} URLs are limited to {max_length} characters.")
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValidationError(f"{label} URLs must use HTTPS.")
    if parsed.username or parsed.password or parsed.fragment or (parsed.query and not allow_query):
        suffix = "credentials or fragments" if allow_query else "credentials, query strings, or fragments"
        raise ValidationError(f"{label} URLs cannot contain {suffix}.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValidationError(f"{label} URLs contain an invalid port.") from exc
    if port not in {None, 443}:
        raise ValidationError(f"{label} URLs must use the standard HTTPS port.")
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        try:
            hostname = parsed.hostname.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValidationError(f"{label} URLs contain an invalid hostname.") from exc
    else:
        raise ValidationError(f"{label} URLs must use a DNS hostname rather than an IP literal.")
    if "." not in hostname or hostname.endswith((".local", ".internal")):
        raise ValidationError(f"{label} URLs must use a public DNS hostname.")
    return urlunsplit(("https", hostname, parsed.path or "/", parsed.query if allow_query else "", ""))


def resolve_public_https_target(
    value: str,
    *,
    resolver: Callable[..., list[Any]] = socket.getaddrinfo,
    label: str = "Outbound",
    allow_query: bool = False,
) -> ApprovedTarget:
    normalized = normalize_public_https_url(value, label=label, allow_query=allow_query)
    parsed = urlsplit(normalized)
    hostname = parsed.hostname
    if hostname is None:  # pragma: no cover - normalization guarantees this
        raise ValidationError(f"{label} URL is invalid.")
    try:
        answers = resolver(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ApprovedEgressError("dns_unavailable") from exc
    addresses = sorted({str(answer[4][0]) for answer in answers})
    if not addresses or any(not is_public_address(address) for address in addresses):
        raise ApprovedEgressError("destination_not_public")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return ApprovedTarget(normalized, hostname, addresses[0], path)


def pinned_https_pool(
    target: ApprovedTarget,
    *,
    connect_timeout: float,
    read_timeout: float,
    pool_factory: Callable[..., Any],
) -> Any:
    """Connect to the reviewed address while retaining hostname/SNI verification."""

    return pool_factory(
        target.address,
        port=443,
        timeout=Timeout(connect=connect_timeout, read=read_timeout),
        retries=False,
        maxsize=1,
        block=True,
        cert_reqs=ssl.CERT_REQUIRED,
        assert_hostname=target.hostname,
        server_hostname=target.hostname,
    )
