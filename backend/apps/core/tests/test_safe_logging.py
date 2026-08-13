from __future__ import annotations

import json
import logging
import sys

from tekdocs.safe_logging import MAX_EVENT_LENGTH, SafeJsonFormatter


def render(message: str, *args: object, **extra: object) -> dict[str, object]:
    record = logging.LogRecord("tekdocs.test", logging.INFO, __file__, 1, message, args, None)
    for name, value in extra.items():
        setattr(record, name, value)
    return json.loads(SafeJsonFormatter().format(record))


def test_formatter_escapes_control_characters_and_retains_only_allowlisted_fields():
    payload = render('line one\nline "two"', request_id="safe-id", arbitrary_payload={"password": "unsafe"})
    assert payload["event"] == 'line one line "two"'
    assert payload["request_id"] == "safe-id"
    assert "arbitrary_payload" not in payload


def test_formatter_redacts_common_credentials_and_bounds_messages():
    payload = render("Authorization: Bearer copied-value password=unsafe otpauth://totp/secret" + "x" * 1000)
    serialized = json.dumps(payload)
    assert "copied-value" not in serialized
    assert "unsafe" not in serialized
    assert "otpauth" not in serialized
    assert len(str(payload["event"])) <= MAX_EVENT_LENGTH


def test_formatter_records_exception_presence_without_exception_text():
    try:
        raise RuntimeError("token=must-not-escape")
    except RuntimeError:
        record = logging.LogRecord("tekdocs.test", logging.ERROR, __file__, 1, "operation_failed", (), sys.exc_info())
    payload = json.loads(SafeJsonFormatter().format(record))
    assert payload["exception"] is True
    assert "must-not-escape" not in json.dumps(payload)
