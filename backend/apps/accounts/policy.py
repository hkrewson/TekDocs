from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from allauth.mfa.models import Authenticator
from django.db.models import Q, QuerySet
from rest_framework.exceptions import APIException, PermissionDenied

from apps.core.models import Entity, EntityVisibility, InstallationState, Organization, OrganizationAccessMode, Tenant
from apps.core.scoping import DataScope

from .models import (
    TENANT_ASSIGNABLE_ROLES,
    BuiltInRole,
    OrganizationAccessAssignment,
    ScopedRoleAssignment,
    TenantMembership,
    User,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


class InstallationContextUnavailable(APIException):
    status_code = 503
    default_detail = "The authenticated installation context is unavailable."
    default_code = "authentication_context_unavailable"


class PrivilegedMFARequired(PermissionDenied):
    default_detail = "Two-factor authentication is required for this privileged action."
    default_code = "privileged_mfa_required"


class PermissionKey(StrEnum):
    INSTALLATION_MANAGE = "installation.manage"
    WORKSPACES_VIEW = "workspaces.view"
    ORGANIZATIONS_VIEW = "organizations.view"
    ORGANIZATIONS_CREATE = "organizations.create"
    ORGANIZATIONS_EDIT = "organizations.edit"
    ORGANIZATIONS_ARCHIVE = "organizations.archive"
    ORGANIZATIONS_MANAGE_ACCESS = "organizations.manage_access"
    ORGANIZATIONS_ASSIGN_STAFF = "organizations.assign_staff"
    PEOPLE_VIEW = "people.view"
    PEOPLE_CREATE = "people.create"
    PEOPLE_EDIT = "people.edit"
    PEOPLE_ARCHIVE = "people.archive"
    SITES_VIEW = "sites.view"
    SITES_CREATE = "sites.create"
    SITES_EDIT = "sites.edit"
    SITES_ARCHIVE = "sites.archive"
    CUSTOM_FIELDS_VIEW = "custom_fields.view"
    CUSTOM_FIELDS_MANAGE = "custom_fields.manage"
    CUSTOM_FIELDS_EDIT_VALUES = "custom_fields.edit_values"
    RELATIONSHIPS_VIEW = "relationships.view"
    RELATIONSHIPS_CREATE = "relationships.create"
    RELATIONSHIPS_ARCHIVE = "relationships.archive"
    INVITATIONS_VIEW = "invitations.view"
    INVITATIONS_CREATE = "invitations.create"
    INVITATIONS_REVOKE = "invitations.revoke"
    INVITATIONS_RESEND = "invitations.resend"
    STAFF_INVITATIONS_VIEW = "staff_invitations.view"
    STAFF_INVITATIONS_CREATE = "staff_invitations.create"
    STAFF_INVITATIONS_REVOKE = "staff_invitations.revoke"
    STAFF_INVITATIONS_RESEND = "staff_invitations.resend"
    MEMBERSHIPS_VIEW = "memberships.view"
    MEMBERSHIPS_ASSIGN_ROLE = "memberships.assign_role"
    CUSTOM_ROLES_VIEW = "custom_roles.view"
    CUSTOM_ROLES_MANAGE = "custom_roles.manage"
    CUSTOM_ROLES_ASSIGN = "custom_roles.assign"
    ACCESS_COLLECTIONS_VIEW = "access_collections.view"
    ACCESS_COLLECTIONS_MANAGE = "access_collections.manage"
    RECYCLE_BIN_VIEW = "recycle_bin.view"
    RECYCLE_BIN_RESTORE = "recycle_bin.restore"
    DOCUMENTS_VIEW = "documents.view"
    DOCUMENTS_EDIT = "documents.edit"
    DOCUMENTS_PUBLISH = "documents.publish"
    DOCUMENTS_APPROVE = "documents.approve"
    DOCUMENTS_WITHDRAW = "documents.withdraw"
    ASSETS_VIEW = "assets.view"
    ASSETS_EDIT = "assets.edit"
    NETWORKS_VIEW = "networks.view"
    NETWORKS_EDIT = "networks.edit"
    COSTS_VIEW = "costs.view"
    INVOICES_VIEW = "invoices.view"
    INVOICES_EDIT = "invoices.edit"
    CREDENTIAL_REFERENCES_VIEW = "credential_references.view"
    CREDENTIAL_REFERENCES_MANAGE = "credential_references.manage"
    CREDENTIAL_REFERENCES_OPEN = "credential_references.open"
    COMPLIANCE_VIEW = "compliance.view"
    COMPLIANCE_EDIT = "compliance.edit"
    DATA_FLOWS_VIEW = "data_flows.view"
    DATA_FLOWS_EDIT = "data_flows.edit"
    DEADLINES_VIEW = "deadlines.view"
    DEADLINES_EDIT = "deadlines.edit"
    DOMAINS_VIEW = "domains.view"
    DOMAINS_EDIT = "domains.edit"
    INTEGRATIONS_VIEW = "integrations.view"
    INTEGRATIONS_MANAGE = "integrations.manage"
    NOTIFICATIONS_MANAGE = "notifications.manage"
    ACTIVITY_VIEW = "activity.view"


@dataclass(frozen=True, slots=True)
class PermissionDefinition:
    key: PermissionKey
    label: str
    category: str
    requires_mfa: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key.value,
            "label": self.label,
            "category": self.category,
            "requires_mfa": self.requires_mfa,
        }


def _permission(key: PermissionKey, label: str, category: str, *, mfa: bool = False) -> PermissionDefinition:
    return PermissionDefinition(key=key, label=label, category=category, requires_mfa=mfa)


PERMISSION_CATALOG = (
    _permission(PermissionKey.INSTALLATION_MANAGE, "Manage installation ownership", "Administration", mfa=True),
    _permission(PermissionKey.WORKSPACES_VIEW, "Open MSP and authorized organization workspaces", "Workspaces"),
    _permission(PermissionKey.ORGANIZATIONS_VIEW, "View organizations", "Organizations"),
    _permission(PermissionKey.ORGANIZATIONS_CREATE, "Create organizations", "Organizations", mfa=True),
    _permission(PermissionKey.ORGANIZATIONS_EDIT, "Edit organizations", "Organizations", mfa=True),
    _permission(PermissionKey.ORGANIZATIONS_ARCHIVE, "Archive organizations", "Organizations", mfa=True),
    _permission(
        PermissionKey.ORGANIZATIONS_MANAGE_ACCESS, "Manage organization access modes", "Organizations", mfa=True
    ),
    _permission(
        PermissionKey.ORGANIZATIONS_ASSIGN_STAFF,
        "Assign MSP staff to organizations",
        "Organizations",
        mfa=True,
    ),
    _permission(PermissionKey.PEOPLE_VIEW, "View people", "People"),
    _permission(PermissionKey.PEOPLE_CREATE, "Create people", "People", mfa=True),
    _permission(PermissionKey.PEOPLE_EDIT, "Edit people", "People", mfa=True),
    _permission(PermissionKey.PEOPLE_ARCHIVE, "Archive people", "People", mfa=True),
    _permission(PermissionKey.SITES_VIEW, "View sites and locations", "Sites"),
    _permission(PermissionKey.SITES_CREATE, "Create sites and locations", "Sites", mfa=True),
    _permission(PermissionKey.SITES_EDIT, "Edit sites and locations", "Sites", mfa=True),
    _permission(PermissionKey.SITES_ARCHIVE, "Archive sites and locations", "Sites", mfa=True),
    _permission(PermissionKey.CUSTOM_FIELDS_VIEW, "View custom fields", "Custom fields"),
    _permission(PermissionKey.CUSTOM_FIELDS_MANAGE, "Manage custom-field definitions", "Custom fields", mfa=True),
    _permission(PermissionKey.CUSTOM_FIELDS_EDIT_VALUES, "Edit custom-field values", "Custom fields", mfa=True),
    _permission(PermissionKey.RELATIONSHIPS_VIEW, "View entity relationships", "Relationships"),
    _permission(PermissionKey.RELATIONSHIPS_CREATE, "Create entity relationships", "Relationships", mfa=True),
    _permission(PermissionKey.RELATIONSHIPS_ARCHIVE, "Archive entity relationships", "Relationships", mfa=True),
    _permission(PermissionKey.INVITATIONS_VIEW, "View invitations", "Administration"),
    _permission(PermissionKey.INVITATIONS_CREATE, "Issue invitations", "Administration", mfa=True),
    _permission(PermissionKey.INVITATIONS_REVOKE, "Revoke invitations", "Administration", mfa=True),
    _permission(PermissionKey.INVITATIONS_RESEND, "Resend invitations", "Administration", mfa=True),
    _permission(PermissionKey.STAFF_INVITATIONS_VIEW, "View MSP staff invitations", "Administration"),
    _permission(PermissionKey.STAFF_INVITATIONS_CREATE, "Issue MSP staff invitations", "Administration", mfa=True),
    _permission(PermissionKey.STAFF_INVITATIONS_REVOKE, "Revoke MSP staff invitations", "Administration", mfa=True),
    _permission(PermissionKey.STAFF_INVITATIONS_RESEND, "Resend MSP staff invitations", "Administration", mfa=True),
    _permission(PermissionKey.MEMBERSHIPS_VIEW, "View tenant members and built-in roles", "Administration"),
    _permission(PermissionKey.MEMBERSHIPS_ASSIGN_ROLE, "Assign tenant member roles", "Administration", mfa=True),
    _permission(PermissionKey.CUSTOM_ROLES_VIEW, "View custom roles and assignments", "Administration"),
    _permission(PermissionKey.CUSTOM_ROLES_MANAGE, "Manage custom role definitions", "Administration", mfa=True),
    _permission(PermissionKey.CUSTOM_ROLES_ASSIGN, "Assign custom roles", "Administration", mfa=True),
    _permission(PermissionKey.ACCESS_COLLECTIONS_VIEW, "View access collections", "Administration"),
    _permission(PermissionKey.ACCESS_COLLECTIONS_MANAGE, "Manage access collections", "Administration", mfa=True),
    _permission(PermissionKey.RECYCLE_BIN_VIEW, "View archived records", "Recovery"),
    _permission(PermissionKey.RECYCLE_BIN_RESTORE, "Restore archived records", "Recovery", mfa=True),
    _permission(PermissionKey.DOCUMENTS_VIEW, "View documentation", "Documentation"),
    _permission(PermissionKey.DOCUMENTS_EDIT, "Edit documentation", "Documentation", mfa=True),
    _permission(PermissionKey.DOCUMENTS_PUBLISH, "Publish documentation", "Documentation", mfa=True),
    _permission(PermissionKey.DOCUMENTS_APPROVE, "Approve client-visible documentation", "Documentation", mfa=True),
    _permission(PermissionKey.DOCUMENTS_WITHDRAW, "Withdraw published documentation", "Documentation", mfa=True),
    _permission(PermissionKey.ASSETS_VIEW, "View assets", "Assets"),
    _permission(PermissionKey.ASSETS_EDIT, "Edit assets", "Assets", mfa=True),
    _permission(PermissionKey.NETWORKS_VIEW, "View networks", "Networks"),
    _permission(PermissionKey.NETWORKS_EDIT, "Edit networks", "Networks", mfa=True),
    _permission(PermissionKey.COSTS_VIEW, "View costs", "Sensitive data"),
    _permission(PermissionKey.INVOICES_VIEW, "View invoice drafts", "Accounting"),
    _permission(PermissionKey.INVOICES_EDIT, "Edit invoice drafts", "Accounting", mfa=True),
    _permission(PermissionKey.CREDENTIAL_REFERENCES_VIEW, "View credential references", "Credential references"),
    _permission(
        PermissionKey.CREDENTIAL_REFERENCES_MANAGE,
        "Manage credential references",
        "Credential references",
        mfa=True,
    ),
    _permission(PermissionKey.CREDENTIAL_REFERENCES_OPEN, "Open credential references", "Credential references"),
    _permission(PermissionKey.COMPLIANCE_VIEW, "View compliance evidence", "Compliance"),
    _permission(PermissionKey.COMPLIANCE_EDIT, "Edit compliance evidence", "Compliance", mfa=True),
    _permission(PermissionKey.DATA_FLOWS_VIEW, "View data flows", "Compliance"),
    _permission(PermissionKey.DATA_FLOWS_EDIT, "Edit data flows", "Compliance", mfa=True),
    _permission(PermissionKey.DEADLINES_VIEW, "View deadline schedules", "Deadlines"),
    _permission(PermissionKey.DEADLINES_EDIT, "Manage deadline schedules", "Deadlines", mfa=True),
    _permission(PermissionKey.DOMAINS_VIEW, "View domains", "Domains"),
    _permission(PermissionKey.DOMAINS_EDIT, "Manage domains", "Domains", mfa=True),
    _permission(PermissionKey.INTEGRATIONS_VIEW, "View integrations", "Integrations"),
    _permission(PermissionKey.INTEGRATIONS_MANAGE, "Manage integrations", "Integrations", mfa=True),
    _permission(PermissionKey.NOTIFICATIONS_MANAGE, "Manage notification delivery", "Administration", mfa=True),
    _permission(PermissionKey.ACTIVITY_VIEW, "View audit activity", "Governance"),
)
PERMISSION_BY_KEY = {definition.key: definition for definition in PERMISSION_CATALOG}

IMPLEMENTED_READS = frozenset(
    {
        PermissionKey.WORKSPACES_VIEW,
        PermissionKey.ORGANIZATIONS_VIEW,
        PermissionKey.PEOPLE_VIEW,
        PermissionKey.SITES_VIEW,
        PermissionKey.CUSTOM_FIELDS_VIEW,
        PermissionKey.RELATIONSHIPS_VIEW,
        PermissionKey.RECYCLE_BIN_VIEW,
        PermissionKey.DOCUMENTS_VIEW,
        PermissionKey.ASSETS_VIEW,
        PermissionKey.NETWORKS_VIEW,
        PermissionKey.COMPLIANCE_VIEW,
        PermissionKey.DATA_FLOWS_VIEW,
        PermissionKey.DEADLINES_VIEW,
        PermissionKey.DOMAINS_VIEW,
        PermissionKey.INTEGRATIONS_VIEW,
        PermissionKey.INVOICES_VIEW,
    }
)
TECHNICIAN_MUTATIONS = frozenset(
    {
        PermissionKey.PEOPLE_CREATE,
        PermissionKey.PEOPLE_EDIT,
        PermissionKey.PEOPLE_ARCHIVE,
        PermissionKey.SITES_CREATE,
        PermissionKey.SITES_EDIT,
        PermissionKey.SITES_ARCHIVE,
        PermissionKey.CUSTOM_FIELDS_EDIT_VALUES,
        PermissionKey.RELATIONSHIPS_CREATE,
        PermissionKey.RELATIONSHIPS_ARCHIVE,
        PermissionKey.RECYCLE_BIN_RESTORE,
        PermissionKey.DOCUMENTS_EDIT,
        PermissionKey.CREDENTIAL_REFERENCES_MANAGE,
        PermissionKey.ASSETS_EDIT,
        PermissionKey.NETWORKS_EDIT,
        PermissionKey.COMPLIANCE_EDIT,
        PermissionKey.DATA_FLOWS_EDIT,
        PermissionKey.DEADLINES_EDIT,
        PermissionKey.DOMAINS_EDIT,
    }
)
ADMINISTRATOR_PERMISSIONS = frozenset(
    definition.key
    for definition in PERMISSION_CATALOG
    if definition.key
    not in {
        PermissionKey.INSTALLATION_MANAGE,
        PermissionKey.STAFF_INVITATIONS_VIEW,
        PermissionKey.STAFF_INVITATIONS_CREATE,
        PermissionKey.STAFF_INVITATIONS_REVOKE,
        PermissionKey.STAFF_INVITATIONS_RESEND,
        PermissionKey.MEMBERSHIPS_ASSIGN_ROLE,
        PermissionKey.CUSTOM_ROLES_MANAGE,
        PermissionKey.CUSTOM_ROLES_ASSIGN,
        PermissionKey.ACCESS_COLLECTIONS_MANAGE,
        PermissionKey.ORGANIZATIONS_ASSIGN_STAFF,
        PermissionKey.ORGANIZATIONS_MANAGE_ACCESS,
    }
)

# This explicit allowlist is the privilege ceiling for custom roles. Sensitive
# field policy deliberately permits only cost visibility; access-control and
# credential-reference grants stay provider-neutral and never authorize secret retrieval.
CUSTOM_ROLE_ASSIGNABLE_PERMISSIONS = frozenset(
    IMPLEMENTED_READS
    | TECHNICIAN_MUTATIONS
    | {
        PermissionKey.ORGANIZATIONS_CREATE,
        PermissionKey.ORGANIZATIONS_EDIT,
        PermissionKey.ORGANIZATIONS_ARCHIVE,
        PermissionKey.CUSTOM_FIELDS_MANAGE,
        PermissionKey.DOCUMENTS_PUBLISH,
        PermissionKey.DOCUMENTS_APPROVE,
        PermissionKey.DOCUMENTS_WITHDRAW,
        PermissionKey.COSTS_VIEW,
        PermissionKey.INVOICES_EDIT,
        PermissionKey.CREDENTIAL_REFERENCES_VIEW,
        PermissionKey.CREDENTIAL_REFERENCES_MANAGE,
        PermissionKey.CREDENTIAL_REFERENCES_OPEN,
        PermissionKey.ACTIVITY_VIEW,
    }
)


class DataAudience(StrEnum):
    MSP_STAFF = "msp_staff"
    CLIENT_PORTAL = "client_portal"


class SensitiveField(StrEnum):
    COST = "cost"


SENSITIVE_FIELD_PERMISSIONS = {
    SensitiveField.COST: PermissionKey.COSTS_VIEW,
}


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    value: BuiltInRole
    label: str
    description: str
    assignable_scope: str
    permissions: frozenset[PermissionKey]

    def as_dict(self) -> dict[str, object]:
        return {
            "value": self.value.value,
            "label": self.label,
            "description": self.description,
            "assignable_scope": self.assignable_scope,
            "permissions": sorted(permission.value for permission in self.permissions),
        }


ROLE_DEFINITIONS = (
    RoleDefinition(
        BuiltInRole.OWNER,
        "Owner",
        "Immutable installation owner with every permission.",
        "installation",
        frozenset(PermissionKey),
    ),
    RoleDefinition(
        BuiltInRole.ADMINISTRATOR,
        "Administrator",
        "Tenant-wide administration except ownership, role assignment, and secret reveal.",
        "tenant",
        ADMINISTRATOR_PERMISSIONS,
    ),
    RoleDefinition(
        BuiltInRole.TECHNICIAN,
        "Technician",
        "Operational read and change access across authorized MSP and client workspaces.",
        "tenant",
        IMPLEMENTED_READS
        | TECHNICIAN_MUTATIONS
        | {PermissionKey.CREDENTIAL_REFERENCES_VIEW, PermissionKey.CREDENTIAL_REFERENCES_OPEN},
    ),
    RoleDefinition(
        BuiltInRole.CONTRIBUTOR,
        "Contributor",
        "Read access plus documentation contribution in authorized workspaces.",
        "tenant",
        IMPLEMENTED_READS | {PermissionKey.DOCUMENTS_EDIT},
    ),
    RoleDefinition(
        BuiltInRole.READ_ONLY,
        "Read-only",
        "Read access to non-secret operational records in authorized workspaces.",
        "tenant",
        IMPLEMENTED_READS,
    ),
    RoleDefinition(
        BuiltInRole.CLIENT_ADMINISTRATOR,
        "Client Administrator",
        "Future organization-scoped client administration role.",
        "organization",
        IMPLEMENTED_READS | {PermissionKey.DOCUMENTS_EDIT},
    ),
    RoleDefinition(
        BuiltInRole.CLIENT_USER,
        "Client User",
        "Future organization-scoped client reader role.",
        "organization",
        frozenset({PermissionKey.WORKSPACES_VIEW, PermissionKey.DOCUMENTS_VIEW}),
    ),
)
ROLE_BY_VALUE = {definition.value: definition for definition in ROLE_DEFINITIONS}


@dataclass(frozen=True)
class InstallationMemberContext:
    state: InstallationState
    tenant: Tenant
    user: User
    role: BuiltInRole
    is_owner: bool
    membership_id: UUID | None = None
    organization: Organization | None = None

    @property
    def surface(self) -> str:
        return "client_portal" if self.role in {BuiltInRole.CLIENT_ADMINISTRATOR, BuiltInRole.CLIENT_USER} else "msp"

    @property
    def data_scope(self) -> DataScope:
        return DataScope.tenant(self.tenant)

    @property
    def permissions(self) -> frozenset[PermissionKey]:
        permissions = ROLE_BY_VALUE[self.role].permissions
        token = getattr(self.user, "tekdocs_api_token", None)
        if token is None:
            return permissions
        token_permissions = {
            PermissionKey(row.permission)
            for row in token.permission_rows.all()
            if row.permission in PermissionKey._value2member_map_
        }
        return permissions & token_permissions


def permission_catalog() -> list[dict[str, object]]:
    return [definition.as_dict() for definition in PERMISSION_CATALOG]


def role_catalog() -> list[dict[str, object]]:
    return [definition.as_dict() for definition in ROLE_DEFINITIONS]


def require_installation_member(user: User) -> InstallationMemberContext:
    if not user.is_authenticated:
        raise PermissionDenied("Authentication is required.")
    try:
        state = InstallationState.objects.select_related("tenant", "owner").get(
            pk=InstallationState.SINGLETON_ID,
            bootstrapped_at__isnull=False,
        )
    except InstallationState.DoesNotExist as exc:
        raise InstallationContextUnavailable() from exc
    if state.tenant is None:
        raise InstallationContextUnavailable()
    is_owner = state.owner_id == user.pk
    if is_owner:
        return InstallationMemberContext(
            state=state, tenant=state.tenant, user=user, role=BuiltInRole.OWNER, is_owner=True, membership_id=None
        )
    membership = (
        TenantMembership.scoped.for_tenant(state.tenant)
        .select_related("organization", "organization__entity")
        .filter(user=user)
        .first()
    )
    if membership is None:
        raise PermissionDenied("Installation membership is required.")
    return InstallationMemberContext(
        state=state,
        tenant=state.tenant,
        user=user,
        role=BuiltInRole(membership.role),
        is_owner=False,
        membership_id=membership.id,
        organization=membership.organization,
    )


def _organization_allowed(context: InstallationMemberContext, organization: Organization) -> bool:
    if organization.tenant_id != context.tenant.id or organization.entity.archived_at is not None:
        return False
    if context.surface == "client_portal":
        return context.organization is not None and organization.id == context.organization.id
    if organization.access_mode == OrganizationAccessMode.ALL_AUTHORIZED:
        return True
    if context.is_owner:
        return True
    return (
        OrganizationAccessAssignment.scoped.for_tenant(context.tenant)
        .filter(
            organization=organization,
            membership__user=context.user,
        )
        .exists()
    )


def _archived_organization_allowed(context: InstallationMemberContext, organization: Organization) -> bool:
    if organization.tenant_id != context.tenant.id or organization.entity.archived_at is None:
        return False
    if organization.access_mode == OrganizationAccessMode.ALL_AUTHORIZED or context.is_owner:
        return True
    return (
        OrganizationAccessAssignment.scoped.for_tenant(context.tenant)
        .filter(
            organization=organization,
            membership__user=context.user,
        )
        .exists()
    )


def context_has_permission(
    context: InstallationMemberContext,
    permission: PermissionKey,
    *,
    organization: Organization | None = None,
) -> bool:
    if context.surface == "client_portal":
        return False
    if not _token_allows(context, permission, organization=organization):
        return False
    if not _permission_granted(context, permission, organization=organization):
        return False
    return organization is None or _organization_allowed(context, organization)


def require_permission(
    user: User,
    permission: PermissionKey,
    *,
    organization: Organization | None = None,
) -> InstallationMemberContext:
    context = require_installation_member(user)
    if not context_has_permission(context, permission, organization=organization):
        raise PermissionDenied("Your account is not authorized for this action.")
    if (
        PERMISSION_BY_KEY[permission].requires_mfa
        and not Authenticator.objects.filter(
            user=user,
            type=Authenticator.Type.TOTP,
        ).exists()
    ):
        raise PrivilegedMFARequired()
    return context


def require_client_portal_member(user: User) -> InstallationMemberContext:
    context = require_installation_member(user)
    if context.surface != "client_portal" or context.organization is None:
        raise PermissionDenied("Client portal membership is required.")
    if context.organization.entity.archived_at is not None:
        raise PermissionDenied("Client portal membership is unavailable.")
    return context


def context_has_archived_organization_permission(
    context: InstallationMemberContext,
    permission: PermissionKey,
    *,
    organization: Organization,
) -> bool:
    return (
        _token_allows(context, permission, organization=organization)
        and _permission_granted(context, permission, organization=organization)
        and _archived_organization_allowed(context, organization)
    )


def require_archived_organization_permission(
    user: User,
    permission: PermissionKey,
    *,
    organization: Organization,
) -> InstallationMemberContext:
    context = require_installation_member(user)
    if not context_has_archived_organization_permission(context, permission, organization=organization):
        raise PermissionDenied("Your account is not authorized for this action.")
    if (
        PERMISSION_BY_KEY[permission].requires_mfa
        and not Authenticator.objects.filter(
            user=user,
            type=Authenticator.Type.TOTP,
        ).exists()
    ):
        raise PrivilegedMFARequired()
    return context


def accessible_organizations(
    context: InstallationMemberContext,
    permission: PermissionKey = PermissionKey.ORGANIZATIONS_VIEW,
) -> QuerySet[Organization]:
    organizations = Organization.scoped.for_tenant(context.tenant).filter(entity__archived_at__isnull=True)
    token = getattr(context.user, "tekdocs_api_token", None)
    if token is not None:
        if not _token_allows(context, permission, organization=token.organization):
            return organizations.none()
        organizations = organizations.filter(pk=token.organization_id)
    tenant_grant = permission in context.permissions or _custom_permission_exists(context, permission)
    if not tenant_grant:
        if context.membership_id is None:
            return organizations.none()
        organizations = organizations.filter(
            Q(
                scoped_role_assignments__membership_id=context.membership_id,
                scoped_role_assignments__role__scope="organization",
                scoped_role_assignments__role__archived_at__isnull=True,
                scoped_role_assignments__role__permission_rows__permission=permission.value,
            )
            | Q(
                access_collection_edges__collection__scoped_role_assignments__membership_id=context.membership_id,
                access_collection_edges__collection__scoped_role_assignments__role__scope="collection",
                access_collection_edges__collection__scoped_role_assignments__role__archived_at__isnull=True,
                access_collection_edges__collection__scoped_role_assignments__role__permission_rows__permission=permission.value,
                access_collection_edges__collection__archived_at__isnull=True,
            )
        )
    if context.surface == "client_portal":
        if context.organization is None:
            return organizations.none()
        organizations = organizations.filter(pk=context.organization.id)
    elif not context.is_owner:
        organizations = organizations.filter(
            Q(access_mode=OrganizationAccessMode.ALL_AUTHORIZED) | Q(access_assignments__membership__user=context.user)
        ).distinct()
    return organizations


def _custom_permission_exists(
    context: InstallationMemberContext,
    permission: PermissionKey,
    organization: Organization | None = None,
) -> bool:
    if context.membership_id is None:
        return False
    assignments = ScopedRoleAssignment.scoped.for_tenant(context.tenant).filter(
        membership_id=context.membership_id,
        role__archived_at__isnull=True,
        role__permission_rows__permission=permission.value,
    )
    if organization is None:
        assignments = assignments.filter(
            role__scope="tenant",
            organization__isnull=True,
            collection__isnull=True,
        )
    else:
        assignments = assignments.filter(
            Q(role__scope="tenant", organization__isnull=True, collection__isnull=True)
            | Q(role__scope="organization", organization=organization, collection__isnull=True)
            | Q(
                role__scope="collection",
                organization__isnull=True,
                collection__archived_at__isnull=True,
                collection__organization_edges__organization=organization,
            )
        )
    return assignments.exists()


def _permission_granted(
    context: InstallationMemberContext,
    permission: PermissionKey,
    *,
    organization: Organization | None = None,
) -> bool:
    return permission in context.permissions or _custom_permission_exists(context, permission, organization)


def _token_allows(
    context: InstallationMemberContext,
    permission: PermissionKey,
    *,
    organization: Organization | None,
) -> bool:
    token = getattr(context.user, "tekdocs_api_token", None)
    if token is None:
        return True
    if not any(row.permission == permission.value for row in token.permission_rows.all()):
        return False
    if token.workspace_scope == "msp":
        return organization is None
    return organization is not None and organization.id == token.organization_id


def custom_assignable_permission_catalog() -> list[dict[str, object]]:
    return [
        definition.as_dict()
        for definition in PERMISSION_CATALOG
        if definition.key in CUSTOM_ROLE_ASSIGNABLE_PERMISSIONS
    ]


def entity_visible_to_audience(
    context: InstallationMemberContext,
    entity: Entity,
    *,
    audience: DataAudience,
    organization: Organization | None = None,
) -> bool:
    if entity.tenant_id != context.tenant.id:
        return False
    if audience == DataAudience.MSP_STAFF:
        return entity.organization_id is None or (
            organization is not None
            and entity.organization_id == organization.id
            and _organization_allowed(context, organization)
        )
    return (
        organization is not None
        and entity.organization_id == organization.id
        and entity.visibility == EntityVisibility.CLIENT_VISIBLE
        and _organization_allowed(context, organization)
    )


def entities_visible_to_audience(
    context: InstallationMemberContext,
    entities: QuerySet[Entity],
    *,
    audience: DataAudience,
    organization: Organization | None = None,
) -> QuerySet[Entity]:
    entities = entities.filter(tenant=context.tenant)
    if audience == DataAudience.MSP_STAFF:
        if organization is None:
            return entities.filter(organization__isnull=True)
        if not _organization_allowed(context, organization):
            return entities.none()
        return entities.filter(organization=organization)
    if organization is None or not _organization_allowed(context, organization):
        return entities.none()
    return entities.filter(organization=organization, visibility=EntityVisibility.CLIENT_VISIBLE)


def context_has_field_access(
    context: InstallationMemberContext,
    field: SensitiveField,
    *,
    organization: Organization | None = None,
) -> bool:
    return context_has_permission(context, SENSITIVE_FIELD_PERMISSIONS[field], organization=organization)


def project_authorized_fields(
    context: InstallationMemberContext,
    values: dict[str, object],
    classifications: dict[str, SensitiveField],
    *,
    organization: Organization | None = None,
) -> dict[str, object]:
    return {
        key: value
        for key, value in values.items()
        if key not in classifications
        or context_has_field_access(context, classifications[key], organization=organization)
    }


def require_installation_owner(user: User) -> InstallationMemberContext:
    """Compatibility boundary for bootstrap-era callers; new code requests a permission key."""
    return require_permission(user, PermissionKey.INSTALLATION_MANAGE)


def tenant_assignable_roles() -> Iterable[BuiltInRole]:
    return TENANT_ASSIGNABLE_ROLES
