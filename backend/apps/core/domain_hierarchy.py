from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction

from .domains import DomainError, normalize_domain_name
from .models import (
    DomainDNSObservation,
    Entity,
    EntityVisibility,
    HostnameProvenance,
    ManagedHostname,
    RegisteredDomain,
)
from .workspaces import ResolvedWorkspace

DNS_TYPES = frozenset({"A", "AAAA", "CNAME", "MX", "NS", "TXT", "CAA", "SRV"})


@dataclass(frozen=True, slots=True)
class HostnameInput:
    name: str
    provenance: str
    source: str = ""
    parent_id: UUID | None = None


def domain_for_workspace(workspace: ResolvedWorkspace, domain_id: UUID) -> RegisteredDomain:
    try:
        return RegisteredDomain.scoped.for_scope(workspace.data_scope).get(
            entity_id=domain_id, archived_at__isnull=True
        )
    except RegisteredDomain.DoesNotExist as exc:
        raise DomainError("The selected domain is unavailable in this workspace.") from exc


def hostnames_for_domain(domain: RegisteredDomain):  # type: ignore[no-untyped-def]
    return ManagedHostname.objects.filter(domain=domain, archived_at__isnull=True).select_related(
        "entity", "parent__entity"
    )


@transaction.atomic
def create_hostname(
    *, workspace: ResolvedWorkspace, domain: RegisteredDomain, actor_id: UUID, value: HostnameInput
) -> ManagedHostname:
    name = normalize_domain_name(value.name)
    if name == domain.ascii_name or not name.endswith(f".{domain.ascii_name}"):
        raise DomainError("A managed hostname must be below its registered domain.")
    if value.provenance not in HostnameProvenance.values:
        raise DomainError("Unknown hostname provenance.")
    parent = None
    if value.parent_id:
        try:
            parent = hostnames_for_domain(domain).get(entity_id=value.parent_id)
        except ManagedHostname.DoesNotExist as exc:
            raise DomainError("The selected parent hostname is unavailable.") from exc
        if parent.ascii_name == name or not name.endswith(f".{parent.ascii_name}"):
            raise DomainError("The parent must be an ancestor of the hostname.")
    entity = Entity.objects.create(
        tenant=domain.tenant,
        workspace=domain.workspace,
        organization=domain.organization,
        entity_type="managed_hostname",
        display_name=name,
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    return ManagedHostname.objects.create(
        tenant=domain.tenant,
        workspace=domain.workspace,
        organization=domain.organization,
        entity=entity,
        domain=domain,
        parent=parent,
        ascii_name=name,
        provenance=value.provenance,
        source=value.source,
        created_by_id=actor_id,
    )


@transaction.atomic
def record_dns_observation(
    *,
    hostname: ManagedHostname,
    actor_id: UUID | None,
    record_type: str,
    value: str,
    ttl: int | None,
    provenance: str,
    source: str,
    observed_at: datetime,
) -> DomainDNSObservation:
    kind = record_type.upper()
    normalized_value = value.strip()
    if kind not in DNS_TYPES or not normalized_value or len(normalized_value) > 1_024:
        raise DomainError("The DNS observation is invalid.")
    if provenance not in HostnameProvenance.values or not source.strip():
        raise DomainError("DNS observations require explicit provenance and source.")
    digest = hashlib.sha256(f"{kind}\0{normalized_value}\0{ttl or ''}".encode()).hexdigest()
    return DomainDNSObservation.objects.create(
        tenant=hostname.tenant,
        workspace=hostname.workspace,
        organization=hostname.organization,
        domain=hostname.domain,
        hostname=hostname,
        record_type=kind,
        value=normalized_value,
        ttl=ttl,
        provenance=provenance,
        source=source.strip(),
        content_digest=digest,
        observed_at=observed_at,
        recorded_by_id=actor_id,
    )
