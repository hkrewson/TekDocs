from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

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
from apps.core.organization_views import OrganizationDetailView, OrganizationListCreateView
from apps.core.people_views import (
    MSPPeopleListCreateView,
    MSPPersonDetailView,
    OrganizationPeopleListCreateView,
    OrganizationPersonDetailView,
)
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
    path("api/v1/invitations/accept", InvitationAcceptView.as_view(), name="invitation-accept"),
    path("api/v1/invitations", InvitationListCreateView.as_view(), name="invitation-list-create"),
    path("api/v1/organizations", OrganizationListCreateView.as_view(), name="organization-list-create"),
    path("api/v1/organizations/<uuid:entity_id>", OrganizationDetailView.as_view(), name="organization-detail"),
    path("api/v1/people", MSPPeopleListCreateView.as_view(), name="msp-people-list-create"),
    path("api/v1/people/<uuid:person_entity_id>", MSPPersonDetailView.as_view(), name="msp-person-detail"),
    path("api/v1/sites", MSPSiteListCreateView.as_view(), name="msp-site-list-create"),
    path("api/v1/sites/<uuid:site_entity_id>", MSPSiteDetailView.as_view(), name="msp-site-detail"),
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
