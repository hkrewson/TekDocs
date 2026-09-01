from __future__ import annotations

from typing import Any
from uuid import UUID

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey

from .api_contracts import ApiErrorEnvelopeSerializer
from .collection_pagination import BoundedCollectionQuerySerializer, OffsetPageSerializer
from .imports import (
    RECORD_TYPES,
    SOURCE_FORMATS,
    apply_batch,
    batches_for_workspace,
    cancel_batch,
    create_preview,
    result_report,
    template_csv,
)
from .integrations import resolve_integration_workspace
from .models import ImportBatch, ImportRow

ErrorEnvelopeSerializer = ApiErrorEnvelopeSerializer


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class ImportUploadSerializer(StrictSerializer):
    file = serializers.FileField()
    source_format = serializers.ChoiceField(choices=sorted(SOURCE_FORMATS))
    record_type = serializers.ChoiceField(choices=RECORD_TYPES, required=False, allow_blank=True, default="")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["source_format"] != "tekdocs_bundle" and not attrs.get("record_type"):
            raise serializers.ValidationError({"record_type": "Choose the record type contained in this CSV."})
        return attrs


class ImportApplySerializer(StrictSerializer):
    matches = serializers.DictField(
        child=serializers.UUIDField(),
        required=False,
        default=dict,
        help_text="Preview row UUID to confirmed local entity UUID.",
    )


class ImportRowSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    row_number = serializers.IntegerField()
    record_type = serializers.CharField()
    external_key = serializers.CharField()
    action = serializers.CharField()
    reason_code = serializers.CharField()
    local_entity_id = serializers.UUIDField(allow_null=True)


class ImportBatchSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    source_format = serializers.CharField()
    schema_version = serializers.IntegerField()
    source_filename = serializers.CharField()
    source_digest = serializers.CharField()
    state = serializers.CharField()
    result_counts = serializers.JSONField()
    last_error_code = serializers.CharField()
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    applied_at = serializers.DateTimeField(allow_null=True)


class ImportBatchPageSerializer(OffsetPageSerializer):
    results = ImportBatchSerializer(many=True)


class ImportRowPageSerializer(OffsetPageSerializer):
    results = ImportRowSerializer(many=True)


class ImportRowQuerySerializer(BoundedCollectionQuerySerializer):
    action = serializers.ChoiceField(choices=("create", "update", "unchanged", "conflict", "rejected"), required=False)


def _workspace(request: Any, organization_entity_id: UUID | None, permission: PermissionKey):  # type: ignore[no-untyped-def]
    return resolve_integration_workspace(
        request.user, organization_entity_id=organization_entity_id, permission=permission
    )


def _batch(workspace, batch_id: UUID) -> ImportBatch:  # type: ignore[no-untyped-def]
    try:
        batch: ImportBatch = batches_for_workspace(workspace).get(pk=batch_id)
        return batch
    except ImportBatch.DoesNotExist as exc:
        raise NotFound("The import batch is unavailable.") from exc


class ImportBatchListCreateView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(responses={200: ImportBatchPageSerializer, 400: ErrorEnvelopeSerializer})
    def get(self, request, organization_entity_id: UUID | None = None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_VIEW)
        query = BoundedCollectionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = query.validated_data["page"]
        page_size = query.validated_data["page_size"]
        records = batches_for_workspace(workspace)
        count = records.count()
        offset = (page - 1) * page_size
        selected = list(records[offset : offset + page_size + 1])
        return Response(
            {
                "results": ImportBatchSerializer(selected[:page_size], many=True).data,
                "page": page,
                "page_size": page_size,
                "count": count,
                "has_more": len(selected) > page_size,
            }
        )

    @extend_schema(request=ImportUploadSerializer, responses={201: ImportBatchSerializer, 400: ErrorEnvelopeSerializer})
    def post(self, request, organization_entity_id: UUID | None = None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE)
        serializer = ImportUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch = create_preview(
            workspace=workspace,
            actor_id=request.user.id,
            upload=serializer.validated_data["file"],
            source_format=serializer.validated_data["source_format"],
            record_type=serializer.validated_data["record_type"],
        )
        return Response(ImportBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class ImportBatchDetailView(APIView):
    @extend_schema(responses={200: ImportBatchSerializer, 404: ErrorEnvelopeSerializer})
    def get(self, request, batch_id: UUID, organization_entity_id: UUID | None = None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_VIEW)
        return Response(ImportBatchSerializer(_batch(workspace, batch_id)).data)


class MSPImportBatchDetailView(ImportBatchDetailView):
    @extend_schema(
        operation_id="workspaces_msp_integrations_imports_detail_retrieve",
        responses={200: ImportBatchSerializer, 404: ErrorEnvelopeSerializer},
    )
    def get(  # type: ignore[no-untyped-def]
        self, request, batch_id: UUID, organization_entity_id: UUID | None = None
    ):
        return super().get(request, batch_id, organization_entity_id)


class OrganizationImportBatchDetailView(ImportBatchDetailView):
    @extend_schema(
        operation_id="workspaces_organizations_integrations_imports_detail_retrieve",
        responses={200: ImportBatchSerializer, 404: ErrorEnvelopeSerializer},
    )
    def get(  # type: ignore[no-untyped-def]
        self, request, batch_id: UUID, organization_entity_id: UUID | None = None
    ):
        return super().get(request, batch_id, organization_entity_id)


class ImportRowListView(APIView):
    @extend_schema(responses={200: ImportRowPageSerializer, 404: ErrorEnvelopeSerializer})
    def get(self, request, batch_id: UUID, organization_entity_id: UUID | None = None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_VIEW)
        batch = _batch(workspace, batch_id)
        query = ImportRowQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = query.validated_data["page"]
        page_size = query.validated_data["page_size"]
        records = ImportRow.scoped.for_scope(workspace.data_scope).filter(batch=batch).select_related("local_entity")
        action = query.validated_data.get("action", "")
        if action:
            records = records.filter(action=action)
        count = records.count()
        offset = (page - 1) * page_size
        selected = list(records[offset : offset + page_size + 1])
        return Response(
            {
                "results": ImportRowSerializer(selected[:page_size], many=True).data,
                "page": page,
                "page_size": page_size,
                "count": count,
                "has_more": len(selected) > page_size,
            }
        )


class ImportApplyView(APIView):
    @extend_schema(
        request=ImportApplySerializer,
        responses={200: ImportBatchSerializer, 400: ErrorEnvelopeSerializer, 404: ErrorEnvelopeSerializer},
    )
    def post(self, request, batch_id: UUID, organization_entity_id: UUID | None = None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE)
        serializer = ImportApplySerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        batch = apply_batch(
            workspace=workspace,
            batch_id=batch_id,
            actor_id=request.user.id,
            matches={key: str(value) for key, value in serializer.validated_data["matches"].items()},
        )
        return Response(ImportBatchSerializer(batch).data)


class ImportCancelView(APIView):
    @extend_schema(
        request=None, responses={200: ImportBatchSerializer, 400: ErrorEnvelopeSerializer, 404: ErrorEnvelopeSerializer}
    )
    def post(self, request, batch_id: UUID, organization_entity_id: UUID | None = None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE)
        return Response(
            ImportBatchSerializer(cancel_batch(workspace=workspace, batch_id=batch_id, actor_id=request.user.id)).data
        )


class ImportReportView(APIView):
    @extend_schema(
        responses={
            200: OpenApiResponse(response=bytes, description="Value-safe CSV import result report."),
            404: ErrorEnvelopeSerializer,
        }
    )
    def get(self, request, batch_id: UUID, organization_entity_id: UUID | None = None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_VIEW)
        batch = _batch(workspace, batch_id)
        response = HttpResponse(result_report(batch), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="tekdocs-import-{batch.id}.csv"'
        response["Cache-Control"] = "private, no-store"
        return response


class ImportTemplateView(APIView):
    @extend_schema(
        responses={
            200: OpenApiResponse(response=bytes, description="UTF-8 CSV import template."),
            404: ErrorEnvelopeSerializer,
        }
    )
    def get(self, request, record_type: str, organization_entity_id: UUID | None = None):  # type: ignore[no-untyped-def]
        _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_VIEW)
        response = HttpResponse(template_csv(record_type), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="tekdocs-{record_type}-template.csv"'
        response["Cache-Control"] = "private, no-store"
        return response
