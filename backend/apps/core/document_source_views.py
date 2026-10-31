from uuid import UUID

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey

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
    source = _source(workspace, document_entity_id)
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
    source = _source(workspace, document_entity_id)
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
