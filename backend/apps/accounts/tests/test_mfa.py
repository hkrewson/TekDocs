import importlib
import json
import secrets
import time

import pytest
from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import format_hotp_value, generate_totp_secret, hotp_value
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.mfa_storage import PREFIX, decrypt_mfa_value, encrypt_mfa_value
from apps.core.models import AuditEvent, InstallationState

LOGIN_URL = "/_allauth/browser/v1/auth/login"
SESSION_URL = "/_allauth/browser/v1/auth/session"
MFA_AUTH_URL = "/_allauth/browser/v1/auth/2fa/authenticate"
REAUTH_URL = "/_allauth/browser/v1/auth/reauthenticate"
AUTHENTICATORS_URL = "/_allauth/browser/v1/account/authenticators"
TOTP_URL = "/_allauth/browser/v1/account/authenticators/totp"
RECOVERY_URL = "/_allauth/browser/v1/account/authenticators/recovery-codes"


@pytest.fixture
def owner_credentials(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    password = f"{secrets.token_urlsafe(24)}Aa7!"
    result = bootstrap_owner(
        tenant_name="Example MSP",
        owner_email="owner@example.com",
        owner_display_name="Primary Owner",
        password=password,
    )
    return result, password


def csrf(client: Client) -> str:
    return client.cookies["csrftoken"].value


def post(client: Client, url: str, payload: dict[str, str]):  # type: ignore[no-untyped-def]
    return client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        headers={"X-CSRFToken": csrf(client)},
    )


def login(client: Client, email: str, password: str):  # type: ignore[no-untyped-def]
    client.get(SESSION_URL)
    return post(client, LOGIN_URL, {"email": email, "password": password})


def current_code(secret: str) -> str:
    return format_hotp_value(hotp_value(secret, int(time.time()) // 30))


def enroll_totp(client: Client) -> tuple[str, list[str]]:
    started = client.get(TOTP_URL)
    assert started.status_code == 404
    secret = started.json()["meta"]["secret"]
    activated = post(client, TOTP_URL, {"code": current_code(secret)})
    assert activated.status_code == 200
    recovery = client.get(RECOVERY_URL)
    assert recovery.status_code == 200
    return secret, recovery.json()["data"]["unused_codes"]


def forget_recent_authentication(client: Client) -> None:
    session = client.session
    session[AUTHENTICATION_METHODS_SESSION_KEY] = []
    session.save()


@pytest.mark.django_db
def test_totp_enrollment_encrypts_secrets_and_shows_recovery_codes_once(owner_credentials):
    result, password = owner_credentials
    client = Client(enforce_csrf_checks=True)
    assert login(client, result.owner.email, password).status_code == 200

    secret, recovery_codes = enroll_totp(client)

    totp = Authenticator.objects.get(user=result.owner, type=Authenticator.Type.TOTP)
    recovery = Authenticator.objects.get(user=result.owner, type=Authenticator.Type.RECOVERY_CODES)
    assert totp.data["secret"].startswith(PREFIX)
    assert recovery.data["seed"].startswith(PREFIX)
    assert secret not in str(totp.data)
    assert all(code not in str(recovery.data) for code in recovery_codes)
    assert len(recovery_codes) == 10
    viewed_again = client.get(RECOVERY_URL)
    assert viewed_again.status_code == 200
    assert "unused_codes" not in viewed_again.json()["data"]
    assert viewed_again.json()["data"]["unused_code_count"] == 10
    assert mail.outbox[-1].subject == "Your TekDocs two-factor security changed"
    assert secret not in mail.outbox[-1].body
    assert all(code not in mail.outbox[-1].body for code in recovery_codes)
    actions = list(AuditEvent.objects.filter(action__startswith="auth.mfa_").values_list("action", flat=True))
    assert actions.count("auth.mfa_authenticator_added") == 2
    assert all(event.metadata == {} for event in AuditEvent.objects.filter(action__startswith="auth.mfa_"))


@pytest.mark.django_db
def test_mfa_login_accepts_one_time_recovery_code_and_rejects_reuse(owner_credentials):
    result, password = owner_credentials
    setup_client = Client(enforce_csrf_checks=True)
    assert login(setup_client, result.owner.email, password).status_code == 200
    _secret, recovery_codes = enroll_totp(setup_client)
    assert setup_client.delete(SESSION_URL, headers={"X-CSRFToken": csrf(setup_client)}).status_code == 401

    challenged = Client(enforce_csrf_checks=True)
    password_step = login(challenged, result.owner.email, password)
    assert password_step.status_code == 401
    flow = next(item for item in password_step.json()["data"]["flows"] if item["id"] == "mfa_authenticate")
    assert flow["is_pending"] is True
    assert set(flow["types"]) == {"totp", "recovery_codes"}
    assert challenged.get(reverse("auth-context")).status_code == 403

    completed = post(challenged, MFA_AUTH_URL, {"code": recovery_codes[0]})
    assert completed.status_code == 200
    assert challenged.get(reverse("auth-context")).status_code == 200
    assert AuditEvent.objects.filter(action="auth.mfa_succeeded", actor=result.owner).exists()
    assert challenged.delete(SESSION_URL, headers={"X-CSRFToken": csrf(challenged)}).status_code == 401

    replay = Client(enforce_csrf_checks=True)
    assert login(replay, result.owner.email, password).status_code == 401
    rejected = post(replay, MFA_AUTH_URL, {"code": recovery_codes[0]})
    assert rejected.status_code == 400
    failure = AuditEvent.objects.get(action="auth.mfa_failed")
    assert failure.actor == result.owner
    assert failure.metadata == {}


@pytest.mark.django_db
def test_sensitive_mfa_changes_require_recent_password_reauthentication(owner_credentials):
    result, password = owner_credentials
    client = Client(enforce_csrf_checks=True)
    assert login(client, result.owner.email, password).status_code == 200
    _secret, original_codes = enroll_totp(client)
    forget_recent_authentication(client)

    blocked_reset = post(client, RECOVERY_URL, {})
    assert blocked_reset.status_code == 401
    assert any(flow["id"] == "reauthenticate" for flow in blocked_reset.json()["data"]["flows"])
    assert post(client, REAUTH_URL, {"password": password}).status_code == 200
    regenerated = post(client, RECOVERY_URL, {})
    assert regenerated.status_code == 200
    replacement_codes = regenerated.json()["data"]["unused_codes"]
    assert replacement_codes != original_codes
    assert AuditEvent.objects.filter(action="auth.reauthenticated", actor=result.owner).exists()
    assert AuditEvent.objects.filter(action="auth.mfa_recovery_reset", actor=result.owner).exists()

    forget_recent_authentication(client)
    blocked_delete = client.delete(TOTP_URL, headers={"X-CSRFToken": csrf(client)})
    assert blocked_delete.status_code == 401
    assert post(client, REAUTH_URL, {"password": password}).status_code == 200
    removed = client.delete(TOTP_URL, headers={"X-CSRFToken": csrf(client)})
    assert removed.status_code == 200
    assert Authenticator.objects.filter(user=result.owner).count() == 0
    assert AuditEvent.objects.filter(action="auth.mfa_authenticator_removed", actor=result.owner).count() == 2
    assert mail.outbox[-1].subject == "Your TekDocs two-factor security changed"


@pytest.mark.django_db
def test_mfa_mutations_require_csrf_and_authentication(owner_credentials):
    result, password = owner_credentials
    anonymous = Client(enforce_csrf_checks=True)
    assert anonymous.get(AUTHENTICATORS_URL).status_code == 401
    authenticated = Client(enforce_csrf_checks=True)
    assert login(authenticated, result.owner.email, password).status_code == 200
    secret = authenticated.get(TOTP_URL).json()["meta"]["secret"]

    missing_csrf = authenticated.post(
        TOTP_URL,
        data=json.dumps({"code": current_code(secret)}),
        content_type="application/json",
    )

    assert missing_csrf.status_code == 403
    assert Authenticator.objects.filter(user=result.owner).count() == 0


def test_mfa_storage_round_trip_rejects_plaintext_and_tampering():
    plaintext = secrets.token_urlsafe(32)
    encrypted = encrypt_mfa_value(plaintext)
    assert encrypted.startswith(PREFIX)
    assert plaintext not in encrypted
    assert decrypt_mfa_value(encrypted) == plaintext
    with pytest.raises(ImproperlyConfigured):
        decrypt_mfa_value(plaintext)
    with pytest.raises(ImproperlyConfigured):
        decrypt_mfa_value(encrypted[:-1] + ("A" if encrypted[-1] != "A" else "B"))


@pytest.mark.django_db
def test_mfa_data_migration_encrypts_legacy_values(owner_credentials):
    result, _password = owner_credentials
    secret = generate_totp_secret()
    authenticator = Authenticator.objects.create(
        user=result.owner,
        type=Authenticator.Type.TOTP,
        data={"secret": secret},
    )
    migration = importlib.import_module("apps.accounts.migrations.0004_encrypt_existing_mfa_secrets")

    class CurrentApps:
        @staticmethod
        def get_model(app_label, model_name):  # type: ignore[no-untyped-def]
            assert (app_label, model_name) == ("mfa", "Authenticator")
            return Authenticator

    migration.encrypt_existing_secrets(CurrentApps(), None)

    authenticator.refresh_from_db()
    assert authenticator.data["secret"].startswith(PREFIX)
    assert secret not in str(authenticator.data)
    assert decrypt_mfa_value(authenticator.data["secret"]) == secret
