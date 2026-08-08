from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from apps.accounts.models import User
from apps.accounts.policy import InstallationMemberContext, require_installation_member, require_installation_owner

from .models import Organization
from .scoping import DataScope

MSP_CAPABILITIES = (
    "overview",
    "documentation",
    "organizations",
    "people",
    "assets",
    "networks",
    "credentials",
    "compliance",
    "activity",
)

CLASSIFICATION_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "client": ("overview", "documentation", "people", "assets", "networks", "credentials"),
    "vendor": ("overview", "documentation", "people", "products"),
    "manufacturer": ("overview", "documentation", "people", "products"),
    "partner": ("overview", "documentation", "people", "products"),
}


@dataclass(frozen=True, slots=True)
class ResolvedWorkspace:
    member: InstallationMemberContext
    kind: str
    id: UUID
    name: str
    data_scope: DataScope
    classifications: tuple[str, ...]
    capabilities: tuple[str, ...]
    organization: Organization | None = None

    def as_response_data(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "classifications": list(self.classifications),
            "capabilities": list(self.capabilities),
            "organization": self.organization,
        }


def active_organizations_for_member(member: InstallationMemberContext) -> QuerySet[Organization]:
    return (
        Organization.scoped.for_tenant(member.tenant)
        .filter(entity__archived_at__isnull=True)
        .select_related("entity", "tenant")
        .prefetch_related("classifications")
    )


def resolve_msp_workspace(user: User) -> ResolvedWorkspace:
    member = require_installation_member(user)
    return ResolvedWorkspace(
        member=member,
        kind="msp",
        id=member.tenant.id,
        name=member.tenant.name,
        data_scope=DataScope.tenant(member.tenant),
        classifications=(),
        capabilities=MSP_CAPABILITIES,
    )


def resolve_organization_workspace(user: User, *, entity_id: UUID) -> ResolvedWorkspace:
    member = require_installation_owner(user)
    organization = get_object_or_404(active_organizations_for_member(member), entity_id=entity_id)
    classifications = tuple(sorted(classification.kind for classification in organization.classifications.all()))
    capabilities = tuple(
        dict.fromkeys(
            capability
            for classification in classifications
            for capability in CLASSIFICATION_CAPABILITIES[classification]
        )
    )
    return ResolvedWorkspace(
        member=member,
        kind="organization",
        id=organization.entity_id,
        name=organization.entity.display_name,
        data_scope=DataScope.organization(member.tenant, organization),
        classifications=classifications,
        capabilities=capabilities,
        organization=organization,
    )
