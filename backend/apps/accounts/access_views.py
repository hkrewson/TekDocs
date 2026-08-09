from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import OrganizationAccessMode

from .access_collections import (
    access_collections_for_context,
    archive_access_collection,
    create_access_collection,
    update_access_collection,
)
from .access_control import (
    access_mode_organizations,
    assign_membership_role,
    assign_organization_staff,
    change_organization_access_mode,
    members_for_context,
    remove_organization_staff,
)
from .access_serializers import (
    AccessCollectionSerializer,
    AccessCollectionWriteSerializer,
    AccessControlCatalogSerializer,
    CustomRoleCreateSerializer,
    CustomRoleSerializer,
    CustomRoleUpdateSerializer,
    MemberRoleWriteSerializer,
    MemberSerializer,
    OrganizationAccessSerializer,
    OrganizationAccessWriteSerializer,
    OrganizationStaffWriteSerializer,
    ScopedRoleAssignmentSerializer,
    ScopedRoleAssignmentWriteSerializer,
)
from .custom_roles import (
    archive_custom_role,
    create_custom_role,
    create_scoped_assignment,
    custom_roles_for_context,
    remove_scoped_assignment,
    scoped_assignments_for_context,
    update_custom_role,
)
from .models import BuiltInRole, CustomRoleScope
from .policy import (
    PermissionKey,
    custom_assignable_permission_catalog,
    permission_catalog,
    require_permission,
    role_catalog,
)


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
            AccessControlCatalogSerializer(
                {
                    "permissions": permission_catalog(),
                    "roles": role_catalog(),
                    "custom_assignable_permissions": custom_assignable_permission_catalog(),
                }
            ).data
        )


class CustomRoleListCreateView(APIView):
    @extend_schema(responses={200: CustomRoleSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.CUSTOM_ROLES_VIEW)
        return Response(CustomRoleSerializer(custom_roles_for_context(context), many=True).data)

    @extend_schema(request=CustomRoleCreateSerializer, responses={201: CustomRoleSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        require_permission(request.user, PermissionKey.CUSTOM_ROLES_MANAGE)
        serializer = CustomRoleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = create_custom_role(
            actor=request.user,
            name=serializer.validated_data["name"],
            description=serializer.validated_data["description"],
            scope=CustomRoleScope(serializer.validated_data["scope"]),
            permissions=serializer.validated_data["permissions"],
        )
        return Response(CustomRoleSerializer(role).data, status=201)


class AccessCollectionListCreateView(APIView):
    @extend_schema(responses={200: AccessCollectionSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.ACCESS_COLLECTIONS_VIEW)
        return Response(AccessCollectionSerializer(access_collections_for_context(context), many=True).data)

    @extend_schema(request=AccessCollectionWriteSerializer, responses={201: AccessCollectionSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        require_permission(request.user, PermissionKey.ACCESS_COLLECTIONS_MANAGE)
        serializer = AccessCollectionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        collection = create_access_collection(
            actor=request.user,
            name=serializer.validated_data["name"],
            description=serializer.validated_data["description"],
            organization_entity_ids=serializer.validated_data["organization_ids"],
        )
        return Response(AccessCollectionSerializer(collection).data, status=201)


class AccessCollectionDetailView(APIView):
    @extend_schema(request=AccessCollectionWriteSerializer, responses={200: AccessCollectionSerializer})
    def patch(self, request, collection_id):  # type: ignore[no-untyped-def]
        require_permission(request.user, PermissionKey.ACCESS_COLLECTIONS_MANAGE)
        serializer = AccessCollectionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        collection = update_access_collection(
            actor=request.user,
            collection_id=collection_id,
            name=serializer.validated_data["name"],
            description=serializer.validated_data["description"],
            organization_entity_ids=serializer.validated_data["organization_ids"],
        )
        return Response(AccessCollectionSerializer(collection).data)

    @extend_schema(responses={200: AccessCollectionSerializer})
    def delete(self, request, collection_id):  # type: ignore[no-untyped-def]
        collection = archive_access_collection(actor=request.user, collection_id=collection_id)
        return Response(AccessCollectionSerializer(collection).data)


class CustomRoleDetailView(APIView):
    @extend_schema(request=CustomRoleUpdateSerializer, responses={200: CustomRoleSerializer})
    def patch(self, request, role_id):  # type: ignore[no-untyped-def]
        require_permission(request.user, PermissionKey.CUSTOM_ROLES_MANAGE)
        serializer = CustomRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = update_custom_role(
            actor=request.user,
            role_id=role_id,
            name=serializer.validated_data["name"],
            description=serializer.validated_data["description"],
            permissions=serializer.validated_data["permissions"],
        )
        return Response(CustomRoleSerializer(role).data)

    @extend_schema(responses={200: CustomRoleSerializer})
    def delete(self, request, role_id):  # type: ignore[no-untyped-def]
        return Response(CustomRoleSerializer(archive_custom_role(actor=request.user, role_id=role_id)).data)


class ScopedRoleAssignmentListCreateView(APIView):
    @extend_schema(responses={200: ScopedRoleAssignmentSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.CUSTOM_ROLES_VIEW)
        return Response(ScopedRoleAssignmentSerializer(scoped_assignments_for_context(context), many=True).data)

    @extend_schema(request=ScopedRoleAssignmentWriteSerializer, responses={201: ScopedRoleAssignmentSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        require_permission(request.user, PermissionKey.CUSTOM_ROLES_ASSIGN)
        serializer = ScopedRoleAssignmentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment, created = create_scoped_assignment(
            actor=request.user,
            member_user_id=serializer.validated_data["user_id"],
            role_id=serializer.validated_data["role_id"],
            organization_entity_id=serializer.validated_data["organization_id"],
            collection_id=serializer.validated_data["collection_id"],
        )
        return Response(ScopedRoleAssignmentSerializer(assignment).data, status=201 if created else 200)


class ScopedRoleAssignmentDetailView(APIView):
    @extend_schema(responses={204: None})
    def delete(self, request, assignment_id):  # type: ignore[no-untyped-def]
        remove_scoped_assignment(actor=request.user, assignment_id=assignment_id)
        return Response(status=204)


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
        require_permission(request.user, PermissionKey.MEMBERSHIPS_ASSIGN_ROLE)
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
        require_permission(request.user, PermissionKey.ORGANIZATIONS_MANAGE_ACCESS)
        serializer = OrganizationAccessWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = change_organization_access_mode(
            actor=request.user,
            organization_entity_id=organization_entity_id,
            access_mode=OrganizationAccessMode(serializer.validated_data["access_mode"]),
        )
        return Response(OrganizationAccessSerializer(organization).data)


class OrganizationStaffAssignmentView(APIView):
    @extend_schema(
        request=OrganizationStaffWriteSerializer,
        responses={
            200: OrganizationAccessSerializer,
            201: OrganizationAccessSerializer,
            400: OpenApiResponse(description="The owner cannot be assigned explicitly"),
            403: OpenApiResponse(description="Staff assignment permission and MFA required"),
            404: OpenApiResponse(description="Organization or tenant member not found"),
        },
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        require_permission(request.user, PermissionKey.ORGANIZATIONS_ASSIGN_STAFF)
        serializer = OrganizationStaffWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization, created = assign_organization_staff(
            actor=request.user,
            organization_entity_id=organization_entity_id,
            member_user_id=serializer.validated_data["user_id"],
        )
        return Response(OrganizationAccessSerializer(organization).data, status=201 if created else 200)


class OrganizationStaffAssignmentDetailView(APIView):
    @extend_schema(
        responses={
            200: OrganizationAccessSerializer,
            403: OpenApiResponse(description="Staff assignment permission and MFA required"),
            404: OpenApiResponse(description="Organization not found"),
        },
    )
    def delete(self, request, organization_entity_id, user_id):  # type: ignore[no-untyped-def]
        organization = remove_organization_staff(
            actor=request.user,
            organization_entity_id=organization_entity_id,
            member_user_id=user_id,
        )
        return Response(OrganizationAccessSerializer(organization).data)
