from __future__ import annotations

import ipaddress
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urlsplit

import urllib3
from django.core.exceptions import ValidationError
from urllib3.exceptions import HTTPError
from urllib3.util import Timeout

MAX_WEBHOOK_BODY_BYTES = 64 * 1024


class WebhookEgressError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WebhookTarget:
    url: str
    hostname: str
    address: str
    path: str


def _public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return bool(address.is_global and not address.is_multicast and not address.is_unspecified)


def validate_webhook_url(value: str) -> str:
    if len(value) > 500:
        raise ValidationError("Webhook URLs are limited to 500 characters.")
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValidationError("Webhook URLs must use HTTPS.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValidationError("Webhook URLs cannot contain credentials, query strings, or fragments.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValidationError("Webhook URLs contain an invalid port.") from exc
    if port not in {None, 443}:
        raise ValidationError("Webhook URLs must use the standard HTTPS port.")
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        try:
            hostname = parsed.hostname.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValidationError("Webhook URLs contain an invalid hostname.") from exc
    else:
        raise ValidationError("Webhook URLs must use a DNS hostname rather than an IP literal.")
    if "." not in hostname or hostname.endswith(".local") or hostname.endswith(".internal"):
        raise ValidationError("Webhook URLs must use a public DNS hostname.")
    path = parsed.path or "/"
    return f"https://{hostname}{path}"


def resolve_webhook_target(value: str) -> WebhookTarget:
    normalized = validate_webhook_url(value)
    parsed = urlsplit(normalized)
    hostname = parsed.hostname
    if hostname is None:  # pragma: no cover - guaranteed by validation
        raise ValidationError("Webhook URL is invalid.")
    try:
        answers = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise WebhookEgressError("dns_unavailable") from exc
    addresses = sorted({str(answer[4][0]) for answer in answers})
    if not addresses or any(not _public_address(address) for address in addresses):
        raise WebhookEgressError("destination_not_public")
    return WebhookTarget(normalized, hostname, addresses[0], parsed.path or "/")


def post_webhook(*, url: str, body: bytes, headers: dict[str, str]) -> int:
    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        raise WebhookEgressError("request_too_large")
    target = resolve_webhook_target(url)
    pool = urllib3.HTTPSConnectionPool(
        target.address,
        port=443,
        timeout=Timeout(connect=3.0, read=5.0),
        retries=False,
        maxsize=1,
        block=True,
        cert_reqs=ssl.CERT_REQUIRED,
        assert_hostname=target.hostname,
        server_hostname=target.hostname,
    )
    request_headers = {**headers, "Host": target.hostname, "Content-Type": "application/json"}
    try:
        response = pool.urlopen(
            "POST",
            target.path,
            body=body,
            headers=request_headers,
            redirect=False,
            assert_same_host=False,
            preload_content=False,
        )
        status = response.status
        response.close()
        return status
    except HTTPError as exc:
        raise WebhookEgressError("connection_failed") from exc
    finally:
        pool.close()
