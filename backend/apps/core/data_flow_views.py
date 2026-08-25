from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission, require_permission

from .collection_pagination import BoundedCollectionQuerySerializer, paginate
from .data_flow_exports import snapshot_csv, snapshot_json, snapshot_svg
from .data_flows import (
    DataFlowError,
    DataFlowInput,
    archive_data_flow,
    create_data_flow,
    create_data_flow_snapshot,
    data_flow_choices,
    data_flows_for_scope,
    revise_data_flow,
    revisions_for_flow,
    snapshots_for_scope,
)
from .models import (
    DataFlow,
    DataFlowClassification,
    DataFlowDirection,
    DataFlowEndpointKind,
    DataFlowProtection,
    DataFlowProvenance,
    DataFlowSnapshot,
    DataFlowTransfer,
)
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        if isinstance(data, dict):
            unexpected = set(data) - set(self.fields)
            if unexpected:
                raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class DataFlowWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, trim_whitespace=True)
    source_kind = serializers.ChoiceField(choices=DataFlowEndpointKind.values)
    source_entity_id = serializers.UUIDField(required=False, allow_null=True)
    source_label = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    destination_kind = serializers.ChoiceField(choices=DataFlowEndpointKind.values)
    destination_entity_id = serializers.UUIDField(required=False, allow_null=True)
    destination_label = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    direction = serializers.ChoiceField(choices=DataFlowDirection.values)
    transfer_mechanism = serializers.ChoiceField(choices=DataFlowTransfer.values)
    data_classification = serializers.ChoiceField(choices=DataFlowClassification.values)
    purpose = serializers.CharField(max_length=1000, trim_whitespace=True)
    crosses_trust_boundary = serializers.BooleanField()
    protection = serializers.ChoiceField(choices=DataFlowProtection.values)
    owner_entity_id = serializers.UUIDField(required=False, allow_null=True)
    review_due_on = serializers.DateField(required=False, allow_null=True)
    provenance = serializers.ChoiceField(choices=DataFlowProvenance.values)


class DataFlowRevisionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    revision_number = serializers.IntegerField()
    source_kind = serializers.CharField()
    source_entity_id = serializers.UUIDField(allow_null=True)
    source_display_name = serializers.SerializerMethodField()
    source_label = serializers.CharField()
    destination_kind = serializers.CharField()
    destination_entity_id = serializers.UUIDField(allow_null=True)
    destination_display_name = serializers.SerializerMethodField()
    destination_label = serializers.CharField()
    direction = serializers.CharField()
    transfer_mechanism = serializers.CharField()
    data_classification = serializers.CharField()
    purpose = serializers.CharField()
    crosses_trust_boundary = serializers.BooleanField()
    protection = serializers.CharField()
    owner_entity_id = serializers.UUIDField(allow_null=True)
    owner_display_name = serializers.SerializerMethodField()
    review_due_on = serializers.DateField(allow_null=True)
    provenance = serializers.CharField()
    content_digest = serializers.CharField()
    created_at = serializers.DateTimeField()

    def get_source_display_name(self, revision) -> str:  # type: ignore[no-untyped-def]
        return str(revision.source_entity.display_name) if revision.source_entity_id else str(revision.source_label)

    def get_destination_display_name(self, revision) -> str:  # type: ignore[no-untyped-def]
        if revision.destination_entity_id:
            return str(revision.destination_entity.display_name)
        return str(revision.destination_label)

    def get_owner_display_name(self, revision) -> str:  # type: ignore[no-untyped-def]
        return revision.owner_entity.display_name if revision.owner_entity_id else ""


class DataFlowSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    revision_count = serializers.SerializerMethodField()
    current_revision = DataFlowRevisionSerializer(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_revision_count(self, flow: DataFlow) -> int:
        return len(flow.revisions.all())


class DataFlowResultSerializer(serializers.Serializer):
    results = DataFlowSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    #: Whether this member may declare or revise a flow here. A hidden control is not
    #: authorization — the server still refuses — but an authoring surface that offers
    #: an action it knows will be refused wastes the author's time.
    can_manage = serializers.BooleanField()


class DataFlowRevisionResultSerializer(serializers.Serializer):
    results = DataFlowRevisionSerializer(many=True)
    count = serializers.IntegerField()


class DataFlowChoiceSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class DataFlowChoicesSerializer(serializers.Serializer):
    endpoint_kinds = DataFlowChoiceSerializer(many=True)
    directions = DataFlowChoiceSerializer(many=True)
    transfer_mechanisms = DataFlowChoiceSerializer(many=True)
    data_classifications = DataFlowChoiceSerializer(many=True)
    protections = DataFlowChoiceSerializer(many=True)
    provenance_states = DataFlowChoiceSerializer(many=True)


def _workspace(request, organization_entity_id: UUID | None, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    workspace = (
        resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        if organization_entity_id is not None
        else resolve_msp_workspace(request.user)
    )
    require_permission(request.user, permission, organization=workspace.organization)
    return workspace


def _flow(workspace: ResolvedWorkspace, entity_id: UUID) -> DataFlow:
    return get_object_or_404(data_flows_for_scope(workspace.data_scope), entity_id=entity_id)


def _input(payload: dict[str, object]) -> DataFlowInput:
    return DataFlowInput(**payload)  # type: ignore[arg-type]


def _refuse(error: Exception) -> serializers.ValidationError:
    return serializers.ValidationError({"detail": str(error)})


class DataFlowListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: DataFlowResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.DATA_FLOWS_VIEW)
        query = BoundedCollectionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        records = data_flows_for_scope(workspace.data_scope, query=request.query_params.get("q", ""))
        page = paginate(records, page=values["page"], page_size=values["page_size"])
        return Response(
            {
                "results": DataFlowSerializer(page.records, many=True).data,
                "page": page.page,
                "page_size": page.page_size,
                "count": page.count,
                "has_more": page.has_more,
                "can_manage": context_has_permission(
                    workspace.member, PermissionKey.DATA_FLOWS_EDIT, organization=workspace.organization
                ),
            }
        )

    @extend_schema(request=DataFlowWriteSerializer, responses={201: DataFlowSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.DATA_FLOWS_EDIT)
        serializer = DataFlowWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            flow = create_data_flow(
                workspace=workspace, actor_id=request.user.pk, value=_input(serializer.validated_data)
            )
        except (DataFlowError, DjangoValidationError) as exc:
            raise _refuse(exc) from exc
        return Response(DataFlowSerializer(flow).data, status=201)


class DataFlowDetailView(APIView):
    @extend_schema(responses={200: DataFlowSerializer})
    def get(self, request, data_flow_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.DATA_FLOWS_VIEW)
        return Response(DataFlowSerializer(_flow(workspace, data_flow_entity_id)).data)

    @extend_schema(request=DataFlowWriteSerializer, responses={200: DataFlowSerializer})
    def patch(self, request, data_flow_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.DATA_FLOWS_EDIT)
        flow = _flow(workspace, data_flow_entity_id)
        serializer = DataFlowWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            revised = revise_data_flow(
                workspace=workspace, flow=flow, actor_id=request.user.pk, value=_input(serializer.validated_data)
            )
        except (DataFlowError, DjangoValidationError) as exc:
            raise _refuse(exc) from exc
        return Response(DataFlowSerializer(revised).data)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, data_flow_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.DATA_FLOWS_EDIT)
        archive_data_flow(flow=_flow(workspace, data_flow_entity_id), actor_id=request.user.pk)
        return Response(status=204)


class DataFlowRevisionListView(APIView):
    @extend_schema(responses={200: DataFlowRevisionResultSerializer})
    def get(self, request, data_flow_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.DATA_FLOWS_VIEW)
        revisions = list(revisions_for_flow(_flow(workspace, data_flow_entity_id)))
        return Response({"results": DataFlowRevisionSerializer(revisions, many=True).data, "count": len(revisions)})


class DataFlowChoicesView(APIView):
    @extend_schema(responses={200: DataFlowChoicesSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        _workspace(request, organization_entity_id, PermissionKey.DATA_FLOWS_VIEW)
        return Response(data_flow_choices())


@extend_schema_view(
    get=extend_schema(operation_id="msp_data_flows_list"),
    post=extend_schema(operation_id="msp_data_flows_create"),
)
class MSPDataFlowListCreateView(DataFlowListCreateView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="msp_data_flow_retrieve"),
    patch=extend_schema(operation_id="msp_data_flow_revise"),
    delete=extend_schema(operation_id="msp_data_flow_archive"),
)
class MSPDataFlowDetailView(DataFlowDetailView):
    pass


@extend_schema_view(get=extend_schema(operation_id="msp_data_flow_revisions_list"))
class MSPDataFlowRevisionListView(DataFlowRevisionListView):
    pass


@extend_schema_view(get=extend_schema(operation_id="msp_data_flow_choices_retrieve"))
class MSPDataFlowChoicesView(DataFlowChoicesView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="organization_data_flows_list"),
    post=extend_schema(operation_id="organization_data_flows_create"),
)
class OrganizationDataFlowListCreateView(DataFlowListCreateView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="organization_data_flow_retrieve"),
    patch=extend_schema(operation_id="organization_data_flow_revise"),
    delete=extend_schema(operation_id="organization_data_flow_archive"),
)
class OrganizationDataFlowDetailView(DataFlowDetailView):
    pass


@extend_schema_view(get=extend_schema(operation_id="organization_data_flow_revisions_list"))
class OrganizationDataFlowRevisionListView(DataFlowRevisionListView):
    pass


@extend_schema_view(get=extend_schema(operation_id="organization_data_flow_choices_retrieve"))
class OrganizationDataFlowChoicesView(DataFlowChoicesView):
    pass


class DataFlowSnapshotWriteSerializer(StrictSerializer):
    title = serializers.CharField(max_length=240, trim_whitespace=True)
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class DataFlowSnapshotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    reason = serializers.CharField()
    flow_count = serializers.IntegerField()
    content_digest = serializers.CharField()
    created_at = serializers.DateTimeField()


class DataFlowSnapshotResultSerializer(serializers.Serializer):
    results = DataFlowSnapshotSerializer(many=True)
    count = serializers.IntegerField()
    can_manage = serializers.BooleanField()


def _snapshot(workspace: ResolvedWorkspace, snapshot_id: UUID) -> DataFlowSnapshot:
    return get_object_or_404(snapshots_for_scope(workspace.data_scope), id=snapshot_id)


class DataFlowSnapshotListCreateView(APIView):
    @extend_schema(responses={200: DataFlowSnapshotResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.DATA_FLOWS_VIEW)
        records = list(snapshots_for_scope(workspace.data_scope)[:100])
        return Response(
            {
                "results": DataFlowSnapshotSerializer(records, many=True).data,
                "count": len(records),
                "can_manage": context_has_permission(
                    workspace.member, PermissionKey.DATA_FLOWS_EDIT, organization=workspace.organization
                ),
            }
        )

    @extend_schema(request=DataFlowSnapshotWriteSerializer, responses={201: DataFlowSnapshotSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.DATA_FLOWS_EDIT)
        serializer = DataFlowSnapshotWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            snapshot = create_data_flow_snapshot(
                workspace=workspace,
                actor_id=request.user.pk,
                title=serializer.validated_data["title"],
                reason=serializer.validated_data["reason"],
            )
        except DataFlowError as exc:
            raise _refuse(exc) from exc
        return Response(DataFlowSnapshotSerializer(snapshot).data, status=201)


class DataFlowSnapshotExportView(APIView):
    @extend_schema(responses={200: OpenApiResponse(description="Retained snapshot download")})
    def get(self, request, snapshot_id, export_format, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.DATA_FLOWS_VIEW)
        snapshot = _snapshot(workspace, snapshot_id)
        if export_format == "json":
            content: str | bytes = snapshot_json(snapshot)
            media_type = "application/json"
        elif export_format == "csv":
            content, media_type = snapshot_csv(snapshot), "text/csv"
        elif export_format == "svg":
            content, media_type = snapshot_svg(snapshot), "image/svg+xml"
        else:
            raise NotFound("That data-flow export format is not available.")
        response = HttpResponse(content, content_type=media_type)
        response["Content-Disposition"] = f'attachment; filename="data-flows-{snapshot.id}.{export_format}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response


@extend_schema_view(
    get=extend_schema(operation_id="msp_data_flow_snapshots_list"),
    post=extend_schema(operation_id="msp_data_flow_snapshots_create"),
)
class MSPDataFlowSnapshotListCreateView(DataFlowSnapshotListCreateView):
    pass


@extend_schema_view(get=extend_schema(operation_id="msp_data_flow_snapshot_export"))
class MSPDataFlowSnapshotExportView(DataFlowSnapshotExportView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="organization_data_flow_snapshots_list"),
    post=extend_schema(operation_id="organization_data_flow_snapshots_create"),
)
class OrganizationDataFlowSnapshotListCreateView(DataFlowSnapshotListCreateView):
    pass


@extend_schema_view(get=extend_schema(operation_id="organization_data_flow_snapshot_export"))
class OrganizationDataFlowSnapshotExportView(DataFlowSnapshotExportView):
    pass
