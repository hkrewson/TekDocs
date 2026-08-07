from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts.views import (
    AuthenticatedContextView,
    BootstrapStatusView,
    InvitationListCreateView,
    InvitationResendView,
    InvitationRevokeView,
    OwnerBootstrapView,
)
from apps.core.views import ApiRootView, LiveHealthView, ReadyHealthView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("_allauth/", include("allauth.headless.urls")),
    path("api/v1/", ApiRootView.as_view(), name="api-root"),
    path("api/v1/bootstrap/status", BootstrapStatusView.as_view(), name="bootstrap-status"),
    path("api/v1/bootstrap/owner", OwnerBootstrapView.as_view(), name="bootstrap-owner"),
    path("api/v1/auth/context", AuthenticatedContextView.as_view(), name="auth-context"),
    path("api/v1/invitations", InvitationListCreateView.as_view(), name="invitation-list-create"),
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
