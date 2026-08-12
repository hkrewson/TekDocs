from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from django.db import transaction

from apps.accounts.models import TenantMembership
from apps.accounts.policy import PermissionKey, context_has_permission, require_installation_member

from .models import (
    AuditEvent,
    DomainRenewalMode,
    Entity,
    EntityVisibility,
    Organization,
    RegisteredDomain,
    RegisteredDomainStatus,
)
from .workspaces import ResolvedWorkspace


class DomainError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DomainInput:
    name: str
    renewal_mode: str
    status: str
    registrar_id: UUID | None = None
    registration_date: date | None = None
    expiration_date: date | None = None
    owner_id: UUID | None = None
    notes: str = ""


def normalize_domain_name(value: str) -> str:
    candidate = value.strip().rstrip(".").lower()
    if not candidate or len(candidate) > 253 or "." not in candidate:
        raise DomainError("Enter a registrable domain name.")
    try:
        ascii_name = candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise DomainError("The domain name is invalid.") from exc
    labels = ascii_name.split(".")
    if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in labels):
        raise DomainError("The domain name is invalid.")
    if any(not label.replace("-", "").isalnum() for label in labels):
        raise DomainError("The domain name is invalid.")
    return ascii_name


def domains_for_scope(workspace: ResolvedWorkspace):  # type: ignore[no-untyped-def]
    return (
        RegisteredDomain.scoped.for_scope(workspace.data_scope)
        .filter(archived_at__isnull=True)
        .select_related("entity", "registrar__entity", "owner", "created_by")
    )


def _registrar(workspace: ResolvedWorkspace, registrar_id: UUID | None):  # type: ignore[no-untyped-def]
    if registrar_id is None:
        return None
    try:
        return (
            Organization.scoped.for_tenant(workspace.member.tenant)
            .filter(classifications__classification__in=("vendor", "partner"))
            .distinct()
            .get(entity_id=registrar_id, entity__archived_at__isnull=True)
        )
    except Organization.DoesNotExist as exc:
        raise DomainError("The selected registrar is unavailable.") from exc


def _owner(workspace: ResolvedWorkspace, owner_id: UUID | None):  # type: ignore[no-untyped-def]
    if owner_id is None:
        return None
    try:
        membership = TenantMembership.objects.select_related("user").get(
            tenant=workspace.member.tenant, user_id=owner_id, user__is_active=True
        )
    except TenantMembership.DoesNotExist as exc:
        raise DomainError("The selected owner is unavailable.") from exc
    if not context_has_permission(
        require_installation_member(membership.user), PermissionKey.DOMAINS_VIEW, organization=workspace.organization
    ):
        raise DomainError("The selected owner cannot access this domain workspace.")
    return membership.user


def _validated(workspace: ResolvedWorkspace, value: DomainInput):  # type: ignore[no-untyped-def]
    if value.renewal_mode not in DomainRenewalMode.values or value.status not in RegisteredDomainStatus.values:
        raise DomainError("Unknown domain lifecycle value.")
    if value.registration_date and value.expiration_date and value.expiration_date < value.registration_date:
        raise DomainError("Expiration cannot precede registration.")
    return (
        normalize_domain_name(value.name),
        _registrar(workspace, value.registrar_id),
        _owner(workspace, value.owner_id),
    )


@transaction.atomic
def create_domain(*, workspace: ResolvedWorkspace, actor_id: UUID, value: DomainInput) -> RegisteredDomain:
    ascii_name, registrar, owner = _validated(workspace, value)
    entity = Entity.objects.create(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        entity_type="registered_domain",
        display_name=ascii_name,
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    domain = RegisteredDomain.objects.create(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        entity=entity,
        ascii_name=ascii_name,
        registrar=registrar,
        registration_date=value.registration_date,
        expiration_date=value.expiration_date,
        renewal_mode=value.renewal_mode,
        owner=owner,
        status=value.status,
        notes=value.notes,
        created_by_id=actor_id,
    )
    AuditEvent.objects.create(
        tenant=domain.tenant,
        actor_id=actor_id,
        action="domain.created",
        entity_id=entity.id,
        metadata={"renewal_mode": domain.renewal_mode, "status": domain.status},
    )
    return domain
