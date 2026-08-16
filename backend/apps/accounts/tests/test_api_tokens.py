import json
import secrets
import time
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from allauth.mfa.totp.internal.auth import format_hotp_value, hotp_value
from django.contrib.auth.hashers import check_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client
from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import APIToken, APITokenKind, APITokenPermission, User
from apps.core.models import AuditEvent, Entity, InstallationState, Organization, OrganizationClassification

SESSION_URL = "/_allauth/browser/v1/auth/session"
LOGIN_URL = "/_allauth/browser/v1/auth/login"
TOTP_URL = "/_allauth/browser/v1/account/authenticators/totp"
API_PATH = "/api/v1/auth/api-tokens"


def csrf(client: Client) -> str:
    return client.cookies["csrftoken"].value


def post(client: Client, url: str, payload: dict):  # type: ignore[type-arg,no-untyped-def]
    return client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        headers={"X-CSRFToken": csrf(client)},
    )


def authenticated_owner() -> tuple[object, str, Client]:
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    password = f"{secrets.token_urlsafe(24)}Aa7!"
    result = bootstrap_owner(
        tenant_name="Example MSP",
        owner_email="owner@example.com",
        owner_display_name="Primary Owner",
        password=password,
    )
    client = Client(enforce_csrf_checks=True)
    client.get(SESSION_URL)
    assert post(client, LOGIN_URL, {"email": result.owner.email, "password": password}).status_code == 200
    started = client.get(TOTP_URL)
    secret = parse_qs(urlsplit(started.json()["meta"]["totp_url"]).query)["secret"][0]
    code = format_hotp_value(hotp_value(secret, int(time.time()) // 30))
    assert post(client, TOTP_URL, {"code": code}).status_code == 200
    return result, password, client


def create_client(tenant, name: str) -> Organization:  # type: ignore[no-untyped-def]
    entity = Entity.objects.create_owned(tenant=tenant, entity_type="organization", display_name=name)
    organization = Organization.objects.create(tenant=tenant, entity=entity)
    OrganizationClassification.objects.create(tenant=tenant, organization=organization, kind="client")
    return organization


def issue(client: Client, **overrides):  # type: ignore[no-untyped-def]
    payload = {
        "name": "Documentation automation",
        "kind": "personal",
        "workspace_scope": "msp",
        "organization_id": None,
        "permissions": ["documents.view"],
        "expires_in_days": 30,
    }
    payload.update(overrides)
    return post(client, API_PATH, payload)


@pytest.mark.django_db
def test_personal_token_is_one_time_scoped_and_audited_without_secret():
    installation, _password, client = authenticated_owner()
    response = issue(client)
    assert response.status_code == 201
    plaintext = response.json()["token"]
    record = APIToken.objects.get()
    assert plaintext.startswith("tdp_")
    assert plaintext not in record.secret_hash
    assert check_password(plaintext.split("_", 2)[2], record.secret_hash)
    assert response["Cache-Control"] == "no-store"

    listed = client.get(API_PATH)
    assert listed.status_code == 200
    assert "token" not in listed.json()["tokens"][0]
    assert listed.json()["tokens"][0]["permissions"] == ["documents.view"]
    service_eligibility = {item["key"]: item["service_eligible"] for item in listed.json()["permissions"]}
    assert service_eligibility["documents.view"] is True
    assert service_eligibility["costs.view"] is False
    event = AuditEvent.objects.get(action="api_token.created", actor=installation.owner)
    assert event.metadata == {}
    assert plaintext not in json.dumps(listed.json())

    allowed = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {plaintext}"})
    denied = client.get("/api/v1/workspaces/msp/assets", headers={"Authorization": f"Bearer {plaintext}"})
    assert allowed.status_code == 200
    assert denied.status_code == 403


@pytest.mark.django_db
def test_organization_token_is_exact_scope_and_msp_data_is_not_visible():
    installation, _password, client = authenticated_owner()
    first = create_client(installation.tenant, "First Client")
    second = create_client(installation.tenant, "Second Client")
    response = issue(
        client,
        workspace_scope="organization",
        organization_id=str(first.entity_id),
        permissions=["workspaces.view", "documents.view"],
    )
    assert response.status_code == 201
    token = response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    first_response = client.get(f"/api/v1/workspaces/organizations/{first.entity_id}/documents", headers=headers)
    second_response = client.get(f"/api/v1/workspaces/organizations/{second.entity_id}/documents", headers=headers)
    assert first_response.status_code == 200
    assert second_response.status_code in {403, 404}
    assert client.get("/api/v1/documents", headers=headers).status_code == 403


@pytest.mark.django_db
def test_personal_token_can_read_but_not_mutate_document_files_and_exports(tmp_path, settings):
    installation, _password, client = authenticated_owner()
    settings.MEDIA_ROOT = tmp_path
    created = post(client, "/api/v1/documents", {"title": "Token export", "markdown": "# Token export"})
    assert created.status_code == 201
    document_id = created.json()["id"]
    upload = client.post(
        f"/api/v1/documents/{document_id}/attachments",
        {"file": SimpleUploadedFile("private.txt", b"bounded private file")},
        headers={"X-CSRFToken": csrf(client)},
    )
    assert upload.status_code == 201
    attachment_id = upload.json()["id"]
    issued = issue(client)
    token = issued.json()["token"]
    bearer = {"Authorization": f"Bearer {token}"}

    exported = client.get(f"/api/v1/documents/{document_id}/export?export_format=md", headers=bearer)
    downloaded = client.get(
        f"/api/v1/documents/{document_id}/attachments/{attachment_id}/download",
        headers={**bearer, "Range": "bytes=0-6"},
    )
    denied_upload = client.post(
        f"/api/v1/documents/{document_id}/attachments",
        {"file": SimpleUploadedFile("denied.txt", b"must not persist")},
        headers=bearer,
    )

    assert exported.status_code == 200
    assert exported.content == b"# Token export\n"
    assert downloaded.status_code == 206
    assert downloaded.content == b"bounded"
    assert denied_upload.status_code == 403
    assert AuditEvent.objects.get(action="document.exported").metadata == {"format": "md", "attachment_count": 0}
    assert AuditEvent.objects.get(action="document.attachment.downloaded").metadata == {
        "partial": True,
        "purpose": "attachment",
    }
    assert b"private" not in json.dumps(list(AuditEvent.objects.values_list("metadata", flat=True))).encode()


@pytest.mark.django_db
def test_rotation_revocation_and_invalid_tokens_fail_closed():
    _installation, _password, client = authenticated_owner()
    created = issue(client)
    token_id = created.json()["id"]
    first = created.json()["token"]
    rotated = post(client, f"{API_PATH}/{token_id}/rotate", {"expires_in_days": 60})
    assert rotated.status_code == 200
    second = rotated.json()["token"]
    assert first != second
    assert client.get("/api/v1/documents", headers={"Authorization": f"Bearer {first}"}).status_code == 401
    assert client.get("/api/v1/documents", headers={"Authorization": f"Bearer {second}"}).status_code == 200

    revoked = client.delete(f"{API_PATH}/{token_id}", headers={"X-CSRFToken": csrf(client)})
    assert revoked.status_code == 200
    assert client.get("/api/v1/documents", headers={"Authorization": f"Bearer {second}"}).status_code == 401
    malformed = client.get("/api/v1/documents", headers={"Authorization": "Bearer not-a-token"})
    assert malformed.status_code == 401
    assert malformed.json()["error"]["message"] == "Authentication is required."


@pytest.mark.django_db
def test_service_tokens_use_noninteractive_subject_and_cannot_manage_tokens():
    installation, _password, client = authenticated_owner()
    organization = create_client(installation.tenant, "Service Client")
    created = issue(
        client,
        name="Read-only connector",
        kind="service",
        workspace_scope="organization",
        organization_id=str(organization.entity_id),
        permissions=["workspaces.view", "assets.view"],
    )
    assert created.status_code == 201
    record = APIToken.objects.get(kind=APITokenKind.SERVICE)
    assert record.subject.is_service_account is True
    assert record.subject.has_usable_password() is False
    assert User.objects.filter(pk=record.subject_id, is_staff=True).exists() is False
    token = created.json()["token"]
    bearer = {"Authorization": f"Bearer {token}"}
    assert (
        client.get(f"/api/v1/workspaces/organizations/{organization.entity_id}/assets", headers=bearer).status_code
        == 200
    )
    assert client.post(API_PATH, data={}, content_type="application/json", headers=bearer).status_code in {401, 403}
    assert client.get(API_PATH, headers=bearer).status_code == 403
    assert client.delete(f"{API_PATH}/{record.id}", headers=bearer).status_code == 403

    revoked = client.delete(f"{API_PATH}/{record.id}", headers={"X-CSRFToken": csrf(client)})
    assert revoked.status_code == 200
    record.subject.refresh_from_db()
    assert record.subject.is_active is False


@pytest.mark.django_db
def test_token_permissions_and_authority_are_immutable():
    _installation, _password, client = authenticated_owner()
    created = issue(client)
    record = APIToken.objects.get(pk=created.json()["id"])
    permission = APITokenPermission.objects.get(token=record)
    with transaction.atomic(), pytest.raises(IntegrityError):
        permission.delete()
    with transaction.atomic(), pytest.raises(IntegrityError):
        APITokenPermission.objects.create(
            tenant=record.tenant,
            token=record,
            permission="assets.view",
        )
    with transaction.atomic(), pytest.raises(IntegrityError):
        APIToken.objects.filter(pk=record.pk).update(expires_at=timezone.now() + timedelta(days=90))
    permission.refresh_from_db()
    assert permission.permission == "documents.view"


@pytest.mark.django_db
def test_token_issue_requires_mfa_recent_session_csrf_and_eligible_permissions():
    installation, password, client = authenticated_owner()
    no_csrf = client.post(API_PATH, data=json.dumps({}), content_type="application/json")
    assert no_csrf.status_code == 403
    browser = Client(enforce_csrf_checks=True)
    browser.get(SESSION_URL)
    password_step = post(browser, LOGIN_URL, {"email": installation.owner.email, "password": password})
    assert password_step.status_code == 401
    disallowed = issue(client, permissions=["credential_references.open"])
    assert disallowed.status_code == 400
    session = client.session
    session[AUTHENTICATION_METHODS_SESSION_KEY] = []
    session.save()
    assert issue(client).status_code == 403
