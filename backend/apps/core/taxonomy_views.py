from uuid import UUID

from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey

from .document_views import _msp_workspace, _organization_workspace
from .models import Taxonomy
from .taxonomies import (
    TaxonomyError,
    apply_migration,
    archive_taxonomy,
    create_local_term,
    create_taxonomy,
    migration_preview,
    revise_taxonomy,
    serialize_taxonomy,
    taxonomy_queryset,
)
from .taxonomy_serializers import (
    OrganizationTaxonomyTermWriteSerializer,
    TaxonomyCreateSerializer,
    TaxonomyMigrationSerializer,
    TaxonomyMigrationWriteSerializer,
    TaxonomyResultSerializer,
    TaxonomySerializer,
    TaxonomyVersionWriteSerializer,
)


def _response(tenant, *, organization=None) -> Response:  # type: ignore[no-untyped-def]
    rows = [serialize_taxonomy(item, organization=organization) for item in taxonomy_queryset(tenant)]
    return Response(TaxonomyResultSerializer({"results": rows, "count": len(rows)}).data)


def _owned(tenant, taxonomy_id: UUID) -> Taxonomy:  # type: ignore[no-untyped-def]
    return get_object_or_404(Taxonomy, id=taxonomy_id, tenant=tenant)


class MSPTaxonomyListCreateView(APIView):
    @extend_schema(operation_id="taxonomies_msp_list", responses={200: TaxonomyResultSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        workspace = _msp_workspace(request, PermissionKey.CUSTOM_FIELDS_VIEW)
        return _response(workspace.member.tenant)

    @extend_schema(
        operation_id="taxonomies_msp_create", request=TaxonomyCreateSerializer, responses={201: TaxonomySerializer}
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        workspace = _msp_workspace(request, PermissionKey.CUSTOM_FIELDS_MANAGE)
        serializer = TaxonomyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            taxonomy = create_taxonomy(
                tenant=workspace.member.tenant, actor_id=request.user.pk, **serializer.validated_data
            )
        except TaxonomyError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(TaxonomySerializer(serialize_taxonomy(taxonomy)).data, status=status.HTTP_201_CREATED)


class MSPTaxonomyDetailView(APIView):
    @extend_schema(
        operation_id="taxonomies_msp_revise",
        request=TaxonomyVersionWriteSerializer,
        responses={200: TaxonomySerializer},
    )
    def patch(self, request, taxonomy_id):  # type: ignore[no-untyped-def]
        workspace = _msp_workspace(request, PermissionKey.CUSTOM_FIELDS_MANAGE)
        serializer = TaxonomyVersionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            taxonomy = revise_taxonomy(
                taxonomy=_owned(workspace.member.tenant, taxonomy_id),
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except TaxonomyError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(TaxonomySerializer(serialize_taxonomy(taxonomy)).data)

    @extend_schema(operation_id="taxonomies_msp_archive", responses={204: None})
    def delete(self, request, taxonomy_id):  # type: ignore[no-untyped-def]
        workspace = _msp_workspace(request, PermissionKey.CUSTOM_FIELDS_MANAGE)
        archive_taxonomy(taxonomy=_owned(workspace.member.tenant, taxonomy_id), actor_id=request.user.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MSPTaxonomyMigrationView(APIView):
    @extend_schema(
        operation_id="taxonomies_msp_migration",
        request=TaxonomyMigrationWriteSerializer,
        responses={200: TaxonomyMigrationSerializer},
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        workspace = _msp_workspace(request, PermissionKey.CUSTOM_FIELDS_MANAGE)
        serializer = TaxonomyMigrationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = (
            apply_migration(tenant=workspace.member.tenant, actor_id=request.user.pk)
            if serializer.validated_data["apply"]
            else migration_preview(tenant=workspace.member.tenant)
        )
        return Response(TaxonomyMigrationSerializer(result).data)


class OrganizationTaxonomyListView(APIView):
    @extend_schema(operation_id="taxonomies_organization_list", responses={200: TaxonomyResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW)
        return _response(workspace.member.tenant, organization=workspace.organization)


class OrganizationTaxonomyLocalTermCreateView(APIView):
    @extend_schema(
        operation_id="taxonomies_organization_local_term_create",
        request=OrganizationTaxonomyTermWriteSerializer,
        responses={201: TaxonomySerializer},
    )
    def post(self, request, organization_entity_id, taxonomy_id):  # type: ignore[no-untyped-def]
        workspace = _organization_workspace(request, organization_entity_id, PermissionKey.CUSTOM_FIELDS_MANAGE)
        if workspace.organization is None:
            raise Http404
        serializer = OrganizationTaxonomyTermWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        taxonomy = _owned(workspace.member.tenant, taxonomy_id)
        try:
            create_local_term(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                taxonomy=taxonomy,
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except TaxonomyError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        taxonomy.refresh_from_db()
        return Response(
            TaxonomySerializer(serialize_taxonomy(taxonomy, organization=workspace.organization)).data,
            status=status.HTTP_201_CREATED,
        )
