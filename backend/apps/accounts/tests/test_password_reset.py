import json
import re
import secrets

import pytest
from django.core import mail
from django.test import Client, override_settings

from apps.accounts.bootstrap import bootstrap_owner

REQUEST_URL = "/_allauth/browser/v1/auth/password/request"
RESET_URL = "/_allauth/browser/v1/auth/password/reset"
SESSION_URL = "/_allauth/browser/v1/auth/session"


@pytest.fixture
def owner(db):
    return bootstrap_owner(
        tenant_name="Example MSP",
        owner_email="owner@example.com",
        owner_display_name="Primary Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    ).owner


def anonymous_client() -> tuple[Client, str]:
    client = Client(enforce_csrf_checks=True)
    response = client.get(SESSION_URL)
    assert response.status_code == 401
    return client, client.cookies["csrftoken"].value


def request_reset(client: Client, csrf: str, email: str):  # type: ignore[no-untyped-def]
    return client.post(
        REQUEST_URL,
        data=json.dumps({"email": email}),
        content_type="application/json",
        headers={"X-CSRFToken": csrf},
    )


def reset_key_from_mail() -> str:
    match = re.search(r"#key=([^\s<]+)", mail.outbox[-1].body)
    assert match
    return match.group(1)


def test_known_and_unknown_reset_requests_share_response_contract(owner):
    known_client, known_csrf = anonymous_client()
    known = request_reset(known_client, known_csrf, owner.email)
    known_payload = known.json()

    assert known.status_code == 200
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [owner.email]
    assert "#key=" in mail.outbox[0].body
    assert "expires in 60 minutes" in mail.outbox[0].body
    assert len(mail.outbox[0].alternatives) == 1

    mail.outbox.clear()
    unknown_client, unknown_csrf = anonymous_client()
    unknown = request_reset(unknown_client, unknown_csrf, "unknown@example.com")

    assert unknown.status_code == known.status_code
    assert unknown.json() == known_payload
    assert len(mail.outbox) == 1
    assert "unknown@example.com" not in str(unknown.json())
    assert len(mail.outbox[0].alternatives) == 1


def test_password_reset_is_single_use_and_invalidates_existing_sessions(owner):
    first_session = Client()
    second_session = Client()
    first_session.force_login(owner)
    second_session.force_login(owner)
    reset_client, csrf = anonymous_client()
    assert request_reset(reset_client, csrf, owner.email).status_code == 200
    key = reset_key_from_mail()

    validation = reset_client.get(RESET_URL, headers={"X-Password-Reset-Key": key})
    assert validation.status_code == 200
    new_password = f"{secrets.token_urlsafe(24)}Bb8!"
    completed = reset_client.post(
        RESET_URL,
        data=json.dumps({"key": key, "password": new_password}),
        content_type="application/json",
        headers={"X-CSRFToken": csrf},
    )

    assert completed.status_code == 401
    owner.refresh_from_db()
    assert owner.check_password(new_password)
    assert len(mail.outbox) == 2
    assert mail.outbox[-1].subject == "Your TekDocs password was changed"
    assert first_session.get("/api/v1/auth/context").status_code == 403
    assert second_session.get("/api/v1/auth/context").status_code == 403
    assert reset_client.get(SESSION_URL).status_code == 401
    assert reset_client.get(RESET_URL, headers={"X-Password-Reset-Key": key}).status_code == 400


def test_expired_and_malformed_reset_keys_share_invalid_response(owner):
    client, csrf = anonymous_client()
    assert request_reset(client, csrf, owner.email).status_code == 200
    key = reset_key_from_mail()

    with override_settings(PASSWORD_RESET_TIMEOUT=-1):
        expired = client.get(RESET_URL, headers={"X-Password-Reset-Key": key})
    malformed = client.get(RESET_URL, headers={"X-Password-Reset-Key": "not-a-reset-key"})

    assert expired.status_code == malformed.status_code == 400
    assert expired.json() == malformed.json()


def test_password_reset_mutations_require_csrf(owner):
    client = Client(enforce_csrf_checks=True)
    missing_request_csrf = request_reset(client, "", owner.email)

    assert missing_request_csrf.status_code == 403
    assert mail.outbox == []

    requesting_client, csrf = anonymous_client()
    assert request_reset(requesting_client, csrf, owner.email).status_code == 200
    key = reset_key_from_mail()
    original_hash = owner.password
    missing_completion_csrf = client.post(
        RESET_URL,
        data=json.dumps({"key": key, "password": f"{secrets.token_urlsafe(24)}Cc9!"}),
        content_type="application/json",
    )
    owner.refresh_from_db()
    assert missing_completion_csrf.status_code == 403
    assert owner.password == original_hash


def test_weak_password_is_rejected_without_consuming_reset_key(owner):
    client, csrf = anonymous_client()
    assert request_reset(client, csrf, owner.email).status_code == 200
    key = reset_key_from_mail()

    rejected = client.post(
        RESET_URL,
        data=json.dumps({"key": key, "password": "password"}),
        content_type="application/json",
        headers={"X-CSRFToken": csrf},
    )

    assert rejected.status_code == 400
    assert client.get(RESET_URL, headers={"X-Password-Reset-Key": key}).status_code == 200
