from uuid import UUID

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import InstallationMemberContext, PermissionKey, accessible_organizations, require_permission

from .models import Organization
from .organizations import archive_organization, create_organization, update_organization
from .serializers import OrganizationSerializer, OrganizationWriteSerializer


def _organizations_for_context(context: InstallationMemberContext, permission: PermissionKey) -> QuerySet[Organization]:
    return (
        accessible_organizations(context, permission)
        .select_related("entity", "tenant")
        .prefetch_related("classifications")
        .order_by("entity__display_name", "entity_id")
    )


class OrganizationListCreateView(APIView):
    @extend_schema(
        responses={
            200: OrganizationSerializer(many=True),
            403: OpenApiResponse(description="Organization view permission required"),
        }
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.ORGANIZATIONS_VIEW)
        return Response(
            OrganizationSerializer(
                _organizations_for_context(context, PermissionKey.ORGANIZATIONS_VIEW), many=True
            ).data
        )

    @extend_schema(
        request=OrganizationWriteSerializer,
        responses={
            201: OrganizationSerializer,
            400: OpenApiResponse(description="Invalid organization details"),
            403: OpenApiResponse(description="Organization creation permission and MFA required"),
        },
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.ORGANIZATIONS_CREATE)
        serializer = OrganizationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = create_organization(
            tenant=context.tenant,
            actor_id=request.user.pk,
            **serializer.validated_data,
        )
        organization = _organizations_for_context(context, PermissionKey.ORGANIZATIONS_VIEW).get(pk=organization.pk)
        return Response(OrganizationSerializer(organization).data, status=201)


class OrganizationDetailView(APIView):
    def _get(self, *, context: InstallationMemberContext, permission: PermissionKey, entity_id: UUID) -> Organization:
        return get_object_or_404(_organizations_for_context(context, permission), entity_id=entity_id)

    @extend_schema(
        responses={
            200: OrganizationSerializer,
            403: OpenApiResponse(description="Organization view permission required"),
            404: OpenApiResponse(description="Organization not found"),
        }
    )
    def get(self, request, entity_id):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.ORGANIZATIONS_VIEW)
        return Response(
            OrganizationSerializer(
                self._get(context=context, permission=PermissionKey.ORGANIZATIONS_VIEW, entity_id=entity_id)
            ).data
        )

    @extend_schema(
        request=OrganizationWriteSerializer,
        responses={
            200: OrganizationSerializer,
            400: OpenApiResponse(description="Invalid organization details"),
            403: OpenApiResponse(description="Organization edit permission and MFA required"),
            404: OpenApiResponse(description="Organization not found"),
        },
    )
    def patch(self, request, entity_id):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.ORGANIZATIONS_EDIT)
        organization = self._get(context=context, permission=PermissionKey.ORGANIZATIONS_EDIT, entity_id=entity_id)
        serializer = OrganizationWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changes = {
            "name": organization.entity.display_name,
            "legal_name": organization.legal_name,
            "website": organization.website,
            "classifications": [classification.kind for classification in organization.classifications.all()],
            **serializer.validated_data,
        }
        update_organization(
            organization=organization,
            actor_id=request.user.pk,
            **changes,
        )
        organization = self._get(context=context, permission=PermissionKey.ORGANIZATIONS_EDIT, entity_id=entity_id)
        return Response(OrganizationSerializer(organization).data)

    @extend_schema(
        request=None,
        responses={
            204: OpenApiResponse(description="Organization archived"),
            403: OpenApiResponse(description="Organization archive permission and MFA required"),
            404: OpenApiResponse(description="Organization not found"),
        },
    )
    def delete(self, request, entity_id):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.ORGANIZATIONS_ARCHIVE)
        organization = self._get(context=context, permission=PermissionKey.ORGANIZATIONS_ARCHIVE, entity_id=entity_id)
        archive_organization(organization=organization, actor_id=request.user.pk)
        return Response(status=204)
