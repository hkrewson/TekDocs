from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from django.http import FileResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .collection_pagination import BoundedCollectionQuerySerializer, OffsetPageSerializer, paginate
from .git_exports import create_git_export
from .integration_providers import provider_catalog
from .integrations import (
    cancel_sync_job,
    connections_for_workspace,
    create_connection,
    enqueue_sync,
    resolve_conflict,
    resolve_integration_workspace,
    rotate_connection_secret,
    update_connection,
)
from .models import (
    GitExportBundle,
    IntegrationConflict,
    IntegrationConflictStatus,
    IntegrationConnection,
    IntegrationLogEvent,
    IntegrationProvider,
    IntegrationSyncJob,
)
from .workspaces import ResolvedWorkspace

IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$")


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class ProviderCredentialFieldSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    secret = serializers.BooleanField()
    minimum_length = serializers.IntegerField()


class ProviderSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    version = serializers.CharField()
    direction = serializers.CharField()
    credential_fields = ProviderCredentialFieldSerializer(many=True)
    capabilities = serializers.ListField(child=serializers.CharField())
    object_types = serializers.ListField(child=serializers.CharField())
    pagination = serializers.CharField()
    minimum_sync_interval_minutes = serializers.IntegerField()
    maximum_sync_interval_minutes = serializers.IntegerField()
    health_states = serializers.ListField(child=serializers.CharField())
    observation_schema_version = serializers.IntegerField()


class ConnectionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    provider = serializers.CharField()
    name = serializers.CharField()
    base_url = serializers.CharField()
    credential_configured = serializers.SerializerMethodField()
    secret_generation = serializers.IntegerField()
    active = serializers.BooleanField()
    sync_interval_minutes = serializers.IntegerField()
    next_sync_at = serializers.DateTimeField()
    health_status = serializers.CharField()
    last_successful_sync_at = serializers.DateTimeField(allow_null=True)
    last_error_code = serializers.CharField()
    rate_limit_reset_at = serializers.DateTimeField(allow_null=True)
    reconciliation_counts = serializers.JSONField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_credential_configured(self, connection: IntegrationConnection) -> bool:
        return bool(connection.secret_envelope)


class ConnectionWriteSerializer(StrictSerializer):
    provider = serializers.ChoiceField(choices=IntegrationProvider.values)
    name = serializers.CharField(min_length=1, max_length=100, trim_whitespace=True)
    base_url = serializers.URLField(max_length=500)
    api_token = serializers.CharField(min_length=8, max_length=4096, trim_whitespace=False, write_only=True)
    sync_interval_minutes = serializers.IntegerField(min_value=5, max_value=10080, default=60)


class ConnectionUpdateSerializer(StrictSerializer):
    active = serializers.BooleanField()
    sync_interval_minutes = serializers.IntegerField(min_value=5, max_value=10080)


class CredentialRotationSerializer(StrictSerializer):
    api_token = serializers.CharField(min_length=8, max_length=4096, trim_whitespace=False, write_only=True)


class JobSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    connection_id = serializers.UUIDField()
    connection_name = serializers.CharField(source="connection.name")
    trigger = serializers.CharField()
    state = serializers.CharField()
    attempts = serializers.IntegerField()
    cursor_present = serializers.SerializerMethodField()
    last_error_code = serializers.CharField()
    result_counts = serializers.JSONField()
    available_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()

    def get_cursor_present(self, job: IntegrationSyncJob) -> bool:
        return bool(job.cursor_before or job.cursor_after)


class JobPageSerializer(OffsetPageSerializer):
    results = JobSerializer(many=True)


class JobStartSerializer(StrictSerializer):
    connection_id = serializers.UUIDField()


class LogSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    connection_id = serializers.UUIDField()
    connection_name = serializers.CharField(source="connection.name")
    job_id = serializers.UUIDField(allow_null=True)
    level = serializers.CharField()
    code = serializers.CharField()
    metrics = serializers.JSONField()
    occurred_at = serializers.DateTimeField()


class LogPageSerializer(OffsetPageSerializer):
    results = LogSerializer(many=True)


class ConflictSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    connection_id = serializers.UUIDField()
    connection_name = serializers.CharField(source="connection.name")
    local_entity_id = serializers.UUIDField(allow_null=True)
    remote_type = serializers.CharField()
    remote_id = serializers.CharField()
    difference = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    resolved_at = serializers.DateTimeField(allow_null=True)


class ConflictPageSerializer(OffsetPageSerializer):
    results = ConflictSerializer(many=True)


class ConflictResolutionSerializer(StrictSerializer):
    resolution = serializers.ChoiceField(
        choices=(
            IntegrationConflictStatus.KEEP_LOCAL,
            IntegrationConflictStatus.ACCEPT_REMOTE,
            IntegrationConflictStatus.IGNORED,
        )
    )


class GitExportWriteSerializer(StrictSerializer):
    document_ids = serializers.ListField(child=serializers.UUIDField(), max_length=250, default=list)
    publication_ids = serializers.ListField(child=serializers.UUIDField(), max_length=250, default=list)


class GitExportSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    selection_manifest = serializers.JSONField()
    content_digest = serializers.CharField()
    byte_size = serializers.IntegerField()
    created_at = serializers.DateTimeField()


def _workspace(request: Any, organization_entity_id: UUID | None, permission: PermissionKey) -> ResolvedWorkspace:
    return resolve_integration_workspace(
        request.user, organization_entity_id=organization_entity_id, permission=permission
    )


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    response["Pragma"] = "no-cache"
    return response


class IntegrationProviderCatalogView(APIView):
    @extend_schema(responses={200: ProviderSerializer(many=True)})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_VIEW)
        return _private(Response(provider_catalog()))


class IntegrationConnectionListCreateView(APIView):
    @extend_schema(responses={200: ConnectionSerializer(many=True)})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_VIEW)
        return _private(Response(ConnectionSerializer(connections_for_workspace(workspace), many=True).data))

    @extend_schema(request=ConnectionWriteSerializer, responses={201: ConnectionSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE)
        serializer = ConnectionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        connection = create_connection(
            request=request, organization_entity_id=organization_entity_id, **serializer.validated_data
        )
        return _private(Response(ConnectionSerializer(connection).data, status=201))


class IntegrationConnectionDetailView(APIView):
    @extend_schema(request=ConnectionUpdateSerializer, responses={200: ConnectionSerializer})
    def patch(self, request, connection_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE)
        serializer = ConnectionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        connection = update_connection(
            request=request,
            organization_entity_id=organization_entity_id,
            connection_id=connection_id,
            **serializer.validated_data,
        )
        return _private(Response(ConnectionSerializer(connection).data))


class IntegrationConnectionRotateView(APIView):
    @extend_schema(request=CredentialRotationSerializer, responses={200: ConnectionSerializer})
    def post(self, request, connection_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE)
        serializer = CredentialRotationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        connection = rotate_connection_secret(
            request=request,
            organization_entity_id=organization_entity_id,
            connection_id=connection_id,
            **serializer.validated_data,
        )
        return _private(Response(ConnectionSerializer(connection).data))


class IntegrationJobListCreateView(APIView):
    @extend_schema(responses={200: JobPageSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_VIEW)
        query = BoundedCollectionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = paginate(
            IntegrationSyncJob.scoped.for_scope(workspace.data_scope)
            .filter(workspace_id=workspace.data_scope.workspace_id)
            .select_related("connection"),
            **query.validated_data,
        )
        return _private(
            Response(
                {
                    "results": JobSerializer(page.records, many=True).data,
                    "page": page.page,
                    "page_size": page.page_size,
                    "count": page.count,
                    "has_more": page.has_more,
                }
            )
        )

    @extend_schema(
        request=JobStartSerializer,
        responses={202: JobSerializer, 409: OpenApiResponse(description="Idempotency key required")},
    )
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE)
        serializer = JobStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = request.headers.get("Idempotency-Key", "")
        if not IDEMPOTENCY_KEY.fullmatch(key):
            raise ValidationError({"idempotency_key": "Provide an 8–160 character Idempotency-Key header."})
        try:
            connection_id = serializer.validated_data["connection_id"]
            connection = connections_for_workspace(workspace).get(pk=connection_id, active=True)
        except IntegrationConnection.DoesNotExist as exc:
            raise NotFound("The active integration connection is unavailable.") from exc
        job = enqueue_sync(
            connection=connection, trigger="manual", requested_by_id=request.user.pk, idempotency_key=key
        )
        return _private(Response(JobSerializer(job).data, status=202))


class IntegrationJobCancelView(APIView):
    @extend_schema(request=None, responses={200: JobSerializer})
    def post(self, request, job_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE)
        job = cancel_sync_job(workspace=workspace, job_id=job_id, actor=request.user)
        return _private(Response(JobSerializer(job).data))


class IntegrationLogListView(APIView):
    @extend_schema(responses={200: LogPageSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_VIEW)
        query = BoundedCollectionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = paginate(
            IntegrationLogEvent.scoped.for_scope(workspace.data_scope)
            .filter(workspace_id=workspace.data_scope.workspace_id)
            .select_related("connection"),
            **query.validated_data,
        )
        return _private(
            Response(
                {
                    "results": LogSerializer(page.records, many=True).data,
                    "page": page.page,
                    "page_size": page.page_size,
                    "count": page.count,
                    "has_more": page.has_more,
                }
            )
        )


class IntegrationConflictListView(APIView):
    @extend_schema(responses={200: ConflictPageSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_VIEW)
        query = BoundedCollectionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = paginate(
            IntegrationConflict.scoped.for_scope(workspace.data_scope)
            .filter(workspace_id=workspace.data_scope.workspace_id)
            .select_related("connection"),
            **query.validated_data,
        )
        return _private(
            Response(
                {
                    "results": ConflictSerializer(page.records, many=True).data,
                    "page": page.page,
                    "page_size": page.page_size,
                    "count": page.count,
                    "has_more": page.has_more,
                }
            )
        )


class IntegrationConflictResolveView(APIView):
    @extend_schema(request=ConflictResolutionSerializer, responses={200: ConflictSerializer})
    def post(self, request, conflict_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE)
        serializer = ConflictResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conflict = resolve_conflict(
            workspace=workspace, conflict_id=conflict_id, actor=request.user, **serializer.validated_data
        )
        return _private(Response(ConflictSerializer(conflict).data))


class GitExportListCreateView(APIView):
    @extend_schema(responses={200: GitExportSerializer(many=True)})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_VIEW)
        require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization)
        bundles = GitExportBundle.scoped.for_scope(workspace.data_scope).filter(
            workspace_id=workspace.data_scope.workspace_id
        )[:100]
        return _private(Response(GitExportSerializer(bundles, many=True).data))

    @extend_schema(request=GitExportWriteSerializer, responses={201: GitExportSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE)
        require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization)
        serializer = GitExportWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bundle = create_git_export(workspace=workspace, actor=request.user, **serializer.validated_data)
        return _private(Response(GitExportSerializer(bundle).data, status=201))


class GitExportDownloadView(APIView):
    @extend_schema(responses={(200, "application/zip"): bytes})
    def get(self, request, bundle_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INTEGRATIONS_VIEW)
        require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization)
        try:
            bundle = GitExportBundle.scoped.for_scope(workspace.data_scope).get(
                workspace_id=workspace.data_scope.workspace_id, pk=bundle_id
            )
        except GitExportBundle.DoesNotExist as exc:
            raise NotFound("The Git export is unavailable.") from exc
        response = FileResponse(
            bundle.artifact.open("rb"),
            content_type="application/zip",
            as_attachment=True,
            filename=f"tekdocs-export-{bundle.id}.zip",
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
