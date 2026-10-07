"""Staff-only, exact-owner coexistence diagnostics for legacy documents."""

from __future__ import annotations

from uuid import UUID

from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey

from .document_migration_coexistence import document_coexistence_status
from .document_views import _document, _msp_workspace, _organization_workspace
from .models import workspace_for_owner
from .workspaces import ResolvedWorkspace


class DocumentMigrationStatusSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    legacy_authoritative = serializers.BooleanField()
    cutover_ready = serializers.BooleanField()
    handoff_blockers = serializers.ListField(child=serializers.CharField())
    read_projection_state = serializers.ChoiceField(choices=("not_checked", "matched", "different", "unavailable"))
    content_copy_state = serializers.ChoiceField(
        choices=(
            "legacy_only",
            "repository_missing",
            "index_pending",
            "unsupported_legacy_shape",
            "partial_copy",
            "diverged",
            "in_sync",
        )
    )
    accepted_commit = serializers.CharField(allow_null=True)
    indexed_commit = serializers.CharField(allow_null=True)
    legacy_revision_id = serializers.UUIDField(allow_null=True)
    legacy_revision_ids = serializers.ListField(child=serializers.UUIDField())


def _status(workspace: ResolvedWorkspace, document_entity_id: UUID) -> Response:
    if workspace.member.surface == "client_portal":
        raise PermissionDenied("Migration status is unavailable to this audience")
    document = _document(workspace, document_entity_id)
    if document.organization_id != (workspace.organization.id if workspace.organization else None):
        raise Http404
    owner = workspace_for_owner(tenant=workspace.member.tenant, organization=workspace.organization)
    return Response(
        DocumentMigrationStatusSerializer(
            document_coexistence_status(workspace=owner, document=document, reader_workspace=workspace)
        ).data
    )


class MSPDocumentMigrationStatusView(APIView):
    @extend_schema(operation_id="documents_msp_migration_status", responses={200: DocumentMigrationStatusSerializer})
    def get(self, request, document_entity_id):  # type: ignore[no-untyped-def]
        return _status(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id)


class OrganizationDocumentMigrationStatusView(APIView):
    @extend_schema(
        operation_id="documents_organization_migration_status", responses={200: DocumentMigrationStatusSerializer}
    )
    def get(self, request, organization_entity_id, document_entity_id):  # type: ignore[no-untyped-def]
        return _status(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
        )
