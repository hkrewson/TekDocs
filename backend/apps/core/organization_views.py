from uuid import UUID

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import require_installation_owner

from .models import Organization, Tenant
from .organizations import archive_organization, create_organization, update_organization
from .serializers import OrganizationSerializer, OrganizationWriteSerializer


def _organizations_for_tenant(tenant: Tenant) -> QuerySet[Organization]:
    return (
        Organization.scoped.for_tenant(tenant)
        .filter(entity__archived_at__isnull=True)
        .select_related("entity", "tenant")
        .prefetch_related("classifications")
        .order_by("entity__display_name", "entity_id")
    )


class OrganizationListCreateView(APIView):
    @extend_schema(
        responses={
            200: OrganizationSerializer(many=True),
            403: OpenApiResponse(description="Installation owner with MFA required"),
        }
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        context = require_installation_owner(request.user)
        return Response(OrganizationSerializer(_organizations_for_tenant(context.tenant), many=True).data)

    @extend_schema(
        request=OrganizationWriteSerializer,
        responses={
            201: OrganizationSerializer,
            400: OpenApiResponse(description="Invalid organization details"),
            403: OpenApiResponse(description="Installation owner with MFA required"),
        },
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        context = require_installation_owner(request.user)
        serializer = OrganizationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = create_organization(
            tenant=context.tenant,
            actor_id=request.user.pk,
            **serializer.validated_data,
        )
        organization = _organizations_for_tenant(context.tenant).get(pk=organization.pk)
        return Response(OrganizationSerializer(organization).data, status=201)


class OrganizationDetailView(APIView):
    def _get(self, *, tenant: Tenant, entity_id: UUID) -> Organization:
        return get_object_or_404(_organizations_for_tenant(tenant), entity_id=entity_id)

    @extend_schema(
        responses={
            200: OrganizationSerializer,
            403: OpenApiResponse(description="Installation owner with MFA required"),
            404: OpenApiResponse(description="Organization not found"),
        }
    )
    def get(self, request, entity_id):  # type: ignore[no-untyped-def]
        context = require_installation_owner(request.user)
        return Response(OrganizationSerializer(self._get(tenant=context.tenant, entity_id=entity_id)).data)

    @extend_schema(
        request=OrganizationWriteSerializer,
        responses={
            200: OrganizationSerializer,
            400: OpenApiResponse(description="Invalid organization details"),
            403: OpenApiResponse(description="Installation owner with MFA required"),
            404: OpenApiResponse(description="Organization not found"),
        },
    )
    def patch(self, request, entity_id):  # type: ignore[no-untyped-def]
        context = require_installation_owner(request.user)
        organization = self._get(tenant=context.tenant, entity_id=entity_id)
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
        organization = self._get(tenant=context.tenant, entity_id=entity_id)
        return Response(OrganizationSerializer(organization).data)

    @extend_schema(
        request=None,
        responses={
            204: OpenApiResponse(description="Organization archived"),
            403: OpenApiResponse(description="Installation owner with MFA required"),
            404: OpenApiResponse(description="Organization not found"),
        },
    )
    def delete(self, request, entity_id):  # type: ignore[no-untyped-def]
        context = require_installation_owner(request.user)
        organization = self._get(tenant=context.tenant, entity_id=entity_id)
        archive_organization(organization=organization, actor_id=request.user.pk)
        return Response(status=204)
