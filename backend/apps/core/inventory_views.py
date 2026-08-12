from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission, require_permission

from .asset_csv import (
    AssetCsvError,
    apply_assets_csv,
    export_assets_csv,
    preview_assets_csv,
    template_csv,
)
from .collection_pagination import BoundedCollectionQuerySerializer, paginate
from .inventory import (
    InventoryError,
    assets_for_scope,
    assign_hardware,
    assignment_choices,
    bulk_update_assets,
    create_client_asset,
    dispose_hardware,
    lifecycle_events,
    model_choices_for_client,
    require_operational_owner,
    unassign_hardware,
    update_hardware_details,
    vendors_for_scope,
)
from .models import (
    CatalogModel,
    CatalogModelRevision,
    ClientAsset,
    ClientAssetDocumentProvenance,
    ClientHardwareAsset,
    DocumentPublicationArtifact,
    HardwareAcquisitionMethod,
    HardwareDisposalMethod,
    HardwareLifecycleState,
    NetworkMACAddress,
    Organization,
)
from .network_endpoints import NetworkEndpointError, create_mac_address, update_mac_address
from .publications import PublicationConflict, read_publication_artifact, verify_publication
from .software_inventory import SoftwareInventoryError
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class ClientAssetWriteSerializer(StrictSerializer):
    model_id = serializers.UUIDField()
    name = serializers.CharField(max_length=240, allow_blank=True, required=False, default="", trim_whitespace=True)


class ClientAssetBulkWriteSerializer(StrictSerializer):
    asset_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=100,
        allow_empty=False,
    )
    action = serializers.ChoiceField(choices=("set_hardware_state", "archive"))
    lifecycle_state = serializers.ChoiceField(
        choices=[
            HardwareLifecycleState.IN_STOCK,
            HardwareLifecycleState.IN_SERVICE,
            HardwareLifecycleState.REPAIR,
            HardwareLifecycleState.RETIRED,
        ],
        required=False,
    )

    def validate(self, attrs):  # type: ignore[no-untyped-def]
        attrs = super().validate(attrs)
        if len(set(attrs["asset_ids"])) != len(attrs["asset_ids"]):
            raise serializers.ValidationError({"asset_ids": "Choose each asset only once."})
        if attrs["action"] == "set_hardware_state" and "lifecycle_state" not in attrs:
            raise serializers.ValidationError({"lifecycle_state": "Choose a hardware lifecycle state."})
        if attrs["action"] == "archive" and "lifecycle_state" in attrs:
            raise serializers.ValidationError({"lifecycle_state": "Archive does not accept a lifecycle state."})
        return attrs


class ClientAssetBulkResultSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("set_hardware_state", "archive"))
    processed = serializers.IntegerField(min_value=1, max_value=100)


class AssetCsvUploadSerializer(StrictSerializer):
    file = serializers.FileField()

    def validate_file(self, value):  # type: ignore[no-untyped-def]
        if value.content_type not in {
            "text/csv",
            "application/csv",
            "application/vnd.ms-excel",
            "application/octet-stream",
            "text/plain",
        }:
            raise serializers.ValidationError("Choose a CSV file.")
        return value


class AssetCsvApplySerializer(AssetCsvUploadSerializer):
    preview_token = serializers.CharField(max_length=4096)


class AssetCsvPreviewRowSerializer(serializers.Serializer):
    row = serializers.IntegerField()
    asset_id = serializers.UUIDField()
    name = serializers.CharField()
    kind = serializers.ChoiceField(choices=("hardware", "software"))
    action = serializers.ChoiceField(choices=("create", "update", "skip"))
    changes = serializers.ListField(child=serializers.CharField())


class AssetCsvErrorSerializer(serializers.Serializer):
    row = serializers.IntegerField()
    message = serializers.CharField()


class AssetCsvPreviewSerializer(serializers.Serializer):
    schema_version = serializers.CharField()
    rows = AssetCsvPreviewRowSerializer(many=True)
    errors = AssetCsvErrorSerializer(many=True)
    summary = serializers.DictField(child=serializers.IntegerField())
    preview_token = serializers.CharField(allow_null=True)


class AssetCsvApplyResultSerializer(serializers.Serializer):
    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    skipped = serializers.IntegerField()


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


class HardwareAssignmentSerializer(serializers.Serializer):
    person_id = serializers.UUIDField(source="assigned_person_id", allow_null=True)
    person_name = serializers.CharField(source="assigned_person.person.entity.display_name", allow_null=True)
    site_id = serializers.UUIDField(source="assigned_site_id", allow_null=True)
    site_name = serializers.CharField(source="assigned_site.entity.display_name", allow_null=True)
    location_id = serializers.UUIDField(source="assigned_location_id", allow_null=True)
    location_name = serializers.CharField(source="assigned_location.entity.display_name", allow_null=True)
    assigned_at = serializers.DateTimeField(allow_null=True)


class HardwareProfileSerializer(serializers.Serializer):
    serial_number = serializers.CharField()
    asset_tag = serializers.CharField()
    lifecycle_state = serializers.CharField()
    acquired_on = serializers.DateField(allow_null=True)
    acquisition_method = serializers.CharField()
    acquisition_reference = serializers.CharField()
    warranty_provider = serializers.CharField()
    warranty_starts_on = serializers.DateField(allow_null=True)
    warranty_ends_on = serializers.DateField(allow_null=True)
    warranty_reference = serializers.CharField()
    assignment = HardwareAssignmentSerializer(source="*")
    disposed_on = serializers.DateField(allow_null=True)
    disposal_method = serializers.CharField()
    disposal_reason = serializers.CharField()


class HardwareLifecycleEventSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    event_type = serializers.CharField()
    from_state = serializers.CharField()
    to_state = serializers.CharField()
    person_name = serializers.CharField(source="person.person.entity.display_name", allow_null=True)
    site_name = serializers.CharField(source="site.entity.display_name", allow_null=True)
    location_name = serializers.CharField(source="location.entity.display_name", allow_null=True)
    occurred_at = serializers.DateTimeField()


class HardwareDetailWriteSerializer(StrictSerializer):
    serial_number = serializers.CharField(max_length=160, allow_blank=True, required=False)
    asset_tag = serializers.CharField(max_length=120, allow_blank=True, required=False)
    lifecycle_state = serializers.ChoiceField(
        choices=[choice for choice in HardwareLifecycleState.values if choice != HardwareLifecycleState.DISPOSED],
        required=False,
    )
    acquired_on = serializers.DateField(allow_null=True, required=False)
    acquisition_method = serializers.ChoiceField(choices=["", *HardwareAcquisitionMethod.values], required=False)
    acquisition_reference = serializers.CharField(max_length=240, allow_blank=True, required=False)
    warranty_provider = serializers.CharField(max_length=160, allow_blank=True, required=False)
    warranty_starts_on = serializers.DateField(allow_null=True, required=False)
    warranty_ends_on = serializers.DateField(allow_null=True, required=False)
    warranty_reference = serializers.CharField(max_length=240, allow_blank=True, required=False)


class HardwareAssignmentWriteSerializer(StrictSerializer):
    person_id = serializers.UUIDField(allow_null=True, required=False)
    site_id = serializers.UUIDField(allow_null=True, required=False)
    location_id = serializers.UUIDField(allow_null=True, required=False)


class HardwareDisposalWriteSerializer(StrictSerializer):
    disposed_on = serializers.DateField()
    method = serializers.ChoiceField(choices=HardwareDisposalMethod.values)
    reason = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")


class HardwareAssignmentChoicesSerializer(serializers.Serializer):
    people = serializers.ListField()
    sites = serializers.ListField()
    locations = serializers.ListField()


class SoftwareInstallationSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    installed_version = serializers.CharField()
    installed_on = serializers.DateField(allow_null=True)
    last_verified_on = serializers.DateField(allow_null=True)
    site_id = serializers.UUIDField(allow_null=True)
    site_name = serializers.CharField(source="site.entity.display_name", allow_null=True)


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
    hardware = HardwareProfileSerializer(allow_null=True)
    mac_addresses = serializers.SerializerMethodField()
    software_installation = SoftwareInstallationSummarySerializer(allow_null=True)
    created_at = serializers.DateTimeField()

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_mac_addresses(self, asset: ClientAsset) -> list[dict[str, object]]:
        return [
            {"id": item.entity_id, "address": item.address, "description": item.description}
            for item in asset.network_mac_addresses.all()
        ]


class AssetMACAddressWriteSerializer(StrictSerializer):
    address = serializers.CharField(max_length=17, trim_whitespace=True)
    description = serializers.CharField(max_length=4000, allow_blank=True, required=False, default="")


class AssetMACAddressSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    address = serializers.CharField()
    description = serializers.CharField()


class ClientAssetResultSerializer(serializers.Serializer):
    results = ClientAssetSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    can_manage = serializers.BooleanField()
    can_view_relationships = serializers.BooleanField()
    can_create_relationships = serializers.BooleanField()
    can_archive_relationships = serializers.BooleanField()


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


def _workspace(request, organization_entity_id: UUID | None, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    workspace = (
        resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        if organization_entity_id is not None
        else resolve_msp_workspace(request.user)
    )
    require_permission(request.user, permission, organization=workspace.organization)
    try:
        require_operational_owner(workspace.organization)
    except InventoryError as exc:
        raise PermissionDenied(str(exc)) from exc
    return workspace


def _asset(workspace: ResolvedWorkspace, asset_entity_id: UUID) -> ClientAsset:
    return get_object_or_404(assets_for_scope(workspace.data_scope), entity_id=asset_entity_id)


class ClientAssetListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: ClientAssetResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        query = BoundedCollectionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = paginate(assets_for_scope(workspace.data_scope), **query.validated_data)
        return Response(
            ClientAssetResultSerializer(
                {
                    "results": page.records,
                    "page": page.page,
                    "page_size": page.page_size,
                    "count": page.count,
                    "has_more": page.has_more,
                    "can_manage": context_has_permission(
                        workspace.member, PermissionKey.ASSETS_EDIT, organization=workspace.organization
                    ),
                    "can_view_relationships": context_has_permission(
                        workspace.member, PermissionKey.RELATIONSHIPS_VIEW, organization=workspace.organization
                    ),
                    "can_create_relationships": context_has_permission(
                        workspace.member, PermissionKey.RELATIONSHIPS_CREATE, organization=workspace.organization
                    ),
                    "can_archive_relationships": context_has_permission(
                        workspace.member, PermissionKey.RELATIONSHIPS_ARCHIVE, organization=workspace.organization
                    ),
                }
            ).data
        )

    @extend_schema(request=ClientAssetWriteSerializer, responses={201: ClientAssetSerializer})
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = ClientAssetWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
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


class ClientAssetBulkView(APIView):
    @extend_schema(request=ClientAssetBulkWriteSerializer, responses={200: ClientAssetBulkResultSerializer})
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = ClientAssetBulkWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            processed = bulk_update_assets(
                scope=workspace.data_scope,
                actor_id=request.user.pk,
                asset_entity_ids=values["asset_ids"],
                action=values["action"],
                lifecycle_state=values.get("lifecycle_state"),
            )
        except InventoryError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(ClientAssetBulkResultSerializer({"action": values["action"], "processed": processed}).data)


class ClientAssetCsvTemplateView(APIView):
    @extend_schema(responses={200: OpenApiResponse(description="Canonical TekDocs asset CSV template")})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        response = HttpResponse(template_csv(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="tekdocs-assets-template.csv"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ClientAssetCsvExportView(APIView):
    @extend_schema(responses={200: OpenApiResponse(description="Workspace-scoped asset CSV export")})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        response = HttpResponse(export_assets_csv(workspace.data_scope), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="tekdocs-assets.csv"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ClientAssetCsvPreviewView(APIView):
    @extend_schema(request=AssetCsvUploadSerializer, responses={200: AssetCsvPreviewSerializer})
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = AssetCsvUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            preview = preview_assets_csv(scope=workspace.data_scope, content=serializer.validated_data["file"].read())
        except AssetCsvError as exc:
            raise serializers.ValidationError({"file": str(exc)}) from exc
        return Response(AssetCsvPreviewSerializer(preview).data)


class ClientAssetCsvApplyView(APIView):
    @extend_schema(request=AssetCsvApplySerializer, responses={200: AssetCsvApplyResultSerializer})
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = AssetCsvApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = apply_assets_csv(
                scope=workspace.data_scope,
                content=serializer.validated_data["file"].read(),
                preview_token=serializer.validated_data["preview_token"],
                actor_id=request.user.pk,
                tenant=workspace.member.tenant,
                organization=workspace.organization,
            )
        except (AssetCsvError, InventoryError, SoftwareInventoryError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(AssetCsvApplyResultSerializer(result).data)


class ClientAssetDetailView(APIView):
    @extend_schema(responses={200: ClientAssetSerializer})
    def get(self, request, organization_entity_id, asset_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        return Response(ClientAssetSerializer(_asset(workspace, asset_entity_id)).data)


class ClientAssetMACAddressListCreateView(APIView):
    @extend_schema(responses={200: AssetMACAddressSerializer(many=True)})
    def get(self, request, organization_entity_id=None, asset_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        asset = _asset(workspace, asset_entity_id)
        if asset.product.kind != "hardware":
            raise serializers.ValidationError({"detail": "MAC addresses are available only for physical assets."})
        return Response(AssetMACAddressSerializer(asset.network_mac_addresses.all(), many=True).data)

    @extend_schema(request=AssetMACAddressWriteSerializer, responses={201: AssetMACAddressSerializer})
    def post(self, request, organization_entity_id=None, asset_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        asset = _asset(workspace, asset_entity_id)
        if asset.product.kind != "hardware":
            raise serializers.ValidationError({"detail": "MAC addresses are available only for physical assets."})
        serializer = AssetMACAddressWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = create_mac_address(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                interface_entity_id=None,
                hardware_asset_entity_id=asset.entity_id,
                **serializer.validated_data,
            )
        except (NetworkEndpointError, DjangoValidationError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(AssetMACAddressSerializer(record).data, status=201)


class ClientAssetMACAddressDetailView(APIView):
    @extend_schema(request=AssetMACAddressWriteSerializer, responses={200: AssetMACAddressSerializer})
    def patch(self, request, organization_entity_id=None, asset_entity_id=None, mac_address_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        asset = _asset(workspace, asset_entity_id)
        try:
            record = asset.network_mac_addresses.select_related("entity").get(entity_id=mac_address_entity_id)
        except NetworkMACAddress.DoesNotExist as exc:
            raise PermissionDenied("The selected MAC address is unavailable for this asset.") from exc
        serializer = AssetMACAddressWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            updated = update_mac_address(
                record=record,
                actor_id=request.user.pk,
                values={**serializer.validated_data, "hardware_asset_entity_id": asset.entity_id},
            )
        except (NetworkEndpointError, DjangoValidationError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(AssetMACAddressSerializer(updated).data)


class ClientHardwareDetailView(APIView):
    @extend_schema(responses={200: HardwareProfileSerializer})
    def get(self, request, organization_entity_id, asset_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        asset = _asset(workspace, asset_entity_id)
        try:
            return Response(HardwareProfileSerializer(asset.hardware).data)
        except ClientHardwareAsset.DoesNotExist as exc:
            raise serializers.ValidationError({"detail": "Hardware lifecycle is unavailable for this asset."}) from exc

    @extend_schema(request=HardwareDetailWriteSerializer, responses={200: HardwareProfileSerializer})
    def patch(self, request, organization_entity_id, asset_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = HardwareDetailWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            profile = update_hardware_details(
                asset=_asset(workspace, asset_entity_id),
                actor_id=request.user.pk,
                values=serializer.validated_data,
            )
        except InventoryError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(HardwareProfileSerializer(profile).data)


class ClientHardwareAssignmentChoicesView(APIView):
    @extend_schema(
        responses={200: HardwareAssignmentChoicesSerializer},
    )
    def get(self, request, organization_entity_id, asset_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        people, sites, locations = assignment_choices(_asset(workspace, asset_entity_id))
        return Response(
            {
                "people": [{"id": item.id, "name": item.person.entity.display_name} for item in people],
                "sites": [{"id": item.id, "name": item.entity.display_name} for item in sites],
                "locations": [
                    {"id": item.id, "name": item.entity.display_name, "site_id": item.site_id} for item in locations
                ],
            }
        )


class ClientHardwareAssignmentView(APIView):
    @extend_schema(request=HardwareAssignmentWriteSerializer, responses={200: HardwareProfileSerializer})
    def post(self, request, organization_entity_id, asset_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = HardwareAssignmentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = assign_hardware(
                asset=_asset(workspace, asset_entity_id),
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except InventoryError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(HardwareProfileSerializer(profile).data)

    @extend_schema(responses={200: HardwareProfileSerializer})
    def delete(self, request, organization_entity_id, asset_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        try:
            profile = unassign_hardware(asset=_asset(workspace, asset_entity_id), actor_id=request.user.pk)
        except InventoryError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(HardwareProfileSerializer(profile).data)


class ClientHardwareDisposalView(APIView):
    @extend_schema(request=HardwareDisposalWriteSerializer, responses={200: HardwareProfileSerializer})
    def post(self, request, organization_entity_id, asset_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = HardwareDisposalWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = dispose_hardware(
                asset=_asset(workspace, asset_entity_id),
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except InventoryError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(HardwareProfileSerializer(profile).data)


class ClientHardwareLifecycleView(APIView):
    @extend_schema(
        responses={200: HardwareLifecycleEventSerializer(many=True)},
    )
    def get(self, request, organization_entity_id, asset_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        events = lifecycle_events(_asset(workspace, asset_entity_id))
        return Response(HardwareLifecycleEventSerializer(events, many=True).data)


class ClientAssetModelChoiceListView(APIView):
    @extend_schema(
        parameters=[OpenApiParameter("q", str)],
        responses={200: CatalogModelChoiceResultSerializer},
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        query = str(request.query_params.get("q", "")).strip()[:240]
        results = model_choices_for_client(workspace.data_scope, query=query)[:50]
        return Response(CatalogModelChoiceResultSerializer({"results": results}).data)


class ClientAssetDocumentDetailView(APIView):
    @extend_schema(responses={200: AssetDocumentDetailSerializer})
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
    @extend_schema(responses={200: DerivedVendorResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        vendors = vendors_for_scope(workspace.data_scope)
        return Response(DerivedVendorResultSerializer({"results": vendors, "count": vendors.count()}).data)
