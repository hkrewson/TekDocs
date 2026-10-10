"""Permission-scoped source reads and logical Git authoring endpoints."""

from __future__ import annotations

from uuid import UUID

from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
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
from .content_index_models import ContentNode
from .content_read import repository_for_reader
from .document_attachments import (
    archive_document_attachment,
    create_repository_document_attachment,
    repository_attachment_archive_eligible,
)
from .document_file_serializers import DocumentAttachmentSerializer, DocumentAttachmentWriteSerializer
from .document_views import _msp_workspace, _organization_workspace
from .models import AuditEvent, DocumentAttachment, DocumentAttachmentPurpose, WorkspaceRepository
from .repository_editable_bundles import RepositoryEditableBundleError, export_repository_editable_bundle
from .repository_service import (
    RepositoryFileNotFoundError,
    RepositoryInputError,
    RepositoryReconciliationError,
    RepositoryServiceError,
)
from .repository_source_exports import RepositorySourceExportError, export_repository_sources
from .repository_storage import RepositoryStorageError
from .workspaces import ResolvedWorkspace


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


class ContentSourceExportQuerySerializer(serializers.Serializer):
    bundle = serializers.ChoiceField(choices=("editable",), required=False)


class RepositoryAttachmentQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, max_value=100_000, required=False, default=1)


class RepositoryAttachmentStatusSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    filename = serializers.CharField()
    size = serializers.IntegerField()
    linked_current = serializers.BooleanField()
    can_archive = serializers.BooleanField()


class RepositoryAttachmentPageSerializer(serializers.Serializer):
    results = RepositoryAttachmentStatusSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_more = serializers.BooleanField()


class RepositoryAttachmentIndexPending(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Repository content is not fully indexed"


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


def _upload_file(request, content_id: UUID, organization_entity_id: UUID | None = None) -> Response:  # type: ignore[no-untyped-def]
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT)
    serializer = DocumentAttachmentWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        repository = repository_for_reader(workspace)
    except WorkspaceRepository.DoesNotExist:
        return Response({"detail": "Repository document is unavailable"}, status=status.HTTP_404_NOT_FOUND)
    attachment = create_repository_document_attachment(
        repository=repository,
        content_id=content_id,
        actor_id=request.user.id,
        upload=serializer.validated_data["file"],
    )
    return Response(DocumentAttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)


def _locked_attachment_repository(workspace: ResolvedWorkspace, content_id: UUID) -> WorkspaceRepository:
    try:
        repository = repository_for_reader(workspace)
    except WorkspaceRepository.DoesNotExist as exc:
        raise Http404("Repository document is unavailable") from exc
    locked = get_object_or_404(
        WorkspaceRepository.objects.select_for_update().filter(
            pk=repository.pk, tenant=workspace.member.tenant, workspace=repository.workspace
        )
    )
    get_object_or_404(
        ContentNode.objects.filter(
            tenant=workspace.member.tenant,
            organization=workspace.organization,
            workspace=locked.workspace,
            repository=locked,
            kind="document",
        ),
        content_id=content_id,
    )
    if locked.accepted_commit_id is None or locked.accepted_commit_id != locked.indexed_commit_id:
        raise RepositoryAttachmentIndexPending()
    return locked


def _native_attachments(repository: WorkspaceRepository, content_id: UUID):  # type: ignore[no-untyped-def]
    return DocumentAttachment.objects.filter(
        tenant=repository.tenant,
        organization=repository.workspace.organization,
        owner_workspace=repository.workspace,
        owner_content_id=content_id,
        document__isnull=True,
        purpose=DocumentAttachmentPurpose.ATTACHMENT,
        archived_at__isnull=True,
    )


def _list_native_attachments(request, content_id: UUID, organization_entity_id: UUID | None = None) -> Response:  # type: ignore[no-untyped-def]
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW)
    query = RepositoryAttachmentQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    page = query.validated_data["page"]
    page_size = 25
    with transaction.atomic():
        repository = _locked_attachment_repository(workspace, content_id)
        records = _native_attachments(repository, content_id).order_by("-created_at", "id")
        count = records.count()
        results = []
        for attachment in records[(page - 1) * page_size:page * page_size]:
            linked, can_archive = repository_attachment_archive_eligible(repository=repository, attachment=attachment)
            results.append({
                "id": attachment.entity_id,
                "filename": attachment.original_filename,
                "size": attachment.size,
                "linked_current": linked,
                "can_archive": can_archive,
            })
        return Response(RepositoryAttachmentPageSerializer({
            "results": results,
            "count": count,
            "page": page,
            "page_size": page_size,
            "has_more": page * page_size < count,
        }).data)


def _archive_native_attachment(
    request: Request, content_id: UUID, attachment_entity_id: UUID, organization_entity_id: UUID | None = None
) -> Response:
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT)
    with transaction.atomic():
        repository = _locked_attachment_repository(workspace, content_id)
        attachment = get_object_or_404(_native_attachments(repository, content_id), entity_id=attachment_entity_id)
        _linked, can_archive = repository_attachment_archive_eligible(repository=repository, attachment=attachment)
        if not can_archive:
            return Response({"detail": "This file may be referenced by a saved Git revision"}, status=409)
        archive_document_attachment(attachment=attachment, actor_id=request.user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MSPContentAuthoringAttachmentView(APIView):
    parser_classes = (MultiPartParser,)

    @extend_schema(
        operation_id="content_authoring_msp_attachment_list",
        parameters=[RepositoryAttachmentQuerySerializer],
        responses={200: RepositoryAttachmentPageSerializer},
    )
    def get(self, request, content_id):  # type: ignore[no-untyped-def]
        return _list_native_attachments(request, content_id)

    @extend_schema(
        operation_id="content_authoring_msp_attachment_create",
        request=DocumentAttachmentWriteSerializer,
        responses={201: DocumentAttachmentSerializer},
    )
    def post(self, request, content_id):  # type: ignore[no-untyped-def]
        return _upload_file(request, content_id)


class OrganizationContentAuthoringAttachmentView(APIView):
    parser_classes = (MultiPartParser,)

    @extend_schema(
        operation_id="content_authoring_organization_attachment_list",
        parameters=[RepositoryAttachmentQuerySerializer],
        responses={200: RepositoryAttachmentPageSerializer},
    )
    def get(self, request, organization_entity_id, content_id):  # type: ignore[no-untyped-def]
        return _list_native_attachments(request, content_id, organization_entity_id)

    @extend_schema(
        operation_id="content_authoring_organization_attachment_create",
        request=DocumentAttachmentWriteSerializer,
        responses={201: DocumentAttachmentSerializer},
    )
    def post(self, request, organization_entity_id, content_id):  # type: ignore[no-untyped-def]
        return _upload_file(request, content_id, organization_entity_id)


class MSPContentAuthoringAttachmentDetailView(APIView):
    @extend_schema(operation_id="content_authoring_msp_attachment_archive", responses={204: None})
    def delete(self, request, content_id, attachment_entity_id):  # type: ignore[no-untyped-def]
        return _archive_native_attachment(request, content_id, attachment_entity_id)


class OrganizationContentAuthoringAttachmentDetailView(APIView):
    @extend_schema(operation_id="content_authoring_organization_attachment_archive", responses={204: None})
    def delete(self, request, organization_entity_id, content_id, attachment_entity_id):  # type: ignore[no-untyped-def]
        return _archive_native_attachment(request, content_id, attachment_entity_id, organization_entity_id)


def _source_snapshot(request, organization_entity_id: UUID | None = None) -> HttpResponse | Response:  # type: ignore[no-untyped-def]
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW)
    query = ContentSourceExportQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    editable = query.validated_data.get("bundle") == "editable"
    try:
        repository = repository_for_reader(workspace)
        if editable:
            bundle = export_repository_editable_bundle(repository)
            content = bundle.content
            accepted_commit = bundle.accepted_commit
            audit_metadata = {
                "accepted_commit": accepted_commit,
                "file_count": bundle.source_file_count,
                "attachment_count": bundle.attachment_count,
            }
        else:
            snapshot = export_repository_sources(repository)
            content = snapshot.content
            accepted_commit = snapshot.accepted_commit
            audit_metadata = {"accepted_commit": accepted_commit, "file_count": snapshot.file_count}
    except WorkspaceRepository.DoesNotExist:
        return Response({"detail": "Repository source is unavailable"}, status=status.HTTP_404_NOT_FOUND)
    except (RepositorySourceExportError, RepositoryEditableBundleError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    except (RepositoryServiceError, RepositoryStorageError):
        return Response({"detail": "Repository source is unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor=request.user,
        action="repository_editable_bundle.downloaded" if editable else "repository_source_export.downloaded",
        entity_id=repository.id,
        request_id=getattr(request, "request_id", None),
        metadata=audit_metadata,
    )
    response = HttpResponse(content, content_type="application/zip")
    name = "tekdocs-repository-editable" if editable else "tekdocs-repository"
    response["Content-Disposition"] = f'attachment; filename="{name}-{accepted_commit[:12]}.zip"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class MSPContentAuthoringExportView(APIView):
    @extend_schema(
        operation_id="content_authoring_msp_export",
        parameters=[ContentSourceExportQuerySerializer],
        responses={
            (200, "application/zip"): bytes,
            404: OpenApiResponse(description="Workspace repository is unavailable"),
            409: OpenApiResponse(description="Accepted and indexed heads do not match"),
            503: OpenApiResponse(description="Repository source is unavailable or exceeds limits"),
        },
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        return _source_snapshot(request)


class OrganizationContentAuthoringExportView(APIView):
    @extend_schema(
        operation_id="content_authoring_organization_export",
        parameters=[ContentSourceExportQuerySerializer],
        responses={
            (200, "application/zip"): bytes,
            404: OpenApiResponse(description="Workspace repository is unavailable"),
            409: OpenApiResponse(description="Accepted and indexed heads do not match"),
            503: OpenApiResponse(description="Repository source is unavailable or exceeds limits"),
        },
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _source_snapshot(request, organization_entity_id)


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
