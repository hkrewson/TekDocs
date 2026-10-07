"""Permission-scoped source reads and logical Git authoring endpoints."""

from __future__ import annotations

from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey

from .content_authoring import (
    ContentAuthoringConflict,
    ContentAuthoringError,
    author_content,
    read_authored_content,
    resolve_authored_path,
)
from .content_index import ContentIndexValidationError
from .content_read import repository_for_reader
from .document_views import _msp_workspace, _organization_workspace
from .repository_service import (
    RepositoryFileNotFoundError,
    RepositoryInputError,
    RepositoryReconciliationError,
    RepositoryServiceError,
)


class ContentAuthoringMutationSerializer(serializers.Serializer):
    operation = serializers.ChoiceField(choices=("create", "update", "move"))
    content_id = serializers.UUIDField()
    base_commit = serializers.CharField(max_length=64, allow_null=True, required=False, default=None)
    base_blob = serializers.CharField(max_length=64, allow_null=True, required=False, default=None)
    kind = serializers.ChoiceField(choices=("document", "fragment"), required=False, allow_null=True, default=None)
    path = serializers.CharField(max_length=512, required=False, allow_null=True, default=None)
    title = serializers.CharField(max_length=240, required=False, allow_null=True, default=None)
    markdown = serializers.CharField(
        max_length=1048576, allow_blank=True, required=False, allow_null=True, default=None
    )
    metadata_patch = serializers.DictField(required=False, default=dict)


class ContentAuthoringSourceSerializer(serializers.Serializer):
    content_id = serializers.UUIDField()
    path = serializers.CharField()
    kind = serializers.CharField()
    title = serializers.CharField()
    markdown = serializers.CharField(allow_blank=True)
    source = serializers.CharField()
    source_blob = serializers.CharField()
    accepted_commit = serializers.CharField(allow_null=True)
    indexed_commit = serializers.CharField(allow_null=True)


class ContentAuthoringConflictSerializer(serializers.Serializer):
    reason = serializers.CharField()
    base = serializers.CharField(allow_null=True)
    current = serializers.CharField(allow_null=True)
    proposed = serializers.CharField(allow_null=True)
    base_commit = serializers.CharField(allow_null=True)
    current_commit = serializers.CharField(allow_null=True)
    current_blob = serializers.CharField(allow_null=True)


class ContentPathQuerySerializer(serializers.Serializer):
    path = serializers.CharField(max_length=512)


def _workspace(request, organization_entity_id: UUID | None, permission: PermissionKey):  # type: ignore[no-untyped-def]
    workspace = (
        _organization_workspace(request, organization_entity_id, permission)
        if organization_entity_id is not None
        else _msp_workspace(request, permission)
    )
    if workspace.member.surface == "client_portal":
        raise PermissionDenied("Repository authoring is unavailable to this audience")
    return workspace


def _read(request, content_id: UUID, organization_entity_id: UUID | None = None) -> Response:  # type: ignore[no-untyped-def]
    repository = repository_for_reader(_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW))
    try:
        result = read_authored_content(repository=repository, content_id=content_id)
    except RepositoryFileNotFoundError:
        return Response({"detail": "Content does not exist"}, status=status.HTTP_404_NOT_FOUND)
    except RepositoryServiceError:
        return Response({"detail": "Repository source is unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(ContentAuthoringSourceSerializer(result).data)


def _resolve(request, organization_entity_id: UUID | None = None) -> Response:  # type: ignore[no-untyped-def]
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW)
    query = ContentPathQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    repository = repository_for_reader(workspace)
    try:
        result = resolve_authored_path(repository=repository, path=query.validated_data["path"])
    except (RepositoryFileNotFoundError, RepositoryInputError):
        return Response({"detail": "Content path is unavailable"}, status=status.HTTP_404_NOT_FOUND)
    except RepositoryServiceError:
        return Response({"detail": "Repository source is unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(ContentAuthoringSourceSerializer(result).data)


def _write(request, organization_entity_id: UUID | None = None) -> Response:  # type: ignore[no-untyped-def]
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT)
    serializer = ContentAuthoringMutationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    repository = repository_for_reader(workspace)
    try:
        result = author_content(
            repository=repository,
            actor_id=request.user.id,
            request_id=getattr(request, "request_id", None),
            **serializer.validated_data,
        )
    except ContentAuthoringConflict as exc:
        return Response(ContentAuthoringConflictSerializer(exc.payload).data, status=status.HTTP_409_CONFLICT)
    except ContentIndexValidationError as exc:
        return Response({"diagnostics": list(exc.diagnostics)}, status=status.HTTP_400_BAD_REQUEST)
    except (ContentAuthoringError, RepositoryInputError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except RepositoryReconciliationError:
        return Response({"detail": "Repository requires reconciliation"}, status=status.HTTP_409_CONFLICT)
    except RepositoryServiceError:
        return Response({"detail": "Repository authoring is unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(ContentAuthoringSourceSerializer(result).data, status=status.HTTP_200_OK)


class MSPContentAuthoringView(APIView):
    @extend_schema(
        operation_id="content_authoring_msp_write",
        request=ContentAuthoringMutationSerializer,
        responses={200: ContentAuthoringSourceSerializer, 409: ContentAuthoringConflictSerializer},
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        return _write(request)


class OrganizationContentAuthoringView(APIView):
    @extend_schema(
        operation_id="content_authoring_organization_write",
        request=ContentAuthoringMutationSerializer,
        responses={200: ContentAuthoringSourceSerializer, 409: ContentAuthoringConflictSerializer},
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _write(request, organization_entity_id)


class MSPContentAuthoringSourceView(APIView):
    @extend_schema(operation_id="content_authoring_msp_source", responses={200: ContentAuthoringSourceSerializer})
    def get(self, request, content_id):  # type: ignore[no-untyped-def]
        return _read(request, content_id)


class OrganizationContentAuthoringSourceView(APIView):
    @extend_schema(
        operation_id="content_authoring_organization_source", responses={200: ContentAuthoringSourceSerializer}
    )
    def get(self, request, organization_entity_id, content_id):  # type: ignore[no-untyped-def]
        return _read(request, content_id, organization_entity_id)


class MSPContentPathResolveView(APIView):
    @extend_schema(
        operation_id="content_authoring_msp_resolve_path",
        parameters=[ContentPathQuerySerializer],
        responses={200: ContentAuthoringSourceSerializer},
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        return _resolve(request)


class OrganizationContentPathResolveView(APIView):
    @extend_schema(
        operation_id="content_authoring_organization_resolve_path",
        parameters=[ContentPathQuerySerializer],
        responses={200: ContentAuthoringSourceSerializer},
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _resolve(request, organization_entity_id)
