from io import StringIO
from unittest.mock import patch

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.email import (
    TransactionalTemplate,
    send_notification_email,
    send_system_test_email,
    send_transactional_email,
)


def test_transactional_email_renders_text_and_html_parts(settings):
    settings.DEFAULT_FROM_EMAIL = "TekDocs <noreply@example.com>"

    delivered = send_system_test_email("operator@example.com")

    assert delivered == 1
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.subject == "TekDocs email delivery test"
    assert message.from_email == "TekDocs <noreply@example.com>"
    assert message.to == ["operator@example.com"]
    assert "email delivery is working" in message.body
    assert len(message.alternatives) == 1
    assert "<h1" in message.alternatives[0].content
    assert message.alternatives[0].mimetype == "text/html"


@pytest.mark.parametrize(
    "recipient",
    ["not-an-address", "operator@example.com\nBcc: exposed@example.com"],
)
def test_transactional_email_rejects_invalid_or_injected_recipient(recipient):
    with pytest.raises(ValidationError):
        send_system_test_email(recipient)
    assert mail.outbox == []


def test_transactional_email_rejects_header_injection():
    with pytest.raises(ValidationError):
        send_transactional_email(
            template=TransactionalTemplate.SYSTEM_TEST,
            subject="Delivery test\nBcc: exposed@example.com",
            recipient="operator@example.com",
        )
    assert mail.outbox == []


def test_notification_email_uses_generic_headers_and_escapes_display_values(settings):
    settings.DEFAULT_FROM_EMAIL = "TekDocs <noreply@example.com>"

    delivered = send_notification_email(
        recipient="reader@example.com",
        title='<script>alert("title")</script>',
        message='<img src=x onerror="alert(1)">',
        app_url="https://tekdocs.example.test",
        delivery_id="00000000-0000-4000-8000-000000000001",
    )

    assert delivered == 1
    message = mail.outbox[0]
    assert message.subject == "TekDocs notification"
    assert "script" not in message.subject
    html = message.alternatives[0].content
    assert "&lt;script&gt;" in html
    assert "<script>" not in html
    assert "<img src=x" not in html
    assert message.extra_headers["Message-ID"].endswith("@notification.tekdocs.invalid>")


def test_operator_command_reports_delivery_without_recipient_or_content():
    output = StringIO()

    call_command("send_test_email", "operator@example.com", stdout=output)

    result = output.getvalue()
    assert "accepted one test message" in result
    assert "operator@example.com" not in result
    assert "Email delivery is working" not in result
    assert len(mail.outbox) == 1


def test_operator_command_returns_generic_backend_failure():
    with patch("apps.core.management.commands.send_test_email.send_system_test_email", side_effect=OSError("host")):
        with pytest.raises(CommandError, match="did not accept") as exc_info:
            call_command("send_test_email", "operator@example.com")

    assert "operator@example.com" not in str(exc_info.value)
    assert "host" not in str(exc_info.value)
