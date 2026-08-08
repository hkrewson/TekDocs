from allauth.account.signals import authentication_step_completed, password_reset, user_logged_in
from allauth.mfa.signals import (
    authentication_failed,
    authenticator_added,
    authenticator_removed,
    authenticator_reset,
    authenticator_used,
)
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


@receiver(authentication_step_completed, dispatch_uid="tekdocs.auth.reauthenticated")
def audit_reauthentication(sender, *, request: HttpRequest, user: User, reauthenticated=False, **kwargs) -> None:  # type: ignore[no-untyped-def]
    if reauthenticated:
        record_auth_event(action="auth.reauthenticated", request=request, user=user)


@receiver(authenticator_added, dispatch_uid="tekdocs.auth.mfa_added")
def audit_mfa_added(sender, *, request: HttpRequest, user: User, **kwargs) -> None:  # type: ignore[no-untyped-def]
    record_auth_event(action="auth.mfa_authenticator_added", request=request, user=user)


@receiver(authenticator_removed, dispatch_uid="tekdocs.auth.mfa_removed")
def audit_mfa_removed(sender, *, request: HttpRequest, user: User, **kwargs) -> None:  # type: ignore[no-untyped-def]
    record_auth_event(action="auth.mfa_authenticator_removed", request=request, user=user)


@receiver(authenticator_reset, dispatch_uid="tekdocs.auth.mfa_reset")
def audit_mfa_reset(sender, *, request: HttpRequest, user: User, **kwargs) -> None:  # type: ignore[no-untyped-def]
    record_auth_event(action="auth.mfa_recovery_reset", request=request, user=user)


@receiver(authenticator_used, dispatch_uid="tekdocs.auth.mfa_succeeded")
def audit_mfa_succeeded(sender, *, request: HttpRequest, user: User, **kwargs) -> None:  # type: ignore[no-untyped-def]
    record_auth_event(action="auth.mfa_succeeded", request=request, user=user)


@receiver(authentication_failed, dispatch_uid="tekdocs.auth.mfa_failed")
def audit_mfa_failed(sender, *, request: HttpRequest, user: User, **kwargs) -> None:  # type: ignore[no-untyped-def]
    record_auth_event(action="auth.mfa_failed", request=request, user=user)
