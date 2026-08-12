from __future__ import annotations

import socket

import urllib3
from urllib3.exceptions import HTTPError

from .approved_egress import (
    ApprovedEgressError,
    ApprovedTarget,
    normalize_public_https_url,
    pinned_https_pool,
    resolve_public_https_target,
)

MAX_WEBHOOK_BODY_BYTES = 64 * 1024


WebhookEgressError = ApprovedEgressError
WebhookTarget = ApprovedTarget


def validate_webhook_url(value: str) -> str:
    return normalize_public_https_url(value, label="Webhook")


def resolve_webhook_target(value: str) -> WebhookTarget:
    return resolve_public_https_target(value, resolver=socket.getaddrinfo, label="Webhook")


def post_webhook(*, url: str, body: bytes, headers: dict[str, str]) -> int:
    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        raise WebhookEgressError("request_too_large")
    target = resolve_webhook_target(url)
    pool = pinned_https_pool(
        target,
        connect_timeout=3.0,
        read_timeout=5.0,
        pool_factory=urllib3.HTTPSConnectionPool,
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
        return int(status)
    except HTTPError as exc:
        raise WebhookEgressError("connection_failed") from exc
    finally:
        pool.close()
