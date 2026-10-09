"""Bounded, value-free health check for the configured Redis/Valkey broker."""

from functools import lru_cache
from typing import cast

from django.conf import settings
from redis import Redis


@lru_cache(maxsize=4)
def _client(url: str) -> Redis:
    # Reuse a bounded connection pool across frequent readiness requests.
    return Redis.from_url(
        url, max_connections=4, socket_connect_timeout=0.5, socket_timeout=0.5, retry_on_timeout=False
    )


def valkey_health() -> str:
    """Return only a coarse status; never return URLs, exceptions, or key data."""

    url = settings.CELERY_BROKER_URL
    if not url.startswith(("redis://", "rediss://", "unix://")):
        return "not_configured"
    try:
        client = _client(url)
        if not client.ping():
            return "unavailable"
        persistence = cast(dict[str, object], client.info("persistence"))
    except Exception:  # noqa: BLE001 - dependency and URL errors must fail closed without leaking details
        return "unavailable"
    if persistence.get("aof_enabled") and persistence.get("aof_last_write_status") != "ok":
        return "degraded"
    if persistence.get("rdb_last_bgsave_status") not in (None, "ok"):
        return "degraded"
    return "ready"
