from urllib.parse import quote

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core import context
from allauth.mfa.adapter import DefaultMFAAdapter
from allauth.usersessions.adapter import DefaultUserSessionsAdapter
from django.conf import settings

from apps.core.email import (
    send_mfa_security_email,
    send_password_changed_email,
    send_password_reset_email,
    send_password_reset_unavailable_email,
)

from .audit import record_auth_event
from .mfa_storage import decrypt_mfa_value, encrypt_mfa_value


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
        mfa_changes = {
            "mfa/email/totp_activated": "enabled",
            "mfa/email/totp_deactivated": "disabled",
            "mfa/email/recovery_codes_generated": "recovery_codes_replaced",
        }
        if template_prefix in mfa_changes:
            recipient = email or user.email
            if recipient:
                send_mfa_security_email(recipient=recipient, change=mfa_changes[template_prefix])
            return None
        if template_prefix != "account/email/password_reset":
            return super().send_notification_mail(template_prefix, user, context=context, email=email)
        recipient = email or user.email
        if recipient:
            send_password_changed_email(recipient=recipient)
        return None


class AuditedUserSessionsAdapter(DefaultUserSessionsAdapter):
    """End maintained allauth sessions and leave a value-free security event."""

    def end_sessions(self, sessions) -> None:  # type: ignore[no-untyped-def]
        selected = list(sessions)
        super().end_sessions(selected)
        request = context.request
        user = request.user if request is not None and request.user.is_authenticated else None
        record_auth_event(action="auth.session_revoked", request=request, user=user)


class EncryptedMFAAdapter(DefaultMFAAdapter):
    """Store allauth TOTP and recovery seeds through TekDocs envelope encryption."""

    def encrypt(self, text: str) -> str:
        return encrypt_mfa_value(text)

    def decrypt(self, encrypted_text: str) -> str:
        return decrypt_mfa_value(encrypted_text)
