import secrets
from typing import Any

from django.conf import settings
from django.contrib.auth import login
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import InstallationState

from .bootstrap import bootstrap_owner
from .invitations import InvitationConflict, accept_invitation, issue_invitation, resend_invitation, revoke_invitation
from .models import Invitation
from .policy import require_installation_member, require_installation_owner
from .serializers import (
    AuthenticatedContextSerializer,
    BootstrapStatusSerializer,
    InvitationAcceptanceSerializer,
    InvitationRequestSerializer,
    InvitationSerializer,
    OwnerBootstrapResultSerializer,
    OwnerBootstrapSerializer,
)

BOOTSTRAP_AUTH_HEADER = "X-TekDocs-Bootstrap-Token"


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
        return Response(
            {
                "user": {
                    "id": str(request.user.pk),
                    "email": request.user.email,
                    "display_name": request.user.display_name,
                },
                "tenant": {"id": str(context.tenant.id), "name": context.tenant.name},
            }
        )


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
        return Response(
            {
                "user": {
                    "id": str(accepted.user.id),
                    "email": accepted.user.email,
                    "display_name": accepted.user.display_name,
                },
                "tenant": {
                    "id": str(accepted.invitation.tenant.id),
                    "name": accepted.invitation.tenant.name,
                },
            }
        )


class InvitationListCreateView(APIView):
    @extend_schema(responses={200: InvitationSerializer(many=True), 403: OpenApiResponse(description="Owner required")})
    def get(self, request):  # type: ignore[no-untyped-def]
        context = require_installation_owner(request.user)
        invitations = Invitation.objects.filter(tenant=context.tenant)
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
        context = require_installation_owner(request.user)
        serializer = InvitationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = issue_invitation(
            tenant=context.tenant,
            actor=request.user,
            email=serializer.validated_data["email"],
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
        context = require_installation_owner(request.user)
        invitation = get_object_or_404(Invitation, pk=invitation_id, tenant=context.tenant)
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
        context = require_installation_owner(request.user)
        invitation = get_object_or_404(Invitation, pk=invitation_id, tenant=context.tenant)
        return Response(InvitationSerializer(resend_invitation(invitation=invitation, actor=request.user)).data)
