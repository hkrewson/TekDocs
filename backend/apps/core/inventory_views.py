from __future__ import annotations

from uuid import UUID

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission, require_permission

from .inventory import (
    InventoryError,
    assets_for_scope,
    create_client_asset,
    model_choices_for_client,
    require_client,
    vendors_for_scope,
)
from .models import (
    CatalogModel,
    CatalogModelRevision,
    ClientAsset,
    ClientAssetDocumentProvenance,
    DocumentPublicationArtifact,
    Organization,
)
from .publications import PublicationConflict, read_publication_artifact, verify_publication
from .workspaces import ResolvedWorkspace, resolve_organization_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class ClientAssetWriteSerializer(StrictSerializer):
    model_id = serializers.UUIDField()
    name = serializers.CharField(max_length=240, allow_blank=True, required=False, default="", trim_whitespace=True)


class CatalogModelChoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    model_number = serializers.CharField()
    product_id = serializers.UUIDField(source="product.entity_id")
    product_name = serializers.CharField(source="product.entity.display_name")
    kind = serializers.CharField(source="product.kind")
    supplier_id = serializers.UUIDField(source="organization.entity_id")
    supplier_name = serializers.CharField(source="organization.entity.display_name")
    revision = serializers.SerializerMethodField()
    specification_version_id = serializers.SerializerMethodField()
    specifications = serializers.SerializerMethodField()

    def _current(self, item: CatalogModel) -> CatalogModelRevision | None:
        revisions = list(item.revisions.all())
        return revisions[-1] if revisions else None

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_revision(self, item: CatalogModel) -> int | None:
        current = self._current(item)
        return current.revision if current is not None else None

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_specification_version_id(self, item: CatalogModel) -> UUID | None:
        current = self._current(item)
        return current.specification_version_id if current is not None else None

    @extend_schema_field(serializers.JSONField())
    def get_specifications(self, item: CatalogModel) -> dict[str, object]:
        current = self._current(item)
        return current.specifications if current is not None else {}


class CatalogModelChoiceResultSerializer(serializers.Serializer):
    results = CatalogModelChoiceSerializer(many=True)


class AssetPublicationArtifactSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    kind = serializers.CharField()
    filename = serializers.CharField(source="original_filename")
    media_type = serializers.CharField()
    size = serializers.IntegerField()
    checksum = serializers.CharField()


class AssetDocumentSummarySerializer(serializers.Serializer):
    publication_id = serializers.UUIDField(source="publication.entity_id")
    source_document_id = serializers.UUIDField(source="publication.document.entity_id")
    title = serializers.CharField(source="publication.title")
    category = serializers.CharField(source="publication.category")
    reason = serializers.CharField(source="publication.reason")
    content_digest = serializers.CharField()
    published_at = serializers.DateTimeField(source="publication.published_at")
    verification = serializers.SerializerMethodField()
    artifacts = AssetPublicationArtifactSerializer(source="publication.artifacts", many=True)

    @extend_schema_field(serializers.DictField(child=serializers.BooleanField()))
    def get_verification(self, item: ClientAssetDocumentProvenance) -> dict[str, bool]:
        return verify_publication(item.publication)


class AssetDocumentDetailSerializer(AssetDocumentSummarySerializer):
    sanitized_html = serializers.CharField(source="publication.sanitized_html")


class ClientAssetSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    kind = serializers.CharField(source="product.kind")
    supplier_id = serializers.UUIDField(source="supplier.entity_id")
    supplier_name = serializers.CharField(source="supplier.entity.display_name")
    product_id = serializers.UUIDField(source="product.entity_id")
    product_name = serializers.CharField(source="product.entity.display_name")
    model_id = serializers.UUIDField(source="model.entity_id")
    model_name = serializers.CharField(source="model.entity.display_name")
    model_number = serializers.CharField(source="model.model_number")
    model_revision_id = serializers.UUIDField()
    model_revision = serializers.IntegerField(source="model_revision.revision")
    specification_version_id = serializers.UUIDField()
    specification_definition_id = serializers.UUIDField(source="specification_version.definition_id")
    specification_version = serializers.IntegerField(source="specification_version.version")
    specifications = serializers.JSONField()
    provenance_checksum = serializers.CharField()
    documents = AssetDocumentSummarySerializer(source="document_provenance", many=True)
    created_at = serializers.DateTimeField()


class ClientAssetResultSerializer(serializers.Serializer):
    results = ClientAssetSerializer(many=True)
    count = serializers.IntegerField()
    can_manage = serializers.BooleanField()


class DerivedVendorSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    legal_name = serializers.CharField()
    website = serializers.CharField()
    classifications = serializers.SerializerMethodField()
    asset_count = serializers.IntegerField()

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_classifications(self, item: Organization) -> list[str]:
        return sorted(record.kind for record in item.classifications.all())


class DerivedVendorResultSerializer(serializers.Serializer):
    results = DerivedVendorSerializer(many=True)
    count = serializers.IntegerField()


def _workspace(request, organization_entity_id: UUID, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    workspace = resolve_organization_workspace(request.user, entity_id=organization_entity_id)
    require_permission(request.user, permission, organization=workspace.organization)
    if workspace.organization is None:
        raise PermissionDenied("A client organization workspace is required.")
    try:
        require_client(workspace.organization)
    except InventoryError as exc:
        raise PermissionDenied(str(exc)) from exc
    return workspace


def _asset(workspace: ResolvedWorkspace, asset_entity_id: UUID) -> ClientAsset:
    return get_object_or_404(assets_for_scope(workspace.data_scope), entity_id=asset_entity_id)


class ClientAssetListCreateView(APIView):
    @extend_schema(operation_id="organization_client_assets_list", responses={200: ClientAssetResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        assets = assets_for_scope(workspace.data_scope)
        return Response(
            ClientAssetResultSerializer(
                {
                    "results": assets,
                    "count": assets.count(),
                    "can_manage": context_has_permission(
                        workspace.member, PermissionKey.ASSETS_EDIT, organization=workspace.organization
                    ),
                }
            ).data
        )

    @extend_schema(request=ClientAssetWriteSerializer, responses={201: ClientAssetSerializer})
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = ClientAssetWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if workspace.organization is None:
            raise PermissionDenied("A client organization workspace is required.")
        try:
            asset = create_client_asset(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                model_entity_id=serializer.validated_data["model_id"],
                name=serializer.validated_data["name"],
            )
        except (InventoryError, CatalogModel.DoesNotExist) as exc:
            raise serializers.ValidationError({"detail": "The selected supplier model is unavailable."}) from exc
        return Response(ClientAssetSerializer(asset).data, status=201)


class ClientAssetDetailView(APIView):
    @extend_schema(operation_id="organization_client_assets_retrieve", responses={200: ClientAssetSerializer})
    def get(self, request, organization_entity_id, asset_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        return Response(ClientAssetSerializer(_asset(workspace, asset_entity_id)).data)


class ClientAssetModelChoiceListView(APIView):
    @extend_schema(
        operation_id="organization_client_asset_model_choices_list",
        parameters=[OpenApiParameter("q", str)],
        responses={200: CatalogModelChoiceResultSerializer},
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        query = str(request.query_params.get("q", "")).strip()[:240]
        results = model_choices_for_client(workspace.data_scope, query=query)[:50]
        return Response(CatalogModelChoiceResultSerializer({"results": results}).data)


class ClientAssetDocumentDetailView(APIView):
    @extend_schema(
        operation_id="organization_client_asset_document_retrieve", responses={200: AssetDocumentDetailSerializer}
    )
    def get(self, request, organization_entity_id, asset_entity_id, publication_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        asset = _asset(workspace, asset_entity_id)
        provenance = get_object_or_404(
            asset.document_provenance.select_related(
                "publication", "publication__entity", "publication__document__entity"
            ).prefetch_related("publication__artifacts__entity"),
            publication__entity_id=publication_entity_id,
        )
        return Response(AssetDocumentDetailSerializer(provenance).data)


class ClientAssetDocumentArtifactDownloadView(APIView):
    @extend_schema(
        operation_id="organization_client_asset_document_artifact_download",
        responses={200: OpenApiResponse(description="Retained publication artifact")},
    )
    def get(  # type: ignore[no-untyped-def]
        self,
        request,
        organization_entity_id,
        asset_entity_id,
        publication_entity_id,
        artifact_entity_id,
    ) -> HttpResponse:
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        asset = _asset(workspace, asset_entity_id)
        provenance = get_object_or_404(
            asset.document_provenance.select_related("publication"),
            publication__entity_id=publication_entity_id,
        )
        artifact = get_object_or_404(
            DocumentPublicationArtifact.objects.filter(publication=provenance.publication).select_related("entity"),
            entity_id=artifact_entity_id,
        )
        try:
            content = read_publication_artifact(artifact)
        except PublicationConflict as conflict:
            return HttpResponse(str(conflict), status=409, content_type="text/plain; charset=utf-8")
        response = HttpResponse(content, content_type=artifact.media_type)
        disposition = content_disposition_header(True, artifact.original_filename)
        if disposition is not None:
            response["Content-Disposition"] = disposition
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ClientVendorListView(APIView):
    @extend_schema(operation_id="organization_client_vendors_list", responses={200: DerivedVendorResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        vendors = vendors_for_scope(workspace.data_scope)
        return Response(DerivedVendorResultSerializer({"results": vendors, "count": vendors.count()}).data)
