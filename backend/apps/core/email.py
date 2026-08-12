from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.template.loader import render_to_string


class TransactionalTemplate(StrEnum):
    SYSTEM_TEST = "system_test"
    INVITATION = "invitation"
    RECOVERY_REQUEST = "password_reset"
    RECOVERY_UNAVAILABLE = "password_reset_unavailable"
    CREDENTIAL_CHANGED = "password_changed"
    MFA_CHANGED = "mfa_changed"
    NOTIFICATION = "notification"


def send_transactional_email(
    *,
    template: TransactionalTemplate,
    subject: str,
    recipient: str,
    context: dict[str, Any] | None = None,
    message_id: str | None = None,
) -> int:
    normalized_recipient = recipient.strip()
    if "\r" in normalized_recipient or "\n" in normalized_recipient:
        raise ValidationError("Enter a valid email address.")
    validate_email(normalized_recipient)
    if "\r" in subject or "\n" in subject:
        raise ValidationError("Email subjects cannot contain newlines.")
    if message_id is not None and (
        "\r" in message_id
        or "\n" in message_id
        or not message_id.startswith("<")
        or not message_id.endswith(">")
    ):
        raise ValidationError("Email message identifiers must be a bracketed value.")

    template_context = {"product_name": "TekDocs", **(context or {})}
    text_body = render_to_string(f"email/{template.value}.txt", template_context).strip()
    html_body = render_to_string(f"email/{template.value}.html", template_context).strip()
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[normalized_recipient],
        headers={"Message-ID": message_id} if message_id is not None else None,
    )
    message.attach_alternative(html_body, "text/html")
    return message.send(fail_silently=False)


def send_notification_email(
    *,
    recipient: str,
    title: str,
    message: str,
    app_url: str,
    delivery_id: str,
) -> int:
    return send_transactional_email(
        template=TransactionalTemplate.NOTIFICATION,
        subject="TekDocs notification",
        recipient=recipient,
        context={"notification_title": title, "notification_message": message, "app_url": app_url},
        message_id=f"<tekdocs-notification-{delivery_id}@notification.tekdocs.invalid>",
    )


def send_system_test_email(recipient: str) -> int:
    return send_transactional_email(
        template=TransactionalTemplate.SYSTEM_TEST,
        subject="TekDocs email delivery test",
        recipient=recipient,
    )


def send_invitation_email(
    *,
    recipient: str,
    acceptance_url: str,
    tenant_name: str,
    expires_at: datetime,
) -> int:
    return send_transactional_email(
        template=TransactionalTemplate.INVITATION,
        subject="You are invited to TekDocs",
        recipient=recipient,
        context={
            "acceptance_url": acceptance_url,
            "tenant_name": tenant_name,
            "expires_at": expires_at,
        },
    )


def send_password_reset_email(*, recipient: str, reset_url: str, expires_in_minutes: int) -> int:
    return send_transactional_email(
        template=TransactionalTemplate.RECOVERY_REQUEST,
        subject="Reset your TekDocs password",
        recipient=recipient,
        context={"reset_url": reset_url, "expires_in_minutes": expires_in_minutes},
    )


def send_password_changed_email(*, recipient: str) -> int:
    return send_transactional_email(
        template=TransactionalTemplate.CREDENTIAL_CHANGED,
        subject="Your TekDocs password was changed",
        recipient=recipient,
    )


def send_password_reset_unavailable_email(*, recipient: str) -> int:
    return send_transactional_email(
        template=TransactionalTemplate.RECOVERY_UNAVAILABLE,
        subject="TekDocs password reset request",
        recipient=recipient,
    )


def send_mfa_security_email(*, recipient: str, change: str) -> int:
    messages = {
        "enabled": "Two-factor authentication was enabled.",
        "disabled": "Two-factor authentication was disabled.",
        "recovery_codes_replaced": "Your two-factor recovery codes were replaced.",
    }
    try:
        description = messages[change]
    except KeyError as exc:
        raise ValueError("Unsupported MFA notification change") from exc
    return send_transactional_email(
        template=TransactionalTemplate.MFA_CHANGED,
        subject="Your TekDocs two-factor security changed",
        recipient=recipient,
        context={"change_description": description},
    )
