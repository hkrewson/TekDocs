from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

MAX_EVENT_LENGTH = 512
SAFE_EXTRA_FIELDS = {
    "duration_ms",
    "method",
    "request_id",
    "route",
    "status_code",
    "task_name",
}
SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+"),
    re.compile(r"otpauth://\S+", re.IGNORECASE),
    re.compile(r"(?i)(authorization|cookie|password|secret|token)\s*[:=]\s*[^\s,;]+"),
)


def _safe_event(message: str) -> str:
    value = message.replace("\r", " ").replace("\n", " ")
    for pattern in SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value[:MAX_EVENT_LENGTH]


def _safe_extra(name: str, value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    return _safe_event(str(value))


class SafeJsonFormatter(logging.Formatter):
    """Emit one bounded JSON object without serializing arbitrary LogRecord state."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str | int | float | bool | None] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": _safe_event(record.getMessage()),
        }
        for name in SAFE_EXTRA_FIELDS:
            if hasattr(record, name):
                payload[name] = _safe_extra(name, getattr(record, name))
        if record.exc_info:
            payload["exception"] = True
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
