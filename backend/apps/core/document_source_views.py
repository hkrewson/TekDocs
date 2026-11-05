from uuid import UUID

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey

from .content_authoring import AuthoredContent, ContentAuthoringError, read_authored_content
from .content_read import repository_for_reader
from .document_source_models import DocumentRemoteSource
from .document_source_serializers import (
    RemoteObservationApplySerializer,
    RemoteObservationListSerializer,
    RemoteObservationSerializer,
    RemoteSourceResultSerializer,
    RemoteSourceWriteSerializer,
)
from .document_sources import apply_remote_observation, fetch_remote_document
from .document_views import _document, _msp_workspace, _organization_workspace
from .documents import PlacementConflict
from .models import Document, WorkspaceRepository
from .repository_service import RepositoryServiceError
from .workspaces import ResolvedWorkspace


def _source(workspace: ResolvedWorkspace, document_entity_id: UUID) -> DocumentRemoteSource:
    document = _document(workspace, document_entity_id)
    return get_object_or_404(
        DocumentRemoteSource.objects.select_related("last_applied_observation", "document"),
        document=document,
        archived_at__isnull=True,
    )


@transaction.atomic
def _source_detail(workspace: ResolvedWorkspace, document_entity_id: UUID, request: Request) -> Response:
    document = _document(workspace, document_entity_id)
    if request.method == "GET":
        try:
            source = _source(workspace, document_entity_id)
        except Http404:
            return Response(status=204)
        return Response(RemoteSourceResultSerializer(source).data)
    serializer = RemoteSourceWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    from .models import Document

    Document.objects.select_for_update().get(pk=document.pk)
    # Serialize settings with polling, apply, and the authority handoff.
    list(DocumentRemoteSource.objects.select_for_update().filter(document=document))
    source, created = DocumentRemoteSource.objects.get_or_create(
        document=document,
        defaults={
            "tenant": workspace.member.tenant,
            "organization": workspace.organization,
            "created_by": request.user,
            **serializer.validated_data,
        },
    )
    if not created:
        for field, value in serializer.validated_data.items():
            setattr(source, field, value)
        source.archived_at = None
        source.save(update_fields=(*serializer.validated_data.keys(), "archived_at", "updated_at"))
    return Response(RemoteSourceResultSerializer(source).data, status=201)


def _observations(workspace: ResolvedWorkspace, document_entity_id: UUID, request: Request) -> Response:
    return _source_observations(_source(workspace, document_entity_id), request)


def _source_observations(source: DocumentRemoteSource, request: Request) -> Response:
    if request.method == "POST":
        observation = fetch_remote_document(source)
        from .document_source_git import source_uses_git

        # Polling holds the source row until the request commits. Do not take a
        # Git lock in this response: a writer may already hold Git while waiting
        # for this row. The reader obtains its review in a subsequent GET.
        review = (
            {"fingerprint": "", "blocker": "source_review_required", "diff": ""} if source_uses_git(source) else None
        )
        return Response(RemoteObservationSerializer(
            observation, context={"apply_reviews": {observation.id: review}},
        ).data, status=201)
    from .document_source_git import preview_remote_observations

    records = list(source.observations.all()[:50])
    reviews = preview_remote_observations(source=source, observations=records)
    return Response(
        {
            "results": RemoteObservationSerializer(records, many=True, context={"apply_reviews": reviews}).data,
            "count": source.observations.count(),
        }
    )


def _apply(workspace: ResolvedWorkspace, document_entity_id: UUID, observation_id: UUID, request: Request) -> Response:
    return _source_apply(_source(workspace, document_entity_id), observation_id, request)


def _source_apply(source: DocumentRemoteSource, observation_id: UUID, request: Request) -> Response:
    observation = get_object_or_404(source.observations.all(), id=observation_id)
    serializer = RemoteObservationApplySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        apply_remote_observation(
            observation=observation, actor_id=request.user.pk,
            review_fingerprint=serializer.validated_data.get("review_fingerprint"),
        )
    except PlacementConflict as exc:
        return Response({"code": "placement_conflict", "detail": str(exc)}, status=409)
    return Response(RemoteObservationSerializer(observation).data)


def _native_owner(
    workspace: ResolvedWorkspace, content_id: UUID, *, lock: bool = False,
) -> tuple[WorkspaceRepository, AuthoredContent]:
    try:
        repository = repository_for_reader(workspace)
        if lock:
            repository = WorkspaceRepository.objects.select_for_update().get(pk=repository.pk)
        authored = read_authored_content(repository=repository, content_id=content_id)
    except (WorkspaceRepository.DoesNotExist, ContentAuthoringError, RepositoryServiceError, ValueError) as exc:
        raise Http404 from exc
    if authored.kind != "document" or Document.objects.filter(
        pk=content_id,
        tenant_id=workspace.member.tenant.id,
        organization=workspace.organization,
    ).exists():
        raise Http404
    return repository, authored


def _native_source(workspace: ResolvedWorkspace, content_id: UUID) -> DocumentRemoteSource:
    repository, _authored = _native_owner(workspace, content_id)
    return get_object_or_404(
        DocumentRemoteSource.objects.select_related("last_applied_observation", "repository"),
        repository=repository, content_id=content_id, archived_at__isnull=True,
    )


@transaction.atomic
def _native_source_detail(workspace: ResolvedWorkspace, content_id: UUID, request: Request) -> Response:
    repository, _authored = _native_owner(workspace, content_id, lock=request.method != "GET")
    if request.method == "GET":
        try:
            source = _native_source(workspace, content_id)
        except Http404:
            return Response(status=204)
        return Response(RemoteSourceResultSerializer(source).data)
    serializer = RemoteSourceWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    list(DocumentRemoteSource.objects.select_for_update().filter(repository=repository, content_id=content_id))
    source, created = DocumentRemoteSource.objects.get_or_create(
        repository=repository,
        content_id=content_id,
        defaults={
            "tenant": workspace.member.tenant,
            "organization": workspace.organization,
            "created_by": request.user,
            **serializer.validated_data,
        },
    )
    if not created:
        for field, value in serializer.validated_data.items():
            setattr(source, field, value)
        source.archived_at = None
        source.save(update_fields=(*serializer.validated_data.keys(), "archived_at", "updated_at"))
    return Response(RemoteSourceResultSerializer(source).data, status=201)


class MSPNativeRemoteSourceView(APIView):
    @extend_schema(responses={200: RemoteSourceResultSerializer, 204: None})
    def get(self, request: Request, content_id: UUID) -> Response:
        return _native_source_detail(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), content_id, request)

    @extend_schema(request=RemoteSourceWriteSerializer, responses={201: RemoteSourceResultSerializer})
    def put(self, request: Request, content_id: UUID) -> Response:
        return _native_source_detail(_msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), content_id, request)


class OrganizationNativeRemoteSourceView(APIView):
    @extend_schema(responses={200: RemoteSourceResultSerializer, 204: None})
    def get(self, request: Request, organization_entity_id: UUID, content_id: UUID) -> Response:
        return _native_source_detail(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW), content_id, request,
        )

    @extend_schema(request=RemoteSourceWriteSerializer, responses={201: RemoteSourceResultSerializer})
    def put(self, request: Request, organization_entity_id: UUID, content_id: UUID) -> Response:
        return _native_source_detail(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT), content_id, request,
        )


class MSPNativeRemoteObservationView(APIView):
    @extend_schema(responses={200: RemoteObservationListSerializer})
    def get(self, request: Request, content_id: UUID) -> Response:
        workspace = _msp_workspace(request, PermissionKey.DOCUMENTS_VIEW)
        return _source_observations(_native_source(workspace, content_id), request)

    @extend_schema(request=None, responses={201: RemoteObservationSerializer})
    def post(self, request: Request, content_id: UUID) -> Response:
        workspace = _msp_workspace(request, PermissionKey.DOCUMENTS_EDIT)
        return _source_observations(_native_source(workspace, content_id), request)


class OrganizationNativeRemoteObservationView(APIView):
    @extend_schema(responses={200: RemoteObservationListSerializer})
    def get(self, request: Request, organization_entity_id: UUID, content_id: UUID) -> Response:
        workspace = _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW)
        return _source_observations(_native_source(workspace, content_id), request)

    @extend_schema(request=None, responses={201: RemoteObservationSerializer})
    def post(self, request: Request, organization_entity_id: UUID, content_id: UUID) -> Response:
        workspace = _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT)
        return _source_observations(_native_source(workspace, content_id), request)


class MSPNativeRemoteObservationApplyView(APIView):
    @extend_schema(request=RemoteObservationApplySerializer, responses={200: RemoteObservationSerializer})
    def post(self, request: Request, content_id: UUID, observation_id: UUID) -> Response:
        workspace = _msp_workspace(request, PermissionKey.DOCUMENTS_EDIT)
        return _source_apply(_native_source(workspace, content_id), observation_id, request)


class OrganizationNativeRemoteObservationApplyView(APIView):
    @extend_schema(request=RemoteObservationApplySerializer, responses={200: RemoteObservationSerializer})
    def post(
        self, request: Request, organization_entity_id: UUID, content_id: UUID, observation_id: UUID,
    ) -> Response:
        workspace = _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT)
        return _source_apply(_native_source(workspace, content_id), observation_id, request)


class MSPDocumentRemoteSourceView(APIView):
    @extend_schema(responses={200: RemoteSourceResultSerializer, 204: None})
    def get(self, request: Request, document_entity_id: UUID) -> Response:
        return _source_detail(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id, request)

    @extend_schema(request=RemoteSourceWriteSerializer, responses={201: RemoteSourceResultSerializer})
    def put(self, request: Request, document_entity_id: UUID) -> Response:
        return _source_detail(_msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), document_entity_id, request)


class OrganizationDocumentRemoteSourceView(APIView):
    @extend_schema(responses={200: RemoteSourceResultSerializer, 204: None})
    def get(self, request: Request, organization_entity_id: UUID, document_entity_id: UUID) -> Response:
        return _source_detail(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
            request,
        )

    @extend_schema(request=RemoteSourceWriteSerializer, responses={201: RemoteSourceResultSerializer})
    def put(self, request: Request, organization_entity_id: UUID, document_entity_id: UUID) -> Response:
        return _source_detail(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            document_entity_id,
            request,
        )


class MSPDocumentRemoteObservationView(APIView):
    @extend_schema(responses={200: RemoteObservationListSerializer})
    def get(self, request: Request, document_entity_id: UUID) -> Response:
        return _observations(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id, request)

    @extend_schema(request=None, responses={201: RemoteObservationSerializer})
    def post(self, request: Request, document_entity_id: UUID) -> Response:
        return _observations(_msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), document_entity_id, request)


class OrganizationDocumentRemoteObservationView(APIView):
    @extend_schema(responses={200: RemoteObservationListSerializer})
    def get(self, request: Request, organization_entity_id: UUID, document_entity_id: UUID) -> Response:
        return _observations(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
            request,
        )

    @extend_schema(request=None, responses={201: RemoteObservationSerializer})
    def post(self, request: Request, organization_entity_id: UUID, document_entity_id: UUID) -> Response:
        return _observations(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            document_entity_id,
            request,
        )


class MSPDocumentRemoteObservationApplyView(APIView):
    @extend_schema(request=RemoteObservationApplySerializer, responses={200: RemoteObservationSerializer})
    def post(self, request: Request, document_entity_id: UUID, observation_id: UUID) -> Response:
        return _apply(
            _msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), document_entity_id, observation_id, request
        )


class OrganizationDocumentRemoteObservationApplyView(APIView):
    @extend_schema(request=RemoteObservationApplySerializer, responses={200: RemoteObservationSerializer})
    def post(
        self, request: Request, organization_entity_id: UUID, document_entity_id: UUID, observation_id: UUID
    ) -> Response:
        return _apply(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            document_entity_id,
            observation_id,
            request,
        )
