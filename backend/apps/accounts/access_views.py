from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import OrganizationAccessMode

from .access_control import (
    access_mode_organizations,
    assign_membership_role,
    change_organization_access_mode,
    members_for_context,
)
from .access_serializers import (
    AccessControlCatalogSerializer,
    MemberRoleWriteSerializer,
    MemberSerializer,
    OrganizationAccessSerializer,
    OrganizationAccessWriteSerializer,
)
from .models import BuiltInRole
from .policy import PermissionKey, permission_catalog, require_permission, role_catalog


class AccessControlCatalogView(APIView):
    @extend_schema(
        responses={
            200: AccessControlCatalogSerializer,
            403: OpenApiResponse(description="Member administration permission required"),
        }
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        require_permission(request.user, PermissionKey.MEMBERSHIPS_VIEW)
        return Response(
            AccessControlCatalogSerializer({"permissions": permission_catalog(), "roles": role_catalog()}).data
        )


class MemberListView(APIView):
    @extend_schema(
        responses={
            200: MemberSerializer(many=True),
            403: OpenApiResponse(description="Member administration permission required"),
        }
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.MEMBERSHIPS_VIEW)
        return Response(MemberSerializer(members_for_context(context), many=True).data)


class MemberRoleView(APIView):
    @extend_schema(
        request=MemberRoleWriteSerializer,
        responses={
            200: MemberSerializer,
            400: OpenApiResponse(description="Invalid or non-assignable role"),
            403: OpenApiResponse(description="Role assignment permission and MFA required"),
            404: OpenApiResponse(description="Tenant member not found"),
        },
    )
    def patch(self, request, user_id):  # type: ignore[no-untyped-def]
        serializer = MemberRoleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = assign_membership_role(
            actor=request.user,
            member_user_id=user_id,
            role=BuiltInRole(serializer.validated_data["role"]),
        )
        return Response(
            MemberSerializer(
                {
                    "id": membership.user_id,
                    "display_name": membership.user.display_name,
                    "email": membership.user.email,
                    "role": membership.role,
                    "is_owner": False,
                    "joined_at": membership.created_at,
                }
            ).data
        )


class OrganizationAccessListView(APIView):
    @extend_schema(
        responses={
            200: OrganizationAccessSerializer(many=True),
            403: OpenApiResponse(description="Organization access administration permission and MFA required"),
        }
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.ORGANIZATIONS_MANAGE_ACCESS)
        return Response(OrganizationAccessSerializer(access_mode_organizations(context), many=True).data)


class OrganizationAccessDetailView(APIView):
    @extend_schema(
        request=OrganizationAccessWriteSerializer,
        responses={
            200: OrganizationAccessSerializer,
            400: OpenApiResponse(description="Invalid access mode"),
            403: OpenApiResponse(description="Organization access administration permission and MFA required"),
            404: OpenApiResponse(description="Organization not found"),
        },
    )
    def patch(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        serializer = OrganizationAccessWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = change_organization_access_mode(
            actor=request.user,
            organization_entity_id=organization_entity_id,
            access_mode=OrganizationAccessMode(serializer.validated_data["access_mode"]),
        )
        return Response(OrganizationAccessSerializer(organization).data)
