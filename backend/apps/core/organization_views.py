from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import InstallationMemberContext, PermissionKey, accessible_organizations, require_permission

from .models import Organization
from .organizations import archive_organization, create_organization, update_organization
from .serializers import (
    OrganizationQuerySerializer,
    OrganizationResultSerializer,
    OrganizationSerializer,
    OrganizationWriteSerializer,
)


def _organizations_for_context(context: InstallationMemberContext, permission: PermissionKey) -> QuerySet[Organization]:
    return (
        accessible_organizations(context, permission)
        .select_related("entity", "tenant")
        .prefetch_related("classifications")
    )


ORGANIZATION_ORDERING_FIELDS = {
    "name": "entity__display_name",
    "legal_name": "legal_name",
    "website": "website",
}


def _organization_page(
    context: InstallationMemberContext,
    permission: PermissionKey,
    *,
    q: str,
    classification: str,
    ordering: str,
    page: int,
    page_size: int,
) -> tuple[list[Organization], int, bool]:
    records = _organizations_for_context(context, permission)
    if q:
        records = records.filter(
            Q(entity__display_name__icontains=q)
            | Q(legal_name__icontains=q)
            | Q(website__icontains=q)
        )
    if classification:
        records = records.filter(classifications__kind=classification)
    descending = ordering.startswith("-")
    order_by = ORGANIZATION_ORDERING_FIELDS[ordering.removeprefix("-")]
    if descending:
        order_by = f"-{order_by}"
    records = records.order_by(order_by, "entity_id").distinct()
    count = records.count()
    offset = (page - 1) * page_size
    selected = list(records[offset : offset + page_size + 1])
    return selected[:page_size], count, len(selected) > page_size


class OrganizationListCreateView(APIView):
    @extend_schema(
        operation_id="organizations_list",
        parameters=[
            OpenApiParameter("q", str),
            OpenApiParameter("classification", str),
            OpenApiParameter("ordering", str),
            OpenApiParameter("page", int),
            OpenApiParameter("page_size", int),
        ],
        responses={
            200: OrganizationResultSerializer,
            403: OpenApiResponse(description="Organization view permission required"),
        }
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        context = require_permission(request.user, PermissionKey.ORGANIZATIONS_VIEW)
        query = OrganizationQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        records, count, has_more = _organization_page(context, PermissionKey.ORGANIZATIONS_VIEW, **values)
        return Response(OrganizationResultSerializer({
            "results": records,
            "page": values["page"],
            "page_size": values["page_size"],
            "count": count,
            "has_more": has_more,
        }).data)

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
        operation_id="organizations_retrieve",
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
        try:
            update_organization(
                organization=organization,
                actor_id=request.user.pk,
                **changes,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"classifications": exc.messages}) from exc
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
