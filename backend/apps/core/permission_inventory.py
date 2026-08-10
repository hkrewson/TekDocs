from dataclasses import dataclass

from apps.accounts.policy import PermissionKey


@dataclass(frozen=True, slots=True)
class RoutePermissionContract:
    route_name: str
    methods: tuple[str, ...]
    read_permission: PermissionKey | None = None
    mutation_permissions: tuple[PermissionKey, ...] = ()
    organization_scoped: bool = False


def route(
    route_name: str,
    methods: tuple[str, ...],
    read: PermissionKey | None = None,
    mutations: tuple[PermissionKey, ...] = (),
    *,
    organization_scoped: bool = False,
) -> RoutePermissionContract:
    return RoutePermissionContract(route_name, methods, read, mutations, organization_scoped)


AUTHENTICATED_ROUTE_PERMISSIONS = (
    route("auth-context", ("GET",)),
    route("auth-profile", ("PATCH",)),
    route("markdown-render", ("POST",), PermissionKey.DOCUMENTS_VIEW),
    route(
        "msp-credential-reference-list-create",
        ("GET", "POST"),
        PermissionKey.CREDENTIAL_REFERENCES_VIEW,
        (PermissionKey.CREDENTIAL_REFERENCES_MANAGE,),
    ),
    route(
        "msp-credential-reference-detail",
        ("PATCH", "DELETE"),
        mutations=(PermissionKey.CREDENTIAL_REFERENCES_MANAGE, PermissionKey.CREDENTIAL_REFERENCES_MANAGE),
    ),
    route("msp-credential-reference-open", ("GET",), PermissionKey.CREDENTIAL_REFERENCES_OPEN),
    route(
        "msp-document-list-create",
        ("GET", "POST"),
        PermissionKey.DOCUMENTS_VIEW,
        (PermissionKey.DOCUMENTS_EDIT,),
    ),
    route(
        "msp-document-detail",
        ("GET", "PUT", "DELETE"),
        PermissionKey.DOCUMENTS_VIEW,
        (PermissionKey.DOCUMENTS_EDIT,),
    ),
    route("msp-document-revision-list", ("GET",), PermissionKey.DOCUMENTS_VIEW),
    route("msp-document-revision-detail", ("GET",), PermissionKey.DOCUMENTS_VIEW),
    route(
        "msp-document-placement-list-create",
        ("POST",),
        mutations=(PermissionKey.DOCUMENTS_EDIT,),
    ),
    route(
        "msp-document-placement-detail",
        ("PATCH", "DELETE"),
        mutations=(PermissionKey.DOCUMENTS_EDIT,),
    ),
    route(
        "msp-document-placement-reuse", ("GET", "PUT"), PermissionKey.DOCUMENTS_VIEW, (PermissionKey.DOCUMENTS_EDIT,)
    ),
    route("msp-document-placement-detach", ("POST",), mutations=(PermissionKey.DOCUMENTS_EDIT,)),
    route("msp-document-mention-search", ("GET",), PermissionKey.DOCUMENTS_VIEW),
    route("msp-document-template-instantiate", ("POST",), mutations=(PermissionKey.DOCUMENTS_EDIT,)),
    route("msp-document-import", ("POST",), mutations=(PermissionKey.DOCUMENTS_EDIT,)),
    route("msp-document-export", ("GET",), PermissionKey.DOCUMENTS_VIEW),
    route("msp-document-attachment-list-create", ("POST",), mutations=(PermissionKey.DOCUMENTS_EDIT,)),
    route("msp-document-attachment-detail", ("DELETE",), mutations=(PermissionKey.DOCUMENTS_EDIT,)),
    route("msp-document-attachment-download", ("GET",), PermissionKey.DOCUMENTS_VIEW),
    route(
        "msp-document-publication-list-create",
        ("GET", "POST"),
        PermissionKey.DOCUMENTS_VIEW,
        (PermissionKey.DOCUMENTS_PUBLISH,),
    ),
    route("msp-document-publication-detail", ("GET",), PermissionKey.DOCUMENTS_VIEW),
    route("msp-document-publication-markdown", ("GET",), PermissionKey.DOCUMENTS_VIEW),
    route("msp-document-publication-manifest", ("GET",), PermissionKey.DOCUMENTS_VIEW),
    route("msp-document-publication-artifact-download", ("GET",), PermissionKey.DOCUMENTS_VIEW),
    route(
        "msp-document-reference-list-create",
        ("GET", "POST"),
        PermissionKey.DOCUMENTS_VIEW,
        (PermissionKey.DOCUMENTS_EDIT,),
    ),
    route(
        "msp-document-reference-detail",
        ("DELETE",),
        mutations=(PermissionKey.DOCUMENTS_EDIT,),
    ),
    route("access-control-catalog", ("GET",), PermissionKey.MEMBERSHIPS_VIEW),
    route(
        "access-collection-list-create",
        ("GET", "POST"),
        PermissionKey.ACCESS_COLLECTIONS_VIEW,
        (PermissionKey.ACCESS_COLLECTIONS_MANAGE,),
    ),
    route(
        "access-collection-detail",
        ("PATCH", "DELETE"),
        mutations=(PermissionKey.ACCESS_COLLECTIONS_MANAGE,),
    ),
    route(
        "custom-role-list-create",
        ("GET", "POST"),
        PermissionKey.CUSTOM_ROLES_VIEW,
        (PermissionKey.CUSTOM_ROLES_MANAGE,),
    ),
    route("custom-role-detail", ("PATCH", "DELETE"), mutations=(PermissionKey.CUSTOM_ROLES_MANAGE,)),
    route(
        "scoped-role-assignment-list-create",
        ("GET", "POST"),
        PermissionKey.CUSTOM_ROLES_VIEW,
        (PermissionKey.CUSTOM_ROLES_ASSIGN,),
    ),
    route(
        "scoped-role-assignment-detail",
        ("DELETE",),
        mutations=(PermissionKey.CUSTOM_ROLES_ASSIGN,),
    ),
    route("access-control-members", ("GET",), PermissionKey.MEMBERSHIPS_VIEW),
    route(
        "access-control-member-role",
        ("PATCH",),
        mutations=(PermissionKey.MEMBERSHIPS_ASSIGN_ROLE,),
    ),
    route(
        "access-control-organizations",
        ("GET",),
        PermissionKey.ORGANIZATIONS_MANAGE_ACCESS,
    ),
    route(
        "access-control-organization-detail",
        ("PATCH",),
        mutations=(PermissionKey.ORGANIZATIONS_MANAGE_ACCESS,),
        organization_scoped=True,
    ),
    route(
        "access-control-organization-staff",
        ("POST",),
        None,
        (PermissionKey.ORGANIZATIONS_ASSIGN_STAFF,),
        organization_scoped=True,
    ),
    route(
        "access-control-organization-staff-detail",
        ("DELETE",),
        mutations=(PermissionKey.ORGANIZATIONS_ASSIGN_STAFF,),
        organization_scoped=True,
    ),
    route(
        "invitation-list-create",
        ("GET", "POST"),
        PermissionKey.INVITATIONS_VIEW,
        (PermissionKey.INVITATIONS_CREATE,),
    ),
    route("invitation-revoke", ("POST",), mutations=(PermissionKey.INVITATIONS_REVOKE,)),
    route("invitation-resend", ("POST",), mutations=(PermissionKey.INVITATIONS_RESEND,)),
    route(
        "organization-list-create",
        ("GET", "POST"),
        PermissionKey.ORGANIZATIONS_VIEW,
        (PermissionKey.ORGANIZATIONS_CREATE,),
    ),
    route(
        "organization-detail",
        ("GET", "PATCH", "DELETE"),
        PermissionKey.ORGANIZATIONS_VIEW,
        (PermissionKey.ORGANIZATIONS_EDIT, PermissionKey.ORGANIZATIONS_ARCHIVE),
    ),
    route("entity-link-type-catalog", ("GET",), PermissionKey.RELATIONSHIPS_VIEW),
    route("msp-entity-search", ("GET",), PermissionKey.RELATIONSHIPS_VIEW),
    route(
        "msp-entity-relationship-list-create",
        ("GET", "POST"),
        PermissionKey.RELATIONSHIPS_VIEW,
        (PermissionKey.RELATIONSHIPS_CREATE,),
    ),
    route(
        "msp-entity-relationship-detail",
        ("DELETE",),
        mutations=(PermissionKey.RELATIONSHIPS_ARCHIVE,),
    ),
    route(
        "msp-people-list-create",
        ("GET", "POST"),
        PermissionKey.PEOPLE_VIEW,
        (PermissionKey.PEOPLE_CREATE,),
    ),
    route(
        "msp-person-detail",
        ("GET", "PATCH", "DELETE"),
        PermissionKey.PEOPLE_VIEW,
        (PermissionKey.PEOPLE_EDIT, PermissionKey.PEOPLE_ARCHIVE),
    ),
    route(
        "msp-site-list-create",
        ("GET", "POST"),
        PermissionKey.SITES_VIEW,
        (PermissionKey.SITES_CREATE,),
    ),
    route(
        "msp-site-detail",
        ("GET", "PATCH", "DELETE"),
        PermissionKey.SITES_VIEW,
        (PermissionKey.SITES_EDIT, PermissionKey.SITES_ARCHIVE),
    ),
    route("msp-location-list-create", ("POST",), mutations=(PermissionKey.SITES_CREATE,)),
    route(
        "msp-location-detail",
        ("PATCH", "DELETE"),
        mutations=(PermissionKey.SITES_EDIT, PermissionKey.SITES_ARCHIVE),
    ),
    route(
        "msp-custom-field-definition-list-create",
        ("GET", "POST"),
        PermissionKey.CUSTOM_FIELDS_VIEW,
        (PermissionKey.CUSTOM_FIELDS_MANAGE,),
    ),
    route(
        "msp-custom-field-definition-detail",
        ("PATCH", "DELETE"),
        mutations=(PermissionKey.CUSTOM_FIELDS_MANAGE,),
    ),
    route("msp-entity-custom-field-list", ("GET",), PermissionKey.CUSTOM_FIELDS_VIEW),
    route(
        "msp-entity-custom-field-detail",
        ("PATCH", "DELETE"),
        mutations=(PermissionKey.CUSTOM_FIELDS_EDIT_VALUES,),
    ),
    route("msp-recycle-bin", ("GET",), PermissionKey.RECYCLE_BIN_VIEW),
    route("msp-recycle-bin-restore", ("POST",), mutations=(PermissionKey.RECYCLE_BIN_RESTORE,)),
    route("workspace-msp", ("GET",), PermissionKey.WORKSPACES_VIEW),
    route("workspace-organization-search", ("GET",), PermissionKey.ORGANIZATIONS_VIEW),
    route("workspace-organization", ("GET",), PermissionKey.WORKSPACES_VIEW, organization_scoped=True),
    route(
        "organization-credential-reference-list-create",
        ("GET", "POST"),
        PermissionKey.CREDENTIAL_REFERENCES_VIEW,
        (PermissionKey.CREDENTIAL_REFERENCES_MANAGE,),
        organization_scoped=True,
    ),
    route(
        "organization-credential-reference-detail",
        ("PATCH", "DELETE"),
        mutations=(PermissionKey.CREDENTIAL_REFERENCES_MANAGE, PermissionKey.CREDENTIAL_REFERENCES_MANAGE),
        organization_scoped=True,
    ),
    route(
        "organization-credential-reference-open",
        ("GET",),
        PermissionKey.CREDENTIAL_REFERENCES_OPEN,
        organization_scoped=True,
    ),
    route(
        "organization-people-list-create",
        ("GET", "POST"),
        PermissionKey.PEOPLE_VIEW,
        (PermissionKey.PEOPLE_CREATE,),
        organization_scoped=True,
    ),
    route(
        "organization-document-list-create",
        ("GET", "POST"),
        PermissionKey.DOCUMENTS_VIEW,
        (PermissionKey.DOCUMENTS_EDIT,),
        organization_scoped=True,
    ),
    route(
        "organization-document-template-instantiate",
        ("POST",),
        mutations=(PermissionKey.DOCUMENTS_EDIT,),
        organization_scoped=True,
    ),
    route(
        "organization-document-import",
        ("POST",),
        mutations=(PermissionKey.DOCUMENTS_EDIT,),
        organization_scoped=True,
    ),
    route(
        "organization-document-export",
        ("GET",),
        PermissionKey.DOCUMENTS_VIEW,
        organization_scoped=True,
    ),
    route(
        "organization-document-attachment-list-create",
        ("POST",),
        mutations=(PermissionKey.DOCUMENTS_EDIT,),
        organization_scoped=True,
    ),
    route(
        "organization-document-attachment-detail",
        ("DELETE",),
        mutations=(PermissionKey.DOCUMENTS_EDIT,),
        organization_scoped=True,
    ),
    route(
        "organization-document-attachment-download",
        ("GET",),
        PermissionKey.DOCUMENTS_VIEW,
        organization_scoped=True,
    ),
    route(
        "organization-document-publication-list-create",
        ("GET", "POST"),
        PermissionKey.DOCUMENTS_VIEW,
        (PermissionKey.DOCUMENTS_PUBLISH,),
        organization_scoped=True,
    ),
    route(
        "organization-document-publication-detail",
        ("GET",),
        PermissionKey.DOCUMENTS_VIEW,
        organization_scoped=True,
    ),
    route(
        "organization-document-publication-markdown",
        ("GET",),
        PermissionKey.DOCUMENTS_VIEW,
        organization_scoped=True,
    ),
    route(
        "organization-document-publication-manifest",
        ("GET",),
        PermissionKey.DOCUMENTS_VIEW,
        organization_scoped=True,
    ),
    route(
        "organization-document-publication-artifact-download",
        ("GET",),
        PermissionKey.DOCUMENTS_VIEW,
        organization_scoped=True,
    ),
    route(
        "organization-document-detail",
        ("GET", "PUT", "DELETE"),
        PermissionKey.DOCUMENTS_VIEW,
        (PermissionKey.DOCUMENTS_EDIT,),
        organization_scoped=True,
    ),
    route(
        "organization-document-revision-list",
        ("GET",),
        PermissionKey.DOCUMENTS_VIEW,
        organization_scoped=True,
    ),
    route(
        "organization-document-revision-detail",
        ("GET",),
        PermissionKey.DOCUMENTS_VIEW,
        organization_scoped=True,
    ),
    route(
        "organization-document-placement-list-create",
        ("POST",),
        mutations=(PermissionKey.DOCUMENTS_EDIT,),
        organization_scoped=True,
    ),
    route(
        "organization-document-placement-detail",
        ("PATCH", "DELETE"),
        mutations=(PermissionKey.DOCUMENTS_EDIT,),
        organization_scoped=True,
    ),
    route(
        "organization-document-placement-reuse",
        ("GET", "PUT"),
        PermissionKey.DOCUMENTS_VIEW,
        (PermissionKey.DOCUMENTS_EDIT,),
        organization_scoped=True,
    ),
    route(
        "organization-document-placement-detach",
        ("POST",),
        mutations=(PermissionKey.DOCUMENTS_EDIT,),
        organization_scoped=True,
    ),
    route(
        "organization-document-mention-search",
        ("GET",),
        PermissionKey.DOCUMENTS_VIEW,
        organization_scoped=True,
    ),
    route(
        "organization-person-detail",
        ("GET", "PATCH", "DELETE"),
        PermissionKey.PEOPLE_VIEW,
        (PermissionKey.PEOPLE_EDIT, PermissionKey.PEOPLE_ARCHIVE),
        organization_scoped=True,
    ),
    route(
        "organization-site-list-create",
        ("GET", "POST"),
        PermissionKey.SITES_VIEW,
        (PermissionKey.SITES_CREATE,),
        organization_scoped=True,
    ),
    route(
        "organization-site-detail",
        ("GET", "PATCH", "DELETE"),
        PermissionKey.SITES_VIEW,
        (PermissionKey.SITES_EDIT, PermissionKey.SITES_ARCHIVE),
        organization_scoped=True,
    ),
    route(
        "organization-location-list-create",
        ("POST",),
        mutations=(PermissionKey.SITES_CREATE,),
        organization_scoped=True,
    ),
    route(
        "organization-location-detail",
        ("PATCH", "DELETE"),
        mutations=(PermissionKey.SITES_EDIT, PermissionKey.SITES_ARCHIVE),
        organization_scoped=True,
    ),
    route(
        "organization-custom-field-definition-list-create",
        ("GET", "POST"),
        PermissionKey.CUSTOM_FIELDS_VIEW,
        (PermissionKey.CUSTOM_FIELDS_MANAGE,),
        organization_scoped=True,
    ),
    route(
        "organization-custom-field-definition-detail",
        ("PATCH", "DELETE"),
        mutations=(PermissionKey.CUSTOM_FIELDS_MANAGE,),
        organization_scoped=True,
    ),
    route(
        "organization-entity-custom-field-list",
        ("GET",),
        PermissionKey.CUSTOM_FIELDS_VIEW,
        organization_scoped=True,
    ),
    route(
        "organization-entity-custom-field-detail",
        ("PATCH", "DELETE"),
        mutations=(PermissionKey.CUSTOM_FIELDS_EDIT_VALUES,),
        organization_scoped=True,
    ),
    route(
        "organization-entity-search",
        ("GET",),
        PermissionKey.RELATIONSHIPS_VIEW,
        organization_scoped=True,
    ),
    route(
        "organization-entity-relationship-list-create",
        ("GET", "POST"),
        PermissionKey.RELATIONSHIPS_VIEW,
        (PermissionKey.RELATIONSHIPS_CREATE,),
        organization_scoped=True,
    ),
    route(
        "organization-entity-relationship-detail",
        ("DELETE",),
        mutations=(PermissionKey.RELATIONSHIPS_ARCHIVE,),
        organization_scoped=True,
    ),
    route(
        "organization-recycle-bin",
        ("GET",),
        PermissionKey.RECYCLE_BIN_VIEW,
        organization_scoped=True,
    ),
    route(
        "organization-recycle-bin-restore",
        ("POST",),
        mutations=(PermissionKey.RECYCLE_BIN_RESTORE,),
        organization_scoped=True,
    ),
)


PUBLIC_API_ROUTE_NAMES = frozenset(
    {
        "api-root",
        "api-docs",
        "schema",
        "health-live",
        "health-ready",
        "bootstrap-status",
        "bootstrap-owner",
        "auth-providers",
        "invitation-accept",
    }
)
