from urllib.parse import quote

from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings

from apps.core.email import (
    send_password_changed_email,
    send_password_reset_email,
    send_password_reset_unavailable_email,
)


class InviteOnlyAccountAdapter(DefaultAccountAdapter):
    """Public registration remains closed; users enter through controlled invitations."""

    def is_open_for_signup(self, request):  # type: ignore[no-untyped-def]
        return False

    def get_reset_password_from_key_url(self, key: str) -> str:
        return f"{settings.TEKDOCS_PUBLIC_URL}/auth/reset-password#key={quote(key, safe='')}"

    def send_password_reset_mail(self, user, email, context):  # type: ignore[no-untyped-def]
        send_password_reset_email(
            recipient=email,
            reset_url=context["password_reset_url"],
            expires_in_minutes=settings.PASSWORD_RESET_TIMEOUT // 60,
        )

    def send_mail(self, template_prefix, email, context):  # type: ignore[no-untyped-def]
        if template_prefix == "account/email/unknown_account":
            send_password_reset_unavailable_email(recipient=email)
            return None
        return super().send_mail(template_prefix, email, context)

    def send_notification_mail(self, template_prefix, user, context=None, email=None):  # type: ignore[no-untyped-def]
        if template_prefix != "account/email/password_reset":
            return super().send_notification_mail(template_prefix, user, context=context, email=email)
        recipient = email or user.email
        if recipient:
            send_password_changed_email(recipient=recipient)
        return None
