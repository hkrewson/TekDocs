from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404

from apps.accounts.models import User
from apps.accounts.policy import (
    InstallationMemberContext,
    PermissionKey,
    accessible_organizations,
    context_has_permission,
    require_permission,
)

from .models import Organization
from .scoping import DataScope

MSP_CAPABILITIES = (
    "overview",
    "organizations",
    "people",
    "sites",
    "custom_fields",
    "documentation",
    "files",
    "assets",
    "licenses",
    "networks",
    "domains",
    "certificates",
    "credentials",
    "services",
    "tickets",
    "vendors",
    "products",
    "compliance",
    "activity",
    "integrations",
    "accounting",
)

CLASSIFICATION_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "client": (
        "overview",
        "people",
        "sites",
        "custom_fields",
        "documentation",
        "files",
        "assets",
        "licenses",
        "networks",
        "domains",
        "certificates",
        "credentials",
        "services",
        "tickets",
        "vendors",
    ),
    "vendor": ("overview", "people", "sites", "custom_fields", "documentation", "files", "products"),
    "manufacturer": ("overview", "people", "sites", "custom_fields", "documentation", "files", "products"),
    "partner": ("overview", "people", "sites", "custom_fields", "documentation", "files", "products"),
}

CAPABILITY_PERMISSIONS: dict[str, PermissionKey] = {
    "overview": PermissionKey.WORKSPACES_VIEW,
    "organizations": PermissionKey.ORGANIZATIONS_VIEW,
    "people": PermissionKey.PEOPLE_VIEW,
    "sites": PermissionKey.SITES_VIEW,
    "custom_fields": PermissionKey.CUSTOM_FIELDS_VIEW,
    "documentation": PermissionKey.DOCUMENTS_VIEW,
    "files": PermissionKey.DOCUMENTS_VIEW,
    "assets": PermissionKey.ASSETS_VIEW,
    "licenses": PermissionKey.ASSETS_VIEW,
    "networks": PermissionKey.NETWORKS_VIEW,
    "domains": PermissionKey.NETWORKS_VIEW,
    "certificates": PermissionKey.NETWORKS_VIEW,
    "credentials": PermissionKey.SECRETS_VIEW,
    "services": PermissionKey.WORKSPACES_VIEW,
    "tickets": PermissionKey.WORKSPACES_VIEW,
    "vendors": PermissionKey.ASSETS_VIEW,
    "products": PermissionKey.ASSETS_VIEW,
    "compliance": PermissionKey.COMPLIANCE_VIEW,
    "activity": PermissionKey.WORKSPACES_VIEW,
    "integrations": PermissionKey.INTEGRATIONS_VIEW,
    "accounting": PermissionKey.COSTS_VIEW,
}


def capabilities_for_classifications(classifications: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            capability
            for classification in classifications
            for capability in CLASSIFICATION_CAPABILITIES[classification]
        )
    )


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
    return accessible_organizations(member).select_related("entity", "tenant").prefetch_related("classifications")


def authorized_capabilities(
    member: InstallationMemberContext,
    capabilities: tuple[str, ...],
    *,
    organization: Organization | None = None,
) -> tuple[str, ...]:
    return tuple(
        capability
        for capability in capabilities
        if context_has_permission(member, CAPABILITY_PERMISSIONS[capability], organization=organization)
    )


def search_organization_workspaces(
    user: User,
    *,
    query: str,
    classification: str,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, object]], bool]:
    member = require_permission(user, PermissionKey.ORGANIZATIONS_VIEW)
    organizations = active_organizations_for_member(member)
    if classification:
        organizations = organizations.filter(classifications__kind=classification)
    if query:
        organizations = organizations.filter(Q(entity__display_name__icontains=query) | Q(legal_name__icontains=query))
    organizations = organizations.order_by("entity__display_name", "entity_id")
    offset = (page - 1) * page_size
    selected = list(organizations[offset : offset + page_size + 1])
    results = []
    for organization in selected[:page_size]:
        classifications = tuple(sorted(item.kind for item in organization.classifications.all()))
        results.append(
            {
                "id": organization.entity_id,
                "name": organization.entity.display_name,
                "classifications": list(classifications),
                "capabilities": list(capabilities_for_classifications(classifications)),
            }
        )
    return results, len(selected) > page_size


def resolve_msp_workspace(user: User) -> ResolvedWorkspace:
    member = require_permission(user, PermissionKey.WORKSPACES_VIEW)
    return ResolvedWorkspace(
        member=member,
        kind="msp",
        id=member.tenant.id,
        name=member.tenant.name,
        data_scope=DataScope.tenant(member.tenant),
        classifications=(),
        capabilities=authorized_capabilities(member, MSP_CAPABILITIES),
    )


def resolve_organization_workspace(user: User, *, entity_id: UUID) -> ResolvedWorkspace:
    member = require_permission(user, PermissionKey.WORKSPACES_VIEW)
    organization = get_object_or_404(active_organizations_for_member(member), entity_id=entity_id)
    classifications = tuple(sorted(classification.kind for classification in organization.classifications.all()))
    capabilities = authorized_capabilities(
        member,
        capabilities_for_classifications(classifications),
        organization=organization,
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
