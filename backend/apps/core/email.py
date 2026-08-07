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


def send_transactional_email(
    *,
    template: TransactionalTemplate,
    subject: str,
    recipient: str,
    context: dict[str, Any] | None = None,
) -> int:
    normalized_recipient = recipient.strip()
    if "\r" in normalized_recipient or "\n" in normalized_recipient:
        raise ValidationError("Enter a valid email address.")
    validate_email(normalized_recipient)
    if "\r" in subject or "\n" in subject:
        raise ValidationError("Email subjects cannot contain newlines.")

    template_context = {"product_name": "TekDocs", **(context or {})}
    text_body = render_to_string(f"email/{template.value}.txt", template_context).strip()
    html_body = render_to_string(f"email/{template.value}.html", template_context).strip()
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[normalized_recipient],
    )
    message.attach_alternative(html_body, "text/html")
    return message.send(fail_silently=False)


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
