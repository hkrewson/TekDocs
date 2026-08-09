from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .rls_contract import RLS_TABLES


class IsolationBoundary(StrEnum):
    FORCED_RLS = "forced_rls"
    AUTHORIZATION_CONTROL_PLANE = "authorization_control_plane"
    INSTALLATION_SINGLETON = "installation_singleton"


@dataclass(frozen=True, slots=True)
class TenantModelContract:
    table: str
    boundary: IsolationBoundary
    rationale: str


# This inventory is deliberately explicit. A new model carrying a ``tenant``
# foreign key must be assigned to one reviewed boundary before certification
# can pass; model discovery tests reject unclassified additions.
TENANT_MODEL_CONTRACTS = tuple(
    TenantModelContract(table, IsolationBoundary.FORCED_RLS, "Tenant-owned entity-domain data.")
    for table in RLS_TABLES
) + (
    TenantModelContract(
        "accounts_invitation",
        IsolationBoundary.AUTHORIZATION_CONTROL_PLANE,
        "Pre-authentication token redemption must discover its tenant from a digest.",
    ),
    TenantModelContract(
        "accounts_tenantmembership",
        IsolationBoundary.AUTHORIZATION_CONTROL_PLANE,
        "Membership establishes the authenticated tenant and built-in role.",
    ),
    TenantModelContract(
        "accounts_organizationaccessassignment",
        IsolationBoundary.AUTHORIZATION_CONTROL_PLANE,
        "The row establishes organization reachability for assigned-only clients.",
    ),
    TenantModelContract(
        "accounts_accesscollection",
        IsolationBoundary.AUTHORIZATION_CONTROL_PLANE,
        "The row defines an authorization scope rather than client domain data.",
    ),
    TenantModelContract(
        "accounts_accesscollectionorganization",
        IsolationBoundary.AUTHORIZATION_CONTROL_PLANE,
        "The row composes authorization scope before domain data can be selected.",
    ),
    TenantModelContract(
        "accounts_customrole",
        IsolationBoundary.AUTHORIZATION_CONTROL_PLANE,
        "The row defines policy evaluated before domain data can be selected.",
    ),
    TenantModelContract(
        "accounts_customrolepermission",
        IsolationBoundary.AUTHORIZATION_CONTROL_PLANE,
        "The row defines a bounded permission grant.",
    ),
    TenantModelContract(
        "accounts_scopedroleassignment",
        IsolationBoundary.AUTHORIZATION_CONTROL_PLANE,
        "The row composes member, role, and tenant/organization/collection scope.",
    ),
    TenantModelContract(
        "core_installationstate",
        IsolationBoundary.INSTALLATION_SINGLETON,
        "The migration-created singleton anchors bootstrap and tenant discovery.",
    ),
)

AUTHORIZATION_CONTROL_PLANE_TABLES = tuple(
    contract.table
    for contract in TENANT_MODEL_CONTRACTS
    if contract.boundary == IsolationBoundary.AUTHORIZATION_CONTROL_PLANE
)

CONTROL_PLANE_GUARD_TRIGGERS = (
    "accounts_tenant_membership_guard",
    "accounts_invitation_scope_guard",
    "accounts_organization_access_assignment_actor_guard",
    "accounts_custom_role_creator_guard",
    "accounts_access_collection_creator_guard",
)
