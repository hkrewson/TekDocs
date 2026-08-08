from allauth.account.signals import password_reset, user_logged_in
from allauth.usersessions.signals import session_client_changed
from django.contrib.auth.signals import user_logged_out, user_login_failed
from django.dispatch import receiver
from django.http import HttpRequest

from .audit import record_auth_event
from .models import User


@receiver(user_logged_in, dispatch_uid="tekdocs.auth.login_succeeded")
def audit_login_succeeded(sender, *, request: HttpRequest, user: User, **kwargs) -> None:  # type: ignore[no-untyped-def]
    record_auth_event(action="auth.login_succeeded", request=request, user=user)


@receiver(user_login_failed, dispatch_uid="tekdocs.auth.login_failed")
def audit_login_failed(sender, *, request: HttpRequest | None, **kwargs) -> None:  # type: ignore[no-untyped-def]
    record_auth_event(action="auth.login_failed", request=request)


@receiver(user_logged_out, dispatch_uid="tekdocs.auth.logged_out")
def audit_logged_out(sender, *, request: HttpRequest, user: User | None, **kwargs) -> None:  # type: ignore[no-untyped-def]
    record_auth_event(action="auth.logged_out", request=request, user=user)


@receiver(password_reset, dispatch_uid="tekdocs.auth.password_reset")
def audit_password_reset(sender, *, request: HttpRequest, user: User, **kwargs) -> None:  # type: ignore[no-untyped-def]
    record_auth_event(action="auth.password_reset", request=request, user=user)


@receiver(session_client_changed, dispatch_uid="tekdocs.auth.session_client_changed")
def audit_session_client_changed(sender, *, request: HttpRequest, to_session, **kwargs) -> None:  # type: ignore[no-untyped-def]
    record_auth_event(action="auth.session_client_changed", request=request, user=to_session.user)
