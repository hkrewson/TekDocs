from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin, urlsplit

import urllib3
from django.core.exceptions import ValidationError
from urllib3.exceptions import HTTPError

from .approved_egress import pinned_https_pool
from .webhook_egress import WebhookEgressError, resolve_webhook_target, validate_webhook_url

MAX_INTEGRATION_RESPONSE_BYTES = 1024 * 1024


def validate_integration_base_url(value: str) -> str:
    normalized = validate_webhook_url(value)
    return normalized if normalized.endswith("/") else f"{normalized}/"


def get_provider_json(*, base_url: str, relative_path: str, authorization: str) -> dict[str, Any]:
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
            "GET",
            request_path,
            headers={"Host": target.hostname, "Accept": "application/json", "Authorization": authorization},
            redirect=False,
            assert_same_host=False,
            preload_content=False,
        )
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
        if not isinstance(payload, dict):
            raise WebhookEgressError("provider_response_invalid")
        return payload
    except (HTTPError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebhookEgressError("provider_connection_failed") from exc
    finally:
        pool.close()
