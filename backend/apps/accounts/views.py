import secrets
from typing import Any
from uuid import UUID

from django.conf import settings
from django.contrib.auth import login
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import InstallationState, Organization

from .audit import record_auth_event
from .bootstrap import bootstrap_owner
from .invitations import InvitationConflict, accept_invitation, issue_invitation, resend_invitation, revoke_invitation
from .models import BuiltInRole, Invitation, User
from .policy import (
    InstallationMemberContext,
    PermissionKey,
    require_client_portal_member,
    require_installation_member,
    require_permission,
)
from .serializers import (
    AuthenticatedContextSerializer,
    BootstrapStatusSerializer,
    InvitationAcceptanceSerializer,
    InvitationRequestSerializer,
    InvitationSerializer,
    OidcProviderListSerializer,
    OwnerBootstrapResultSerializer,
    OwnerBootstrapSerializer,
    ProfileUpdateSerializer,
)

BOOTSTRAP_AUTH_HEADER = "X-TekDocs-Bootstrap-Token"


def _context_payload(user: User, context: InstallationMemberContext) -> dict[str, object]:
    return {
        "user": {"id": str(user.pk), "email": user.email, "display_name": user.display_name},
        "tenant": {"id": str(context.tenant.id), "name": context.tenant.name},
        "role": context.role.value,
        "permissions": sorted(permission.value for permission in context.permissions),
        "surface": context.surface,
        "organization": (
            {
                "id": str(context.organization.entity_id),
                "name": context.organization.entity.display_name,
            }
            if context.organization is not None
            else None
        ),
    }


@method_decorator(ensure_csrf_cookie, name="dispatch")
class BootstrapStatusView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: BootstrapStatusSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        required = InstallationState.objects.filter(
            pk=InstallationState.SINGLETON_ID,
            bootstrapped_at__isnull=True,
        ).exists()
        return Response({"bootstrap_required": required})


class OwnerBootstrapView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=OwnerBootstrapSerializer,
        parameters=[
            OpenApiParameter(
                name=BOOTSTRAP_AUTH_HEADER,
                type=str,
                location=OpenApiParameter.HEADER,
                required=True,
                description="High-entropy deployment bootstrap secret",
            )
        ],
        responses={
            201: OwnerBootstrapResultSerializer,
            400: OpenApiResponse(description="Invalid bootstrap details"),
            403: OpenApiResponse(description="Bootstrap authorization failed"),
            409: OpenApiResponse(description="Installation already bootstrapped or not pristine"),
        },
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        configured_token = settings.TEKDOCS_BOOTSTRAP_TOKEN
        supplied_token = request.headers.get(BOOTSTRAP_AUTH_HEADER, "")
        if not configured_token or not secrets.compare_digest(supplied_token, configured_token):
            raise PermissionDenied("Bootstrap authorization failed.")

        serializer = OwnerBootstrapSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = bootstrap_owner(**serializer.validated_data)
        return Response(
            {
                "tenant": {"id": str(result.tenant.id), "name": result.tenant.name},
                "owner": {"id": str(result.owner.id), "display_name": result.owner.display_name},
            },
            status=201,
        )


class AuthenticatedContextView(APIView):
    @extend_schema(
        responses={
            200: AuthenticatedContextSerializer,
            403: OpenApiResponse(description="Authentication or installation membership required"),
            503: OpenApiResponse(description="Installation context unavailable"),
        }
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        context = require_installation_member(request.user)
        return Response(_context_payload(request.user, context))


class ClientPortalContextView(APIView):
    @extend_schema(responses={200: AuthenticatedContextSerializer, 403: OpenApiResponse(description="Portal required")})
    def get(self, request):  # type: ignore[no-untyped-def]
        context = require_client_portal_member(request.user)
        return Response(_context_payload(request.user, context))


class ProfileView(APIView):
    @extend_schema(
        request=ProfileUpdateSerializer,
        responses={
            200: AuthenticatedContextSerializer,
            400: OpenApiResponse(description="Invalid profile details"),
            403: OpenApiResponse(description="Authentication or installation membership required"),
        },
    )
    @transaction.atomic
    def patch(self, request):  # type: ignore[no-untyped-def]
        context = require_installation_member(request.user)
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.display_name = serializer.validated_data["display_name"]
        request.user.save(update_fields=("display_name",))
        record_auth_event(action="auth.profile_updated", request=request, user=request.user)
        return Response(_context_payload(request.user, context))


class OidcProviderListView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: OidcProviderListSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        provider = settings.TEKDOCS_OIDC_PROVIDER
        providers = [] if provider is None else [{"id": provider["id"], "name": provider["name"]}]
        return Response({"providers": providers})


class InvitationAcceptView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        request=InvitationAcceptanceSerializer,
        responses={
            200: AuthenticatedContextSerializer,
            400: OpenApiResponse(description="Invalid account details or password"),
            403: OpenApiResponse(description="CSRF validation failed"),
            409: OpenApiResponse(description="Sign out before accepting an invitation"),
            410: OpenApiResponse(description="Invitation unavailable"),
        },
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        SessionAuthentication().enforce_csrf(request)
        if request.user.is_authenticated:
            raise InvitationConflict("Sign out before accepting an invitation.")
        serializer = InvitationAcceptanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        accepted = accept_invitation(**serializer.validated_data)
        login(request._request, accepted.user, backend="django.contrib.auth.backends.ModelBackend")
        context = require_installation_member(accepted.user)
        return Response(_context_payload(accepted.user, context))


class InvitationListCreateView(APIView):
    @extend_schema(responses={200: InvitationSerializer(many=True), 403: OpenApiResponse(description="Owner required")})
    def get(self, request):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.INVITATIONS_VIEW)
        invitations = Invitation.scoped.for_tenant(context.tenant).select_related("organization__entity")
        return Response(InvitationSerializer(invitations, many=True).data)

    @extend_schema(
        request=InvitationRequestSerializer,
        responses={
            201: InvitationSerializer,
            400: OpenApiResponse(description="Invalid invitation details"),
            403: OpenApiResponse(description="Owner required"),
            409: OpenApiResponse(description="Invitation conflict"),
            503: OpenApiResponse(description="Invitation retained but email delivery failed"),
        },
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.INVITATIONS_CREATE)
        serializer = InvitationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = issue_invitation(
            tenant=context.tenant,
            actor=request.user,
            email=serializer.validated_data["email"],
        )
        return Response(InvitationSerializer(invitation).data, status=201)


class ClientInvitationListCreateView(APIView):
    def _organization(
        self,
        request: Request,
        organization_entity_id: UUID,
    ) -> tuple[InstallationMemberContext, Organization]:
        context = require_permission(request.user, PermissionKey.INVITATIONS_VIEW)
        organization = get_object_or_404(
            Organization.scoped.for_tenant(context.tenant)
            .select_related("entity")
            .filter(classifications__kind="client", entity__archived_at__isnull=True)
            .distinct(),
            entity_id=organization_entity_id,
        )
        require_permission(request.user, PermissionKey.INVITATIONS_VIEW, organization=organization)
        return context, organization

    @extend_schema(responses={200: InvitationSerializer(many=True)})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        context, organization = self._organization(request, organization_entity_id)
        invitations = (
            Invitation.scoped.for_tenant(context.tenant)
            .filter(organization=organization)
            .select_related("organization__entity")
        )
        return Response(InvitationSerializer(invitations, many=True).data)

    @extend_schema(request=InvitationRequestSerializer, responses={201: InvitationSerializer})
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        context, organization = self._organization(request, organization_entity_id)
        require_permission(request.user, PermissionKey.INVITATIONS_CREATE, organization=organization)
        serializer = InvitationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = issue_invitation(
            tenant=context.tenant,
            actor=request.user,
            email=serializer.validated_data["email"],
            organization=organization,
            role=BuiltInRole.CLIENT_USER,
        )
        return Response(InvitationSerializer(invitation).data, status=201)


class InvitationRevokeView(APIView):
    @extend_schema(
        request=None,
        responses={
            200: InvitationSerializer,
            403: OpenApiResponse(description="Owner required"),
            404: OpenApiResponse(description="Invitation not found"),
            409: OpenApiResponse(description="Invitation is not pending"),
        },
    )
    def post(self, request, invitation_id):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.INVITATIONS_REVOKE)
        invitation = get_object_or_404(Invitation.scoped.for_tenant(context.tenant), pk=invitation_id)
        return Response(InvitationSerializer(revoke_invitation(invitation=invitation, actor=request.user)).data)


class InvitationResendView(APIView):
    @extend_schema(
        request=None,
        responses={
            200: InvitationSerializer,
            403: OpenApiResponse(description="Owner required"),
            404: OpenApiResponse(description="Invitation not found"),
            409: OpenApiResponse(description="Invitation is not pending"),
            503: OpenApiResponse(description="Invitation retained but email delivery failed"),
        },
    )
    def post(self, request, invitation_id):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.INVITATIONS_RESEND)
        invitation = get_object_or_404(Invitation.scoped.for_tenant(context.tenant), pk=invitation_id)
        return Response(InvitationSerializer(resend_invitation(invitation=invitation, actor=request.user)).data)
