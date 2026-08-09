from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts.access_views import (
    AccessCollectionDetailView,
    AccessCollectionListCreateView,
    AccessControlCatalogView,
    CustomRoleDetailView,
    CustomRoleListCreateView,
    MemberListView,
    MemberRoleView,
    OrganizationAccessDetailView,
    OrganizationAccessListView,
    OrganizationStaffAssignmentDetailView,
    OrganizationStaffAssignmentView,
    ScopedRoleAssignmentDetailView,
    ScopedRoleAssignmentListCreateView,
)
from apps.accounts.views import (
    AuthenticatedContextView,
    BootstrapStatusView,
    InvitationAcceptView,
    InvitationListCreateView,
    InvitationResendView,
    InvitationRevokeView,
    OidcProviderListView,
    OwnerBootstrapView,
    ProfileView,
)
from apps.core.custom_field_views import (
    MSPCustomFieldDefinitionDetailView,
    MSPCustomFieldDefinitionListCreateView,
    MSPEntityCustomFieldDetailView,
    MSPEntityCustomFieldListView,
    OrganizationCustomFieldDefinitionDetailView,
    OrganizationCustomFieldDefinitionListCreateView,
    OrganizationEntityCustomFieldDetailView,
    OrganizationEntityCustomFieldListView,
)
from apps.core.document_views import (
    MSPDocumentDetailView,
    MSPDocumentListCreateView,
    MSPDocumentPlacementDetailView,
    MSPDocumentPlacementListCreateView,
    MSPDocumentReferenceDetailView,
    MSPDocumentReferenceListCreateView,
    MSPDocumentRevisionDetailView,
    MSPDocumentRevisionListView,
    OrganizationDocumentDetailView,
    OrganizationDocumentListCreateView,
    OrganizationDocumentPlacementDetailView,
    OrganizationDocumentPlacementListCreateView,
    OrganizationDocumentRevisionDetailView,
    OrganizationDocumentRevisionListView,
)
from apps.core.organization_views import OrganizationDetailView, OrganizationListCreateView
from apps.core.people_views import (
    MSPPeopleListCreateView,
    MSPPersonDetailView,
    OrganizationPeopleListCreateView,
    OrganizationPersonDetailView,
)
from apps.core.recycle_views import (
    MSPRecycleBinListView,
    MSPRecycleBinRestoreView,
    OrganizationRecycleBinListView,
    OrganizationRecycleBinRestoreView,
)
from apps.core.relationship_views import (
    EntityLinkTypeCatalogView,
    MSPEntityRelationshipDetailView,
    MSPEntityRelationshipListCreateView,
    MSPEntitySearchView,
    OrganizationEntityRelationshipDetailView,
    OrganizationEntityRelationshipListCreateView,
    OrganizationEntitySearchView,
)
from apps.core.rendering_views import MarkdownRenderView
from apps.core.site_views import (
    MSPLocationDetailView,
    MSPLocationListCreateView,
    MSPSiteDetailView,
    MSPSiteListCreateView,
    OrganizationLocationDetailView,
    OrganizationLocationListCreateView,
    OrganizationSiteDetailView,
    OrganizationSiteListCreateView,
)
from apps.core.views import ApiRootView, LiveHealthView, ReadyHealthView
from apps.core.workspace_views import (
    MSPWorkspaceContextView,
    OrganizationWorkspaceContextView,
    OrganizationWorkspaceSearchView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("_allauth/oidc/", include("allauth.socialaccount.providers.openid_connect.urls")),
    path("_allauth/", include("allauth.headless.urls")),
    path("api/v1/", ApiRootView.as_view(), name="api-root"),
    path("api/v1/bootstrap/status", BootstrapStatusView.as_view(), name="bootstrap-status"),
    path("api/v1/bootstrap/owner", OwnerBootstrapView.as_view(), name="bootstrap-owner"),
    path("api/v1/auth/context", AuthenticatedContextView.as_view(), name="auth-context"),
    path("api/v1/auth/profile", ProfileView.as_view(), name="auth-profile"),
    path("api/v1/auth/providers", OidcProviderListView.as_view(), name="auth-providers"),
    path("api/v1/access-control/catalog", AccessControlCatalogView.as_view(), name="access-control-catalog"),
    path(
        "api/v1/access-control/collections",
        AccessCollectionListCreateView.as_view(),
        name="access-collection-list-create",
    ),
    path(
        "api/v1/access-control/collections/<uuid:collection_id>",
        AccessCollectionDetailView.as_view(),
        name="access-collection-detail",
    ),
    path("api/v1/access-control/custom-roles", CustomRoleListCreateView.as_view(), name="custom-role-list-create"),
    path(
        "api/v1/access-control/custom-roles/<uuid:role_id>", CustomRoleDetailView.as_view(), name="custom-role-detail"
    ),
    path(
        "api/v1/access-control/role-assignments",
        ScopedRoleAssignmentListCreateView.as_view(),
        name="scoped-role-assignment-list-create",
    ),
    path(
        "api/v1/access-control/role-assignments/<uuid:assignment_id>",
        ScopedRoleAssignmentDetailView.as_view(),
        name="scoped-role-assignment-detail",
    ),
    path("api/v1/access-control/members", MemberListView.as_view(), name="access-control-members"),
    path(
        "api/v1/access-control/members/<uuid:user_id>",
        MemberRoleView.as_view(),
        name="access-control-member-role",
    ),
    path(
        "api/v1/access-control/organizations",
        OrganizationAccessListView.as_view(),
        name="access-control-organizations",
    ),
    path(
        "api/v1/access-control/organizations/<uuid:organization_entity_id>",
        OrganizationAccessDetailView.as_view(),
        name="access-control-organization-detail",
    ),
    path(
        "api/v1/access-control/organizations/<uuid:organization_entity_id>/staff",
        OrganizationStaffAssignmentView.as_view(),
        name="access-control-organization-staff",
    ),
    path(
        "api/v1/access-control/organizations/<uuid:organization_entity_id>/staff/<uuid:user_id>",
        OrganizationStaffAssignmentDetailView.as_view(),
        name="access-control-organization-staff-detail",
    ),
    path("api/v1/invitations/accept", InvitationAcceptView.as_view(), name="invitation-accept"),
    path("api/v1/invitations", InvitationListCreateView.as_view(), name="invitation-list-create"),
    path("api/v1/markdown/render", MarkdownRenderView.as_view(), name="markdown-render"),
    path("api/v1/organizations", OrganizationListCreateView.as_view(), name="organization-list-create"),
    path("api/v1/organizations/<uuid:entity_id>", OrganizationDetailView.as_view(), name="organization-detail"),
    path("api/v1/documents", MSPDocumentListCreateView.as_view(), name="msp-document-list-create"),
    path(
        "api/v1/documents/<uuid:document_entity_id>",
        MSPDocumentDetailView.as_view(),
        name="msp-document-detail",
    ),
    path(
        "api/v1/documents/<uuid:document_entity_id>/placements",
        MSPDocumentPlacementListCreateView.as_view(),
        name="msp-document-placement-list-create",
    ),
    path(
        "api/v1/documents/<uuid:document_entity_id>/placements/<uuid:placement_id>",
        MSPDocumentPlacementDetailView.as_view(),
        name="msp-document-placement-detail",
    ),
    path(
        "api/v1/documents/<uuid:document_entity_id>/revisions",
        MSPDocumentRevisionListView.as_view(),
        name="msp-document-revision-list",
    ),
    path(
        "api/v1/documents/<uuid:document_entity_id>/revisions/<uuid:revision_id>",
        MSPDocumentRevisionDetailView.as_view(),
        name="msp-document-revision-detail",
    ),
    path(
        "api/v1/documents/<uuid:document_entity_id>/references",
        MSPDocumentReferenceListCreateView.as_view(),
        name="msp-document-reference-list-create",
    ),
    path(
        "api/v1/documents/<uuid:document_entity_id>/references/<uuid:reference_id>",
        MSPDocumentReferenceDetailView.as_view(),
        name="msp-document-reference-detail",
    ),
    path("api/v1/recycle-bin", MSPRecycleBinListView.as_view(), name="msp-recycle-bin"),
    path(
        "api/v1/recycle-bin/<str:record_type>/<uuid:record_id>/restore",
        MSPRecycleBinRestoreView.as_view(),
        name="msp-recycle-bin-restore",
    ),
    path("api/v1/entity-link-types", EntityLinkTypeCatalogView.as_view(), name="entity-link-type-catalog"),
    path("api/v1/entities/search", MSPEntitySearchView.as_view(), name="msp-entity-search"),
    path(
        "api/v1/entities/<uuid:entity_id>/links",
        MSPEntityRelationshipListCreateView.as_view(),
        name="msp-entity-relationship-list-create",
    ),
    path(
        "api/v1/entities/<uuid:entity_id>/links/<uuid:link_id>",
        MSPEntityRelationshipDetailView.as_view(),
        name="msp-entity-relationship-detail",
    ),
    path("api/v1/people", MSPPeopleListCreateView.as_view(), name="msp-people-list-create"),
    path("api/v1/people/<uuid:person_entity_id>", MSPPersonDetailView.as_view(), name="msp-person-detail"),
    path("api/v1/sites", MSPSiteListCreateView.as_view(), name="msp-site-list-create"),
    path("api/v1/sites/<uuid:site_entity_id>", MSPSiteDetailView.as_view(), name="msp-site-detail"),
    path(
        "api/v1/custom-field-definitions",
        MSPCustomFieldDefinitionListCreateView.as_view(),
        name="msp-custom-field-definition-list-create",
    ),
    path(
        "api/v1/custom-field-definitions/<uuid:definition_id>",
        MSPCustomFieldDefinitionDetailView.as_view(),
        name="msp-custom-field-definition-detail",
    ),
    path(
        "api/v1/entities/<uuid:entity_id>/custom-fields",
        MSPEntityCustomFieldListView.as_view(),
        name="msp-entity-custom-field-list",
    ),
    path(
        "api/v1/entities/<uuid:entity_id>/custom-fields/<uuid:definition_id>",
        MSPEntityCustomFieldDetailView.as_view(),
        name="msp-entity-custom-field-detail",
    ),
    path(
        "api/v1/sites/<uuid:site_entity_id>/locations",
        MSPLocationListCreateView.as_view(),
        name="msp-location-list-create",
    ),
    path(
        "api/v1/sites/<uuid:site_entity_id>/locations/<uuid:location_entity_id>",
        MSPLocationDetailView.as_view(),
        name="msp-location-detail",
    ),
    path("api/v1/workspaces/msp", MSPWorkspaceContextView.as_view(), name="workspace-msp"),
    path(
        "api/v1/workspaces/organizations",
        OrganizationWorkspaceSearchView.as_view(),
        name="workspace-organization-search",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:entity_id>",
        OrganizationWorkspaceContextView.as_view(),
        name="workspace-organization",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/people",
        OrganizationPeopleListCreateView.as_view(),
        name="organization-people-list-create",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/documents",
        OrganizationDocumentListCreateView.as_view(),
        name="organization-document-list-create",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/documents/<uuid:document_entity_id>",
        OrganizationDocumentDetailView.as_view(),
        name="organization-document-detail",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/documents/<uuid:document_entity_id>/placements",
        OrganizationDocumentPlacementListCreateView.as_view(),
        name="organization-document-placement-list-create",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/documents/<uuid:document_entity_id>/placements/<uuid:placement_id>",
        OrganizationDocumentPlacementDetailView.as_view(),
        name="organization-document-placement-detail",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/documents/<uuid:document_entity_id>/revisions",
        OrganizationDocumentRevisionListView.as_view(),
        name="organization-document-revision-list",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/documents/<uuid:document_entity_id>/revisions/<uuid:revision_id>",
        OrganizationDocumentRevisionDetailView.as_view(),
        name="organization-document-revision-detail",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/recycle-bin",
        OrganizationRecycleBinListView.as_view(),
        name="organization-recycle-bin",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/recycle-bin/<str:record_type>/<uuid:record_id>/restore",
        OrganizationRecycleBinRestoreView.as_view(),
        name="organization-recycle-bin-restore",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/entities/search",
        OrganizationEntitySearchView.as_view(),
        name="organization-entity-search",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/entities/<uuid:entity_id>/links",
        OrganizationEntityRelationshipListCreateView.as_view(),
        name="organization-entity-relationship-list-create",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/entities/<uuid:entity_id>/links/<uuid:link_id>",
        OrganizationEntityRelationshipDetailView.as_view(),
        name="organization-entity-relationship-detail",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/people/<uuid:person_entity_id>",
        OrganizationPersonDetailView.as_view(),
        name="organization-person-detail",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/sites",
        OrganizationSiteListCreateView.as_view(),
        name="organization-site-list-create",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/custom-field-definitions",
        OrganizationCustomFieldDefinitionListCreateView.as_view(),
        name="organization-custom-field-definition-list-create",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/custom-field-definitions/<uuid:definition_id>",
        OrganizationCustomFieldDefinitionDetailView.as_view(),
        name="organization-custom-field-definition-detail",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/entities/<uuid:entity_id>/custom-fields",
        OrganizationEntityCustomFieldListView.as_view(),
        name="organization-entity-custom-field-list",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/entities/<uuid:entity_id>/custom-fields/<uuid:definition_id>",
        OrganizationEntityCustomFieldDetailView.as_view(),
        name="organization-entity-custom-field-detail",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/sites/<uuid:site_entity_id>",
        OrganizationSiteDetailView.as_view(),
        name="organization-site-detail",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/sites/<uuid:site_entity_id>/locations",
        OrganizationLocationListCreateView.as_view(),
        name="organization-location-list-create",
    ),
    path(
        "api/v1/workspaces/organizations/<uuid:organization_entity_id>/sites/<uuid:site_entity_id>/locations/<uuid:location_entity_id>",
        OrganizationLocationDetailView.as_view(),
        name="organization-location-detail",
    ),
    path(
        "api/v1/invitations/<uuid:invitation_id>/revoke",
        InvitationRevokeView.as_view(),
        name="invitation-revoke",
    ),
    path(
        "api/v1/invitations/<uuid:invitation_id>/resend",
        InvitationResendView.as_view(),
        name="invitation-resend",
    ),
    path("api/v1/health/live", LiveHealthView.as_view(), name="health-live"),
    path("api/v1/health/ready", ReadyHealthView.as_view(), name="health-ready"),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
]
