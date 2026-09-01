from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_client_portal_member

from .api_contracts import ApiErrorEnvelopeSerializer
from .documentation_maps import (
    MapFinding,
    archive_map,
    create_baseline,
    create_map,
    inspect_map,
    map_for_workspace,
    maps_for_workspace,
    ordered_map_entries,
    portal_baseline_is_current,
    portal_maps_for_organization,
    read_baseline,
    review_map,
    update_map,
)
from .integrations import resolve_integration_workspace
from .models import (
    Document,
    DocumentationMap,
    DocumentationMapAudience,
    DocumentationMapBaseline,
    DocumentationMapEntry,
    DocumentationMapEntryKind,
    DocumentationMapType,
    DocumentPublication,
    DocumentReviewState,
)
from .preflight import run_map_preflight
from .rls import OrganizationRLSMode, bind_local_rls_scope
from .scoping import DataScope

ErrorEnvelopeSerializer = ApiErrorEnvelopeSerializer


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class MapEntryWriteSerializer(StrictSerializer):
    parent_index = serializers.IntegerField(min_value=0, required=False, allow_null=True, default=None)
    position = serializers.IntegerField(min_value=0)
    kind = serializers.ChoiceField(choices=DocumentationMapEntryKind.choices)
    label = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    document_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    document_revision_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    publication_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    map_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    external_url = serializers.URLField(max_length=1000, required=False, allow_blank=True, default="")


class MapWriteSerializer(StrictSerializer):
    title = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True)
    purpose = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    map_type = serializers.ChoiceField(choices=DocumentationMapType.choices)
    audience = serializers.ChoiceField(choices=DocumentationMapAudience.choices)
    owner_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    entries = MapEntryWriteSerializer(many=True, max_length=250)


class MapUpdateSerializer(MapWriteSerializer):
    expected_revision_id = serializers.UUIDField()


class MapReviewSerializer(StrictSerializer):
    state = serializers.ChoiceField(choices=(DocumentReviewState.APPROVED, DocumentReviewState.CHANGES_REQUESTED))


class MapBaselineWriteSerializer(StrictSerializer):
    expected_revision_id = serializers.UUIDField()
    formats = serializers.ListField(
        child=serializers.ChoiceField(choices=("pdf", "docx")),
        required=False,
        default=list,
        max_length=2,
    )


class MapFindingSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.ChoiceField(choices=("information", "warning", "blocker"))
    entry_id = serializers.UUIDField(allow_null=True)
    detail = serializers.CharField()


class MapEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    parent_id = serializers.UUIDField(allow_null=True)
    position = serializers.IntegerField()
    kind = serializers.CharField()
    label = serializers.CharField()
    title = serializers.SerializerMethodField()
    document_id = serializers.UUIDField(source="document.entity_id", allow_null=True)
    document_revision_id = serializers.UUIDField(allow_null=True)
    publication_id = serializers.UUIDField(source="publication.entity_id", allow_null=True)
    map_id = serializers.UUIDField(source="subordinate_map.entity_id", allow_null=True)
    external_url = serializers.CharField()

    def get_title(self, entry: DocumentationMapEntry) -> str:
        if entry.label:
            return entry.label
        if entry.document_id:
            return cast(Document, entry.document).entity.display_name
        if entry.publication_id:
            return cast(DocumentPublication, entry.publication).title
        if entry.subordinate_map_id:
            return cast(DocumentationMap, entry.subordinate_map).entity.display_name
        return entry.external_url


class MapRevisionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    parent_id = serializers.UUIDField(allow_null=True)
    revision_number = serializers.IntegerField()
    title = serializers.CharField()
    purpose = serializers.CharField()
    map_type = serializers.CharField()
    audience = serializers.CharField()
    content_digest = serializers.CharField()
    created_by = serializers.CharField(source="created_by.display_name")
    created_at = serializers.DateTimeField()
    entries = serializers.SerializerMethodField()

    @extend_schema_field(MapEntrySerializer(many=True))
    def get_entries(self, revision):  # type: ignore[no-untyped-def]
        return MapEntrySerializer(ordered_map_entries(revision), many=True).data


class MapBaselineSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    revision_id = serializers.UUIDField()
    revision_number = serializers.IntegerField(source="revision.revision_number")
    content_digest = serializers.CharField()
    byte_size = serializers.IntegerField()
    formats = serializers.SerializerMethodField()
    created_by = serializers.CharField(source="created_by.display_name")
    created_at = serializers.DateTimeField()

    def get_formats(self, baseline: DocumentationMapBaseline) -> list[str]:
        formats = baseline.manifest.get("formats", [])
        return [str(value) for value in formats] if isinstance(formats, list) else []


class DocumentationMapSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    title = serializers.CharField(source="current_revision.title")
    purpose = serializers.CharField(source="current_revision.purpose")
    map_type = serializers.CharField(source="current_revision.map_type")
    audience = serializers.CharField(source="current_revision.audience")
    owner_id = serializers.UUIDField(allow_null=True)
    owner_name = serializers.CharField(source="owner.display_name", allow_null=True)
    review_state = serializers.CharField()
    current_revision = MapRevisionSerializer()
    revision_count = serializers.SerializerMethodField()
    baselines = MapBaselineSerializer(many=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_revision_count(self, documentation_map: DocumentationMap) -> int:
        return (
            len(getattr(documentation_map, "_prefetched_objects_cache", {}).get("revisions", ()))
            or documentation_map.revisions.count()
        )


class DocumentationMapResultSerializer(serializers.Serializer):
    results = DocumentationMapSerializer(many=True)
    count = serializers.IntegerField()


class MapPreviewSerializer(serializers.Serializer):
    map = DocumentationMapSerializer()
    findings = MapFindingSerializer(many=True)
    blocker_count = serializers.IntegerField()
    warning_count = serializers.IntegerField()


class MapChoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    kind = serializers.CharField()
    detail = serializers.CharField(allow_blank=True)
    current_revision_id = serializers.UUIDField(allow_null=True, required=False)


class MapChoicesSerializer(serializers.Serializer):
    documents = MapChoiceSerializer(many=True)
    publications = MapChoiceSerializer(many=True)
    maps = MapChoiceSerializer(many=True)
    owners = MapChoiceSerializer(many=True)


def _workspace(request: Any, organization_entity_id: UUID | None, permission: PermissionKey):  # type: ignore[no-untyped-def]
    return resolve_integration_workspace(
        request.user, organization_entity_id=organization_entity_id, permission=permission
    )


def _map_payload(record: DocumentationMap) -> dict[str, object]:
    return dict(DocumentationMapSerializer(record).data)


def _list(request: Any, organization_entity_id: UUID | None) -> Response:
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW)
    records = list(maps_for_workspace(workspace))
    return Response(DocumentationMapResultSerializer({"results": records, "count": len(records)}).data)


def _create(request: Any, organization_entity_id: UUID | None) -> Response:
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT)
    serializer = MapWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    record = create_map(workspace=workspace, actor=request.user, **serializer.validated_data)
    return Response(_map_payload(record), status=status.HTTP_201_CREATED)


def _retrieve(request: Any, organization_entity_id: UUID | None, map_entity_id: UUID) -> Response:
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW)
    return Response(_map_payload(map_for_workspace(workspace, map_entity_id)))


def _update(request: Any, organization_entity_id: UUID | None, map_entity_id: UUID) -> Response:
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT)
    serializer = MapUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    record = update_map(
        workspace=workspace,
        actor=request.user,
        documentation_map=map_for_workspace(workspace, map_entity_id),
        **serializer.validated_data,
    )
    return Response(_map_payload(record))


def _archive(request: Any, organization_entity_id: UUID | None, map_entity_id: UUID) -> Response:
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT)
    archive_map(workspace=workspace, actor=request.user, documentation_map=map_for_workspace(workspace, map_entity_id))
    return Response(status=status.HTTP_204_NO_CONTENT)


def _review(request: Any, organization_entity_id: UUID | None, map_entity_id: UUID) -> Response:
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE)
    serializer = MapReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    record = review_map(
        workspace=workspace,
        actor=request.user,
        documentation_map=map_for_workspace(workspace, map_entity_id),
        state=serializer.validated_data["state"],
    )
    return Response(_map_payload(record))


def _preview(request: Any, organization_entity_id: UUID | None, map_entity_id: UUID) -> Response:
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW)
    record = map_for_workspace(workspace, map_entity_id)
    preflight = run_map_preflight(documentation_map=record, findings=inspect_map(record))
    findings: list[MapFinding] = preflight["findings"]
    return Response(
        MapPreviewSerializer(
            {
                "map": record,
                "findings": findings,
                "blocker_count": preflight["counts"]["blocker"],
                "warning_count": preflight["counts"]["warning"],
            }
        ).data
    )


def _baselines(request: Any, organization_entity_id: UUID | None, map_entity_id: UUID) -> Response:
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_PUBLISH)
    record = map_for_workspace(workspace, map_entity_id)
    serializer = MapBaselineWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    baseline = create_baseline(
        workspace=workspace,
        actor=request.user,
        documentation_map=record,
        expected_revision_id=serializer.validated_data["expected_revision_id"],
        formats=set(serializer.validated_data["formats"]),
    )
    return Response(MapBaselineSerializer(baseline).data, status=status.HTTP_201_CREATED)


def _baseline(workspace, map_entity_id: UUID, baseline_id: UUID) -> DocumentationMapBaseline:  # type: ignore[no-untyped-def]
    record = map_for_workspace(workspace, map_entity_id)
    try:
        return DocumentationMapBaseline.objects.select_related("revision", "created_by").get(
            id=baseline_id,
            documentation_map=record,
            tenant=workspace.member.tenant,
            workspace_id=workspace.data_scope.workspace_id,
            organization=workspace.organization,
        )
    except DocumentationMapBaseline.DoesNotExist as exc:
        raise NotFound("The selected documentation map baseline is unavailable.") from exc


def _download(
    request: Any, organization_entity_id: UUID | None, map_entity_id: UUID, baseline_id: UUID
) -> HttpResponse:
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW)
    baseline = _baseline(workspace, map_entity_id, baseline_id)
    response = HttpResponse(read_baseline(baseline), content_type="application/zip")
    response["Content-Disposition"] = (
        content_disposition_header(
            True, f"documentation-map-{baseline.documentation_map.entity_id}-baseline-{baseline.id}.zip"
        )
        or "attachment"
    )
    response["Cache-Control"] = "private, no-store"
    return response


def _choices(request: Any, organization_entity_id: UUID | None) -> Response:
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW)
    documents = (
        Document.objects.filter(
            tenant=workspace.member.tenant,
            organization=workspace.organization,
            entity__workspace_id=workspace.data_scope.workspace_id,
            archived_at__isnull=True,
        )
        .select_related("entity")
        .prefetch_related("placements__block__current_revision")
        .order_by("entity__display_name")[:250]
    )
    publications = (
        DocumentPublication.objects.filter(
            tenant=workspace.member.tenant,
            organization=workspace.organization,
            document__entity__workspace_id=workspace.data_scope.workspace_id,
        )
        .select_related("entity")
        .order_by("title", "id")[:250]
    )
    map_records = maps_for_workspace(workspace)[:250]
    owners = workspace.member.tenant.memberships.select_related("user").order_by("user__email")[:250]
    payload = {
        "documents": [
            {
                "id": item.entity_id,
                "title": item.entity.display_name,
                "kind": "document",
                "detail": item.review_state,
                "current_revision_id": next(
                    (
                        placement.block.current_revision_id
                        for placement in item.placements.all()
                        if placement.parent_id is None
                    ),
                    None,
                ),
            }
            for item in documents
        ],
        "publications": [
            {"id": item.entity_id, "title": item.title, "kind": "publication", "detail": item.audience}
            for item in publications
        ],
        "maps": [
            {
                "id": item.entity_id,
                "title": item.current_revision.title,
                "kind": "map",
                "detail": item.current_revision.audience,
            }
            for item in map_records
            if item.current_revision is not None
        ],
        "owners": [
            {"id": item.user_id, "title": item.user.display_name, "kind": "owner", "detail": item.user.email}
            for item in owners
        ],
    }
    return Response(MapChoicesSerializer(payload).data)


class MSPDocumentationMapListCreateView(APIView):
    @extend_schema(operation_id="documentation_maps_msp_list", responses={200: DocumentationMapResultSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        return _list(request, None)

    @extend_schema(
        operation_id="documentation_maps_msp_create",
        request=MapWriteSerializer,
        responses={201: DocumentationMapSerializer},
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        return _create(request, None)


class OrganizationDocumentationMapListCreateView(APIView):
    @extend_schema(
        operation_id="documentation_maps_organization_list", responses={200: DocumentationMapResultSerializer}
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _list(request, organization_entity_id)

    @extend_schema(
        operation_id="documentation_maps_organization_create",
        request=MapWriteSerializer,
        responses={201: DocumentationMapSerializer},
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _create(request, organization_entity_id)


class MSPDocumentationMapDetailView(APIView):
    @extend_schema(operation_id="documentation_maps_msp_retrieve", responses={200: DocumentationMapSerializer})
    def get(self, request, map_entity_id):  # type: ignore[no-untyped-def]
        return _retrieve(request, None, map_entity_id)

    @extend_schema(
        operation_id="documentation_maps_msp_update",
        request=MapUpdateSerializer,
        responses={200: DocumentationMapSerializer, 409: ErrorEnvelopeSerializer},
    )
    def put(self, request, map_entity_id):  # type: ignore[no-untyped-def]
        return _update(request, None, map_entity_id)

    @extend_schema(operation_id="documentation_maps_msp_archive", responses={204: None})
    def delete(self, request, map_entity_id):  # type: ignore[no-untyped-def]
        return _archive(request, None, map_entity_id)


class OrganizationDocumentationMapDetailView(APIView):
    @extend_schema(operation_id="documentation_maps_organization_retrieve", responses={200: DocumentationMapSerializer})
    def get(self, request, organization_entity_id, map_entity_id):  # type: ignore[no-untyped-def]
        return _retrieve(request, organization_entity_id, map_entity_id)

    @extend_schema(
        operation_id="documentation_maps_organization_update",
        request=MapUpdateSerializer,
        responses={200: DocumentationMapSerializer, 409: ErrorEnvelopeSerializer},
    )
    def put(self, request, organization_entity_id, map_entity_id):  # type: ignore[no-untyped-def]
        return _update(request, organization_entity_id, map_entity_id)

    @extend_schema(operation_id="documentation_maps_organization_archive", responses={204: None})
    def delete(self, request, organization_entity_id, map_entity_id):  # type: ignore[no-untyped-def]
        return _archive(request, organization_entity_id, map_entity_id)


class MSPDocumentationMapChoicesView(APIView):
    @extend_schema(operation_id="documentation_maps_msp_choices", responses={200: MapChoicesSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        return _choices(request, None)


class OrganizationDocumentationMapChoicesView(APIView):
    @extend_schema(operation_id="documentation_maps_organization_choices", responses={200: MapChoicesSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _choices(request, organization_entity_id)


class MSPDocumentationMapReviewView(APIView):
    @extend_schema(
        operation_id="documentation_maps_msp_review",
        request=MapReviewSerializer,
        responses={200: DocumentationMapSerializer},
    )
    def post(self, request, map_entity_id):  # type: ignore[no-untyped-def]
        return _review(request, None, map_entity_id)


class OrganizationDocumentationMapReviewView(APIView):
    @extend_schema(
        operation_id="documentation_maps_organization_review",
        request=MapReviewSerializer,
        responses={200: DocumentationMapSerializer},
    )
    def post(self, request, organization_entity_id, map_entity_id):  # type: ignore[no-untyped-def]
        return _review(request, organization_entity_id, map_entity_id)


class MSPDocumentationMapPreviewView(APIView):
    @extend_schema(operation_id="documentation_maps_msp_preview", responses={200: MapPreviewSerializer})
    def get(self, request, map_entity_id):  # type: ignore[no-untyped-def]
        return _preview(request, None, map_entity_id)


class OrganizationDocumentationMapPreviewView(APIView):
    @extend_schema(operation_id="documentation_maps_organization_preview", responses={200: MapPreviewSerializer})
    def get(self, request, organization_entity_id, map_entity_id):  # type: ignore[no-untyped-def]
        return _preview(request, organization_entity_id, map_entity_id)


class MSPDocumentationMapBaselineListCreateView(APIView):
    @extend_schema(
        operation_id="documentation_maps_msp_baseline_create",
        request=MapBaselineWriteSerializer,
        responses={201: MapBaselineSerializer, 409: ErrorEnvelopeSerializer},
    )
    def post(self, request, map_entity_id):  # type: ignore[no-untyped-def]
        return _baselines(request, None, map_entity_id)


class OrganizationDocumentationMapBaselineListCreateView(APIView):
    @extend_schema(
        operation_id="documentation_maps_organization_baseline_create",
        request=MapBaselineWriteSerializer,
        responses={201: MapBaselineSerializer, 409: ErrorEnvelopeSerializer},
    )
    def post(self, request, organization_entity_id, map_entity_id):  # type: ignore[no-untyped-def]
        return _baselines(request, organization_entity_id, map_entity_id)


class MSPDocumentationMapBaselineDownloadView(APIView):
    @extend_schema(operation_id="documentation_maps_msp_baseline_download", responses={(200, "application/zip"): bytes})
    def get(self, request, map_entity_id, baseline_id):  # type: ignore[no-untyped-def]
        return _download(request, None, map_entity_id, baseline_id)


class OrganizationDocumentationMapBaselineDownloadView(APIView):
    @extend_schema(
        operation_id="documentation_maps_organization_baseline_download", responses={(200, "application/zip"): bytes}
    )
    def get(self, request, organization_entity_id, map_entity_id, baseline_id):  # type: ignore[no-untyped-def]
        return _download(request, organization_entity_id, map_entity_id, baseline_id)


class PortalDocumentationMapSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="documentation_map.entity_id")
    title = serializers.CharField(source="revision.title")
    purpose = serializers.CharField(source="revision.purpose")
    map_type = serializers.CharField(source="revision.map_type")
    baseline_id = serializers.UUIDField(source="id")
    content_digest = serializers.CharField()
    created_at = serializers.DateTimeField()
    contents = serializers.SerializerMethodField()

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_contents(self, baseline: DocumentationMapBaseline) -> list[dict[str, object]]:
        entries = baseline.manifest.get("entries", [])
        if not isinstance(entries, list):
            return []
        return [
            {"title": str(item.get("title", "")), "kind": str(item.get("kind", "")), "source_id": item.get("source_id")}
            for item in entries
            if isinstance(item, dict) and item.get("kind") in {"publication", "map"}
        ]


class PortalDocumentationMapResultSerializer(serializers.Serializer):
    results = PortalDocumentationMapSerializer(many=True)
    count = serializers.IntegerField()


def _portal_baselines(request: Any):  # type: ignore[no-untyped-def]
    member = require_client_portal_member(request.user)
    if member.organization is None:
        raise PermissionDenied("Client portal membership is required.")
    bind_local_rls_scope(
        DataScope.organization(member.tenant, member.organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    )
    return portal_maps_for_organization(member.organization.id)


class ClientPortalDocumentationMapListView(APIView):
    @extend_schema(
        operation_id="client_portal_documentation_maps_list", responses={200: PortalDocumentationMapResultSerializer}
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        records = [baseline for baseline in _portal_baselines(request) if portal_baseline_is_current(baseline)]
        latest: dict[UUID, DocumentationMapBaseline] = {}
        for baseline in records:
            latest.setdefault(baseline.documentation_map_id, baseline)
        selected = list(latest.values())
        return Response(PortalDocumentationMapResultSerializer({"results": selected, "count": len(selected)}).data)


class ClientPortalDocumentationMapDownloadView(APIView):
    @extend_schema(
        operation_id="client_portal_documentation_maps_download", responses={(200, "application/zip"): bytes}
    )
    def get(self, request, baseline_id):  # type: ignore[no-untyped-def]
        baseline = get_object_or_404(_portal_baselines(request), id=baseline_id)
        if not portal_baseline_is_current(baseline):
            raise Http404
        try:
            content = read_baseline(baseline)
        except serializers.ValidationError as exc:
            raise Http404 from exc
        response = HttpResponse(content, content_type="application/zip")
        response["Content-Disposition"] = (
            content_disposition_header(True, f"{baseline.revision.title}-handoff.zip") or "attachment"
        )
        response["Cache-Control"] = "private, no-store"
        return response
