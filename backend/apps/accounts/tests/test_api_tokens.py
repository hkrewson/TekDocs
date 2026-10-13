import json
import secrets
import time
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from allauth.account.models import EmailAddress
from allauth.mfa.totp.internal.auth import TOTP, format_hotp_value, generate_totp_secret, hotp_value
from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client
from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import (
    APIToken,
    APITokenKind,
    APITokenPermission,
    BuiltInRole,
    OrganizationAccessAssignment,
    TenantMembership,
    User,
)
from apps.core.models import AuditEvent, Entity, InstallationState, Organization, OrganizationClassification

SESSION_URL = "/_allauth/browser/v1/auth/session"
LOGIN_URL = "/_allauth/browser/v1/auth/login"
TOTP_URL = "/_allauth/browser/v1/account/authenticators/totp"
API_PATH = "/api/v1/auth/api-tokens"


@pytest.fixture(autouse=True)
def isolate_auth_rate_limits():
    # The test profile uses LocMemCache, which database rollback does not reset.
    cache.clear()
    try:
        yield
    finally:
        cache.clear()


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


def authenticated_staff(tenant, *, role=BuiltInRole.READ_ONLY):  # type: ignore[no-untyped-def]
    password = f"{secrets.token_urlsafe(24)}Aa7!"
    user = User.objects.create_user(email="token-staff@example.com", password=password, display_name="Token staff")
    # Match the verified identity created by successful invitation redemption.
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    membership = TenantMembership.objects.create(tenant=tenant, user=user, role=role)
    client = Client(enforce_csrf_checks=True)
    client.get(SESSION_URL)
    assert post(client, LOGIN_URL, {"email": user.email, "password": password}).status_code == 200
    TOTP.activate(user, generate_totp_secret())
    return membership, client


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["personal", "service"])
def test_issued_token_loses_access_after_membership_removal(kind):
    installation, _password, owner_client = authenticated_owner()
    if kind == "personal":
        _membership, issuer = authenticated_staff(installation.tenant)
    else:
        issuer = owner_client
    created = issue(issuer, kind=kind)
    assert created.status_code == 201
    record = APIToken.objects.get(pk=created.json()["id"])
    client = Client(enforce_csrf_checks=True)
    headers = {"Authorization": f"Bearer {created.json()['token']}"}
    assert client.get("/api/v1/documents", headers=headers).status_code == 200
    TenantMembership.objects.get(tenant=installation.tenant, user=record.subject).delete()
    assert client.get("/api/v1/documents", headers=headers).status_code == 403
    assert client.get("/api/v1/auth/context", headers=headers).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["personal", "service"])
def test_issued_token_loses_assigned_only_client_access_immediately(kind):
    installation, _password, owner_client = authenticated_owner()
    organization = create_client(installation.tenant, "Restricted token client")
    organization.access_mode = "assigned_only"
    organization.save(update_fields=("access_mode",))
    other = create_client(installation.tenant, "Other token client")
    if kind == "personal":
        membership, issuer = authenticated_staff(installation.tenant)
        OrganizationAccessAssignment.objects.create(
            tenant=installation.tenant,
            organization=organization,
            membership=membership,
            created_by=installation.owner,
        )
    else:
        issuer = owner_client
    created = issue(
        issuer,
        kind=kind,
        workspace_scope="organization",
        organization_id=str(organization.entity_id),
        permissions=["workspaces.view", "documents.view"],
    )
    assert created.status_code == 201
    record = APIToken.objects.get(pk=created.json()["id"])
    client = Client(enforce_csrf_checks=True)
    headers = {"Authorization": f"Bearer {created.json()['token']}"}
    path = f"/api/v1/workspaces/organizations/{organization.entity_id}/documents"
    assert client.get(path, headers=headers).status_code == 200
    OrganizationAccessAssignment.objects.get(organization=organization, membership__user=record.subject).delete()
    assert client.get(path, headers=headers).status_code in {403, 404}
    assert client.get(f"/api/v1/workspaces/organizations/{other.entity_id}/documents", headers=headers).status_code in {
        403,
        404,
    }
    assert client.get("/api/v1/documents", headers=headers).status_code == 403


@pytest.mark.django_db
def test_personal_token_permission_context_tracks_role_reduction():
    installation, _password, _owner_client = authenticated_owner()
    membership, issuer = authenticated_staff(installation.tenant, role=BuiltInRole.ADMINISTRATOR)
    created = issue(issuer, permissions=["documents.view", "costs.view"])
    assert created.status_code == 201
    client = Client(enforce_csrf_checks=True)
    headers = {"Authorization": f"Bearer {created.json()['token']}"}
    before = client.get("/api/v1/auth/context", headers=headers)
    assert before.status_code == 200
    assert set(before.json()["permissions"]) == {"documents.view", "costs.view"}
    membership.role = BuiltInRole.READ_ONLY
    membership.save(update_fields=("role",))
    after = client.get("/api/v1/auth/context", headers=headers)
    assert after.status_code == 200
    assert after.json()["permissions"] == ["documents.view"]
    assert client.get("/api/v1/documents", headers=headers).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("authorization", ["Bearer", "bEaReR\tinvalid", "Bearer invalid extra"])
@pytest.mark.parametrize("operation", ["list", "create", "rotate", "revoke"])
def test_token_management_rejects_malformed_bearer_with_valid_browser_session(authorization, operation):
    _installation, _password, client = authenticated_owner()
    created = issue(client)
    assert created.status_code == 201
    token_id = created.json()["id"]
    before = list(APIToken.objects.values())
    audit_count = AuditEvent.objects.filter(action__startswith="api_token.").count()
    headers = {"Authorization": authorization, "X-CSRFToken": csrf(client)}
    if operation == "list":
        response = client.get(API_PATH, headers=headers)
    elif operation == "create":
        response = client.post(
            API_PATH,
            data=json.dumps(
                {
                    "name": "Must not issue",
                    "kind": "personal",
                    "workspace_scope": "msp",
                    "organization_id": None,
                    "permissions": ["documents.view"],
                    "expires_in_days": 30,
                }
            ),
            content_type="application/json",
            headers=headers,
        )
    elif operation == "rotate":
        response = client.post(
            f"{API_PATH}/{token_id}/rotate",
            data=json.dumps({"expires_in_days": 30}),
            content_type="application/json",
            headers=headers,
        )
    else:
        response = client.delete(f"{API_PATH}/{token_id}", headers=headers)
    assert response.status_code == 403
    assert list(APIToken.objects.values()) == before
    assert AuditEvent.objects.filter(action__startswith="api_token.").count() == audit_count
    assert "token" not in response.json() and "tokens" not in response.json()


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
@pytest.mark.parametrize("authorization", ["Bearer", "bEaReR invalid", "Bearer invalid extra"])
def test_profile_rejects_malformed_bearer_even_with_browser_session(authorization):
    installation, _password, client = authenticated_owner()
    original_name = installation.owner.display_name
    response = client.patch(
        "/api/v1/auth/profile",
        data=json.dumps({"display_name": "Unexpected mixed credential edit"}),
        content_type="application/json",
        headers={"Authorization": authorization, "X-CSRFToken": csrf(client)},
    )
    assert response.status_code == 403
    installation.owner.refresh_from_db()
    assert installation.owner.display_name == original_name
    assert not AuditEvent.objects.filter(action="auth.profile_updated").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["personal", "service"])
@pytest.mark.parametrize("browser_session", [False, True])
def test_read_only_token_cannot_change_account_profile(kind, browser_session):
    _installation, _password, owner_client = authenticated_owner()
    created = issue(owner_client, kind=kind)
    assert created.status_code == 201
    subject = APIToken.objects.get(pk=created.json()["id"]).subject
    original_name = subject.display_name
    client = owner_client if browser_session else Client(enforce_csrf_checks=True)
    response = client.patch(
        "/api/v1/auth/profile",
        data=json.dumps({"display_name": "Unexpected token edit"}),
        content_type="application/json",
        headers={"Authorization": f"Bearer {created.json()['token']}", "X-CSRFToken": csrf(owner_client)},
    )
    assert response.status_code == 403
    subject.refresh_from_db()
    assert subject.display_name == original_name
    assert not AuditEvent.objects.filter(action="auth.profile_updated").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["personal", "service"])
@pytest.mark.parametrize("browser_session", [False, True])
@pytest.mark.parametrize("path", [SESSION_URL, "/_allauth/browser/v1/auth/sessions", TOTP_URL])
def test_document_token_cannot_authenticate_browser_account_routes(kind, browser_session, path):
    _installation, _password, owner_client = authenticated_owner()
    created = issue(owner_client, kind=kind)
    assert created.status_code == 201
    client = owner_client if browser_session else Client(enforce_csrf_checks=True)
    response = client.get(path, headers={"Authorization": f"Bearer {created.json()['token']}"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "browser_session_required"
    assert response["Cache-Control"] == "no-store"
    assert "data" not in response.json()
    assert owner_client.get(SESSION_URL).status_code == 200


@pytest.mark.django_db
def test_document_token_cannot_revoke_browser_sessions_even_with_csrf():
    _installation, _password, client = authenticated_owner()
    created = issue(client)
    assert created.status_code == 201
    path = "/_allauth/browser/v1/auth/sessions"
    sessions = client.get(path).json()["data"]
    assert sessions
    response = client.delete(
        path,
        data=json.dumps({"sessions": [item["id"] for item in sessions]}),
        content_type="application/json",
        headers={"Authorization": f"Bearer {created.json()['token']}", "X-CSRFToken": csrf(client)},
    )
    assert response.status_code == 403
    assert {item["id"] for item in client.get(path).json()["data"]} == {item["id"] for item in sessions}
    assert not AuditEvent.objects.filter(action="auth.session_revoked").exists()


@pytest.mark.parametrize("path", [SESSION_URL, "/admin/", "/_allauth/oidc/login/", "/api/v10/documents"])
@pytest.mark.parametrize("authorization", ["Bearer", "bEaReR invalid", "Bearer invalid extra"])
def test_non_api_bearer_rejected_before_token_lookup(path, authorization, monkeypatch):
    from django.test import RequestFactory

    from apps.accounts.authentication import APITokenAuthenticationMiddleware

    def unexpected_call(*args):
        pytest.fail("Browser bearer rejection must not authenticate or dispatch the request")

    monkeypatch.setattr("apps.accounts.authentication.authenticate_bearer_token", unexpected_call)
    request = RequestFactory().get(path, HTTP_AUTHORIZATION=authorization)
    assert APITokenAuthenticationMiddleware(unexpected_call)(request).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("authorization", ["Bearer", "Bearer ", "Bearer invalid extra", "bEaReR invalid"])
def test_malformed_bearer_does_not_fall_back_to_authenticated_browser(authorization):
    _installation, _password, client = authenticated_owner()
    assert client.get("/api/v1/documents").status_code == 200
    denied = client.get("/api/v1/documents", headers={"Authorization": authorization})
    assert denied.status_code == 401
    assert denied.json()["error"]["message"] == "Authentication is required."
    assert client.get("/api/v1/documents").status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["personal", "service"])
def test_existing_token_loses_access_when_subject_is_disabled(kind):
    _installation, _password, client = authenticated_owner()
    created = issue(client, kind=kind)
    assert created.status_code == 201
    record = APIToken.objects.get(pk=created.json()["id"])
    bearer = {"Authorization": f"Bearer {created.json()['token']}"}
    token_client = Client(enforce_csrf_checks=True)
    assert token_client.get("/api/v1/documents", headers=bearer).status_code == 200
    User.objects.filter(pk=record.subject_id).update(is_active=False)
    assert token_client.get("/api/v1/documents", headers=bearer).status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["personal", "service"])
def test_existing_token_loses_access_when_its_organization_is_archived(kind):
    installation, _password, client = authenticated_owner()
    organization = create_client(installation.tenant, "Archived token scope")
    created = issue(
        client,
        kind=kind,
        workspace_scope="organization",
        organization_id=str(organization.entity_id),
        permissions=["workspaces.view", "documents.view"],
    )
    assert created.status_code == 201
    bearer = {"Authorization": f"Bearer {created.json()['token']}"}
    token_client = Client(enforce_csrf_checks=True)
    path = f"/api/v1/workspaces/organizations/{organization.entity_id}/documents"
    assert token_client.get(path, headers=bearer).status_code == 200
    Entity.objects.filter(pk=organization.entity_id).update(archived_at=timezone.now())
    assert token_client.get(path, headers=bearer).status_code in {403, 404}
    assert token_client.get("/api/v1/documents", headers=bearer).status_code == 403


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
