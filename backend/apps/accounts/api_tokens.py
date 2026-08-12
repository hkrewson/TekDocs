from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from allauth.account.internal.flows.reauthentication import did_recently_authenticate
from allauth.mfa.models import Authenticator
from django.contrib.auth.hashers import check_password, make_password
from django.db import models, transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied, ValidationError

from apps.core.models import AuditEvent, Organization

from .models import (
    APIToken,
    APITokenKind,
    APITokenPermission,
    APITokenWorkspaceScope,
    BuiltInRole,
    OrganizationAccessAssignment,
    TenantMembership,
    User,
)
from .policy import (
    IMPLEMENTED_READS,
    PERMISSION_BY_KEY,
    InstallationMemberContext,
    PermissionKey,
    PrivilegedMFARequired,
    context_has_permission,
    require_installation_member,
    require_permission,
)

TOKEN_PATTERN = re.compile(r"^(tdp|tds)_([0-9a-f]{12})_([A-Za-z0-9_-]{43})$")
TOKEN_MAX_DAYS = 365
TOKEN_LAST_USED_INTERVAL = timedelta(minutes=5)
TOKEN_DISALLOWED_PERMISSIONS = frozenset({PermissionKey.CREDENTIAL_REFERENCES_OPEN})
TOKEN_ALLOWED_PERMISSIONS = frozenset(
    definition.key
    for definition in PERMISSION_BY_KEY.values()
    if not definition.requires_mfa and definition.key not in TOKEN_DISALLOWED_PERMISSIONS
)
SERVICE_TOKEN_ALLOWED_PERMISSIONS = TOKEN_ALLOWED_PERMISSIONS & IMPLEMENTED_READS
_DUMMY_SECRET_HASH = make_password(secrets.token_urlsafe(32))


class RecentAuthenticationRequired(PermissionDenied):
    default_detail = "Recent password or MFA reauthentication is required."
    default_code = "recent_authentication_required"


@dataclass(frozen=True, slots=True)
class IssuedAPIToken:
    record: APIToken
    plaintext: str


def require_token_management_browser_session(request) -> InstallationMemberContext:  # type: ignore[no-untyped-def]
    authorization = request.headers.get("Authorization", "")
    if (
        getattr(request, "api_token", None) is not None
        or getattr(request, "auth", None) is not None
        or authorization.lower().startswith("bearer ")
    ):
        raise PermissionDenied("API tokens cannot manage API tokens.")
    context = require_installation_member(request.user)
    if context.surface != "msp":
        raise PermissionDenied("API tokens are available only to MSP staff.")
    return context


def require_token_management_session(request) -> InstallationMemberContext:  # type: ignore[no-untyped-def]
    context = require_token_management_browser_session(request)
    if not Authenticator.objects.filter(user=request.user, type=Authenticator.Type.TOTP).exists():
        raise PrivilegedMFARequired()
    if not did_recently_authenticate(request._request):
        raise RecentAuthenticationRequired()
    return context


def token_permission_catalog() -> list[dict[str, object]]:
    return [
        {
            **PERMISSION_BY_KEY[key].as_dict(),
            "service_eligible": key in SERVICE_TOKEN_ALLOWED_PERMISSIONS,
        }
        for key in sorted(TOKEN_ALLOWED_PERMISSIONS, key=lambda permission: permission.value)
    ]


def _normalized_permissions(values: list[str], *, kind: APITokenKind) -> tuple[PermissionKey, ...]:
    try:
        permissions = tuple(sorted({PermissionKey(value) for value in values}, key=lambda item: item.value))
    except ValueError as exc:
        raise ValidationError({"permissions": "Select only token-eligible permissions."}) from exc
    if not permissions:
        raise ValidationError({"permissions": "Select at least one permission."})
    allowed = SERVICE_TOKEN_ALLOWED_PERMISSIONS if kind == APITokenKind.SERVICE else TOKEN_ALLOWED_PERMISSIONS
    if any(permission not in allowed for permission in permissions):
        raise ValidationError({"permissions": "MFA or browser-only permissions cannot be delegated to an API token."})
    return permissions


def _organization(
    context: InstallationMemberContext,
    workspace_scope: APITokenWorkspaceScope,
    organization_entity_id: UUID | None,
) -> Organization | None:
    if workspace_scope == APITokenWorkspaceScope.MSP:
        if organization_entity_id is not None:
            raise ValidationError({"organization_id": "MSP-scoped tokens do not accept an organization."})
        return None
    if organization_entity_id is None:
        raise ValidationError({"organization_id": "Select one organization Workspace."})
    try:
        return (
            Organization.scoped.for_tenant(context.tenant)
            .select_related("entity")
            .get(entity_id=organization_entity_id, entity__archived_at__isnull=True)
        )
    except Organization.DoesNotExist as exc:
        raise NotFound("The organization is unavailable.") from exc


def _authorize_permissions(
    context: InstallationMemberContext,
    permissions: tuple[PermissionKey, ...],
    organization: Organization | None,
) -> None:
    if any(not context_has_permission(context, permission, organization=organization) for permission in permissions):
        raise PermissionDenied("A token cannot exceed your current authority in the selected Workspace.")


def _new_material(kind: APITokenKind) -> tuple[str, str, str]:
    marker = "tdp" if kind == APITokenKind.PERSONAL else "tds"
    while True:
        prefix = secrets.token_hex(6)
        if not APIToken.objects.filter(prefix=prefix).exists():
            break
    secret = secrets.token_urlsafe(32)
    return prefix, make_password(secret), f"{marker}_{prefix}_{secret}"


def _service_subject(
    *, context: InstallationMemberContext, name: str, organization: Organization | None, actor: User
) -> User:
    subject_id = uuid.uuid4()
    subject = User(
        id=subject_id,
        email=f"service-{subject_id}@service.invalid",
        display_name=f"Service · {name}",
        is_service_account=True,
        is_active=True,
    )
    subject.set_unusable_password()
    subject.save()
    membership = TenantMembership.objects.create(
        tenant=context.tenant,
        user=subject,
        role=BuiltInRole.READ_ONLY,
    )
    if organization is not None:
        OrganizationAccessAssignment.objects.create(
            tenant=context.tenant,
            organization=organization,
            membership=membership,
            created_by=actor,
        )
    return subject


@transaction.atomic
def issue_api_token(
    *,
    request: Any,
    name: str,
    kind: APITokenKind,
    workspace_scope: APITokenWorkspaceScope,
    organization_entity_id: UUID | None,
    permissions: list[str],
    expires_in_days: int,
) -> IssuedAPIToken:
    context = require_token_management_session(request)
    if kind == APITokenKind.SERVICE:
        require_permission(request.user, PermissionKey.INTEGRATIONS_MANAGE)
    normalized_name = " ".join(name.split())
    if not normalized_name or any(ord(character) < 32 for character in normalized_name):
        raise ValidationError({"name": "Enter a visible token name without control characters."})
    normalized_permissions = _normalized_permissions(permissions, kind=kind)
    organization = _organization(context, workspace_scope, organization_entity_id)
    if organization is not None and PermissionKey.WORKSPACES_VIEW not in normalized_permissions:
        raise ValidationError({"permissions": "Organization tokens must include workspaces.view."})
    _authorize_permissions(context, normalized_permissions, organization)
    subject = (
        request.user
        if kind == APITokenKind.PERSONAL
        else _service_subject(context=context, name=normalized_name, organization=organization, actor=request.user)
    )
    prefix, secret_hash, plaintext = _new_material(kind)
    record = APIToken.objects.create(
        tenant=context.tenant,
        kind=kind,
        name=normalized_name,
        subject=subject,
        created_by=request.user,
        workspace_scope=workspace_scope,
        organization=organization,
        prefix=prefix,
        secret_hash=secret_hash,
        expires_at=timezone.now() + timedelta(days=expires_in_days),
    )
    APITokenPermission.objects.bulk_create(
        [
            APITokenPermission(tenant=context.tenant, token=record, permission=permission.value)
            for permission in normalized_permissions
        ]
    )
    record.permissions_locked_at = timezone.now()
    record.save(update_fields=("permissions_locked_at",))
    AuditEvent.objects.create(
        tenant=context.tenant,
        actor=request.user,
        action="api_token.created",
        entity_id=record.id,
        request_id=getattr(request, "request_id", None),
        metadata={},
    )
    record = APIToken.scoped.for_tenant(context.tenant).select_related("organization__entity").prefetch_related(
        "permission_rows"
    ).get(pk=record.pk)
    return IssuedAPIToken(record=record, plaintext=plaintext)


def api_tokens_for_request(request: Any) -> models.QuerySet[APIToken]:
    context = require_token_management_browser_session(request)
    records = (
        APIToken.scoped.for_tenant(context.tenant)
        .select_related("organization__entity", "subject")
        .prefetch_related("permission_rows")
    )
    if context_has_permission(context, PermissionKey.INTEGRATIONS_VIEW):
        visible = models.Q(kind=APITokenKind.SERVICE) | models.Q(
            kind=APITokenKind.PERSONAL,
            subject=request.user,
        )
        return records.filter(visible)[:100]
    return records.filter(kind=APITokenKind.PERSONAL, subject=request.user)[:100]


def _managed_token(request, token_id: UUID, *, lock: bool = False) -> APIToken:  # type: ignore[no-untyped-def]
    context = require_installation_member(request.user)
    records = APIToken.scoped.for_tenant(context.tenant).select_related("subject", "organization__entity")
    if lock:
        records = records.select_for_update(of=("self",))
    try:
        record = records.prefetch_related("permission_rows").get(pk=token_id)
    except APIToken.DoesNotExist as exc:
        raise NotFound("The API token is unavailable.") from exc
    if record.kind == APITokenKind.PERSONAL:
        if record.subject_id != request.user.pk:
            raise NotFound("The API token is unavailable.")
    else:
        require_permission(request.user, PermissionKey.INTEGRATIONS_MANAGE)
    return record


@transaction.atomic
def rotate_api_token(*, request, token_id: UUID, expires_in_days: int) -> IssuedAPIToken:  # type: ignore[no-untyped-def]
    require_token_management_session(request)
    record = _managed_token(request, token_id, lock=True)
    if record.revoked_at is not None:
        raise ValidationError({"token": "A revoked token cannot be rotated."})
    prefix, secret_hash, plaintext = _new_material(APITokenKind(record.kind))
    record.prefix = prefix
    record.secret_hash = secret_hash
    record.generation += 1
    record.expires_at = timezone.now() + timedelta(days=expires_in_days)
    record.rotated_at = timezone.now()
    record.last_used_at = None
    record.save(
        update_fields=("prefix", "secret_hash", "generation", "expires_at", "rotated_at", "last_used_at")
    )
    AuditEvent.objects.create(
        tenant=record.tenant,
        actor=request.user,
        action="api_token.rotated",
        entity_id=record.id,
        request_id=getattr(request, "request_id", None),
        metadata={},
    )
    return IssuedAPIToken(record=record, plaintext=plaintext)


@transaction.atomic
def revoke_api_token(*, request, token_id: UUID) -> APIToken:  # type: ignore[no-untyped-def]
    require_token_management_browser_session(request)
    record = _managed_token(request, token_id, lock=True)
    if record.revoked_at is None:
        record.revoked_at = timezone.now()
        record.save(update_fields=("revoked_at",))
        if record.kind == APITokenKind.SERVICE:
            User.objects.filter(pk=record.subject_id, is_service_account=True).update(is_active=False)
        AuditEvent.objects.create(
            tenant=record.tenant,
            actor=request.user,
            action="api_token.revoked",
            entity_id=record.id,
            request_id=getattr(request, "request_id", None),
            metadata={},
        )
    return record


def authenticate_bearer_token(value: str) -> APIToken:
    matched = TOKEN_PATTERN.fullmatch(value)
    if matched is None:
        check_password(value[:128], _DUMMY_SECRET_HASH)
        raise AuthenticationFailed("The API token is invalid or unavailable.")
    marker, prefix, secret = matched.groups()
    record = (
        APIToken.objects.select_related("tenant", "subject", "organization__entity")
        .prefetch_related("permission_rows")
        .filter(prefix=prefix)
        .first()
    )
    secret_hash = record.secret_hash if record is not None else _DUMMY_SECRET_HASH
    verified = check_password(secret, secret_hash)
    expected_marker = "tdp" if record is not None and record.kind == APITokenKind.PERSONAL else "tds"
    now = timezone.now()
    if (
        record is None
        or not verified
        or marker != expected_marker
        or record.revoked_at is not None
        or record.permissions_locked_at is None
        or record.expires_at <= now
        or not record.subject.is_active
    ):
        raise AuthenticationFailed("The API token is invalid or unavailable.")
    if record.last_used_at is None or record.last_used_at <= now - TOKEN_LAST_USED_INTERVAL:
        APIToken.objects.filter(pk=record.pk, tenant=record.tenant).update(last_used_at=now)
        record.last_used_at = now
    return record
