from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

import urllib3
from django.core.exceptions import ValidationError
from urllib3.exceptions import HTTPError

from .approved_egress import pinned_https_pool
from .webhook_egress import WebhookEgressError, resolve_webhook_target, validate_webhook_url

MAX_INTEGRATION_RESPONSE_BYTES = 1024 * 1024
MAX_RETRY_AFTER_SECONDS = 60 * 60


class ProviderRateLimited(WebhookEgressError):
    def __init__(self, retry_at: datetime):
        super().__init__("provider_rate_limited")
        self.retry_at = retry_at


def _retry_at(value: str, *, now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    try:
        seconds = int(value)
        requested = current + timedelta(seconds=max(1, seconds))
    except ValueError:
        try:
            requested = parsedate_to_datetime(value)
            if requested.tzinfo is None:
                requested = requested.replace(tzinfo=UTC)
        except (TypeError, ValueError, OverflowError):
            requested = current + timedelta(minutes=1)
    return min(max(requested, current + timedelta(seconds=1)), current + timedelta(seconds=MAX_RETRY_AFTER_SECONDS))


def validate_integration_base_url(value: str) -> str:
    normalized = validate_webhook_url(value)
    return normalized if normalized.endswith("/") else f"{normalized}/"


def _provider_json_request(
    *,
    base_url: str,
    relative_path: str,
    method: str,
    headers: dict[str, str],
    body: bytes | None = None,
    allow_list: bool = False,
) -> dict[str, Any] | list[Any]:
    """GET one pinned, bounded provider page without following redirects."""

    base = validate_integration_base_url(base_url)
    absolute = urljoin(base, relative_path)
    base_parts = urlsplit(base)
    target_parts = urlsplit(absolute)
    if (
        target_parts.scheme != "https"
        or target_parts.hostname != base_parts.hostname
        or target_parts.port not in (None, 443)
        or target_parts.username
        or target_parts.password
        or target_parts.fragment
    ):
        raise ValidationError("Provider cursors must remain on the configured HTTPS origin.")
    target = resolve_webhook_target(f"https://{target_parts.hostname}{target_parts.path}")
    request_path = target_parts.path or "/"
    if target_parts.query:
        request_path = f"{request_path}?{target_parts.query}"
    pool = pinned_https_pool(
        target,
        connect_timeout=3.0,
        read_timeout=10.0,
        pool_factory=urllib3.HTTPSConnectionPool,
    )
    try:
        response = pool.urlopen(
            method,
            request_path,
            headers={"Host": target.hostname, "Accept": "application/json", **headers},
            body=body,
            redirect=False,
            assert_same_host=False,
            preload_content=False,
        )
        if response.status == 429:
            retry_at = _retry_at(response.headers.get("Retry-After", "60"))
            response.close()
            raise ProviderRateLimited(retry_at)
        if response.status == 410:
            response.close()
            raise WebhookEgressError("provider_cursor_expired")
        if response.status in {400, 401, 403}:
            response.close()
            raise WebhookEgressError("provider_authentication_failed")
        if response.status != 200:
            response.close()
            raise WebhookEgressError("provider_http_error")
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            response.close()
            raise WebhookEgressError("provider_content_type_invalid")
        body = response.read(MAX_INTEGRATION_RESPONSE_BYTES + 1)
        response.close()
        if len(body) > MAX_INTEGRATION_RESPONSE_BYTES:
            raise WebhookEgressError("provider_response_too_large")
        payload = json.loads(body)
        if not isinstance(payload, dict) and not (allow_list and isinstance(payload, list)):
            raise WebhookEgressError("provider_response_invalid")
        return payload
    except (HTTPError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebhookEgressError("provider_connection_failed") from exc
    finally:
        pool.close()


def get_provider_json(*, base_url: str, relative_path: str, authorization: str) -> dict[str, Any]:
    """GET one pinned, bounded provider page without following redirects."""

    payload = _provider_json_request(
        base_url=base_url,
        relative_path=relative_path,
        method="GET",
        headers={"Authorization": authorization},
    )
    if not isinstance(payload, dict):
        raise WebhookEgressError("provider_response_invalid")
    return payload


def get_provider_json_or_list(*, base_url: str, relative_path: str, authorization: str) -> dict[str, Any]:
    """GET a provider page and normalize an allowed top-level list."""

    payload = _provider_json_request(
        base_url=base_url,
        relative_path=relative_path,
        method="GET",
        headers={"Authorization": authorization},
        allow_list=True,
    )
    return {"items": payload} if isinstance(payload, list) else payload


def post_provider_form(*, base_url: str, relative_path: str, fields: dict[str, str]) -> dict[str, Any]:
    """POST a bounded form to a pinned provider endpoint without retaining request values."""

    payload = _provider_json_request(
        base_url=base_url,
        relative_path=relative_path,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=urlencode(fields).encode("utf-8"),
    )
    if not isinstance(payload, dict):
        raise WebhookEgressError("provider_response_invalid")
    return payload


def post_provider_form_basic(
    *, base_url: str, relative_path: str, fields: dict[str, str], username: str, password: str
) -> dict[str, Any]:
    """POST a bounded form with HTTP Basic client authentication.

    The encoded authorization value is constructed only at the egress boundary and is
    never returned or retained.
    """

    authorization = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    payload = _provider_json_request(
        base_url=base_url,
        relative_path=relative_path,
        method="POST",
        headers={
            "Authorization": f"Basic {authorization}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body=urlencode(fields).encode("utf-8"),
    )
    if not isinstance(payload, dict):
        raise WebhookEgressError("provider_response_invalid")
    return payload
