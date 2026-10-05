from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey

from .content_graph_serializers import (
    ContentGraphQuerySerializer,
    ContentGraphRebuildSerializer,
    ContentGraphSerializer,
)
from .content_index import (
    ContentIndexError,
    ContentIndexValidationError,
    content_graph_projection,
    index_repository_content,
)
from .document_views import _msp_workspace, _organization_workspace
from .models import WorkspaceRepository, workspace_for_owner
from .workspaces import ResolvedWorkspace


def _repository(resolved: ResolvedWorkspace) -> WorkspaceRepository:
    workspace = workspace_for_owner(tenant=resolved.member.tenant, organization=resolved.organization)
    return workspace.repository


def _get(resolved, request) -> Response:  # type: ignore[no-untyped-def]
    if resolved.member.surface == "client_portal":
        raise PermissionDenied("Repository content graph is unavailable to this audience")
    query = ContentGraphQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    audience = query.validated_data["audience"]
    repository = _repository(resolved)
    repository = type(repository).objects.select_related("accepted_commit", "indexed_commit").get(pk=repository.pk)
    return Response(
        ContentGraphSerializer(
            content_graph_projection(
                repository=repository,
                audience=None if audience == "all" else audience,
            )
        ).data
    )


def _post(resolved, request) -> Response:  # type: ignore[no-untyped-def]
    if resolved.member.surface == "client_portal":
        raise PermissionDenied("Repository content graph is unavailable to this audience")
    serializer = ContentGraphRebuildSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    repository = _repository(resolved)
    try:
        index_repository_content(repository_id=repository.id, force=serializer.validated_data["force"])
    except ContentIndexValidationError as exc:
        raise serializers.ValidationError({"diagnostics": list(exc.diagnostics)}) from exc
    except ContentIndexError as exc:
        raise serializers.ValidationError({"detail": str(exc)}) from exc
    return _get(resolved, request)


class MSPContentGraphView(APIView):
    @extend_schema(
        operation_id="content_graph_msp_retrieve",
        parameters=[ContentGraphQuerySerializer],
        responses={200: ContentGraphSerializer},
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        return _get(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), request)

    @extend_schema(
        operation_id="content_graph_msp_rebuild",
        request=ContentGraphRebuildSerializer,
        responses={200: ContentGraphSerializer},
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        return _post(_msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), request)


class OrganizationContentGraphView(APIView):
    @extend_schema(
        operation_id="content_graph_organization_retrieve",
        parameters=[ContentGraphQuerySerializer],
        responses={200: ContentGraphSerializer},
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _get(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            request,
        )

    @extend_schema(
        operation_id="content_graph_organization_rebuild",
        request=ContentGraphRebuildSerializer,
        responses={200: ContentGraphSerializer},
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _post(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            request,
        )
