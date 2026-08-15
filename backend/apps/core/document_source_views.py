from difflib import unified_diff
from uuid import UUID

from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey

from .document_sources import apply_remote_observation, fetch_remote_document, validate_remote_source_url
from .document_views import _document, _msp_workspace, _organization_workspace
from .documents import PlacementConflict
from .models import DocumentRemoteObservation, DocumentRemoteSource, DocumentSourceKind
from .workspaces import ResolvedWorkspace


class RemoteSourceWriteSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=500)
    source_kind = serializers.ChoiceField(choices=DocumentSourceKind.values, default=DocumentSourceKind.AUTO)
    enabled = serializers.BooleanField(default=True)
    check_interval_minutes = serializers.IntegerField(min_value=15, max_value=10080, default=1440)

    def validate_url(self, value: str) -> str:
        return validate_remote_source_url(value)


class RemoteSourceResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    url = serializers.URLField()
    source_kind = serializers.CharField()
    enabled = serializers.BooleanField()
    check_interval_minutes = serializers.IntegerField()
    next_check_at = serializers.DateTimeField()
    last_checked_at = serializers.DateTimeField(allow_null=True)
    last_applied_observation_id = serializers.UUIDField(allow_null=True)


class RemoteObservationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    state = serializers.CharField()
    status_code = serializers.IntegerField(allow_null=True)
    content_type = serializers.CharField()
    content_digest = serializers.CharField()
    error_code = serializers.CharField()
    fetched_at = serializers.DateTimeField()
    canonical_markdown = serializers.CharField()
    diff = serializers.SerializerMethodField()

    def get_diff(self, observation: DocumentRemoteObservation) -> str:
        source = observation.source
        prior = source.last_applied_observation
        before = prior.canonical_markdown if prior else ""
        return "".join(
            unified_diff(
                before.splitlines(keepends=True),
                observation.canonical_markdown.splitlines(keepends=True),
                fromfile="last-applied" if prior else "empty",
                tofile="observed",
            )
        )


class RemoteObservationListSerializer(serializers.Serializer):
    results = RemoteObservationSerializer(many=True)
    count = serializers.IntegerField()


def _source(workspace: ResolvedWorkspace, document_entity_id: UUID) -> DocumentRemoteSource:
    document = _document(workspace, document_entity_id)
    return get_object_or_404(
        DocumentRemoteSource.objects.select_related("last_applied_observation", "document"),
        document=document,
        archived_at__isnull=True,
    )


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
        return Response(RemoteObservationSerializer(observation).data, status=201)
    records = source.observations.all()[:50]
    return Response(
        {"results": RemoteObservationSerializer(records, many=True).data, "count": source.observations.count()}
    )


def _apply(workspace: ResolvedWorkspace, document_entity_id: UUID, observation_id: UUID, request: Request) -> Response:
    source = _source(workspace, document_entity_id)
    observation = get_object_or_404(source.observations.all(), id=observation_id)
    try:
        apply_remote_observation(observation=observation, actor_id=request.user.pk)
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
    @extend_schema(request=None, responses={200: RemoteObservationSerializer})
    def post(self, request: Request, document_entity_id: UUID, observation_id: UUID) -> Response:
        return _apply(
            _msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), document_entity_id, observation_id, request
        )


class OrganizationDocumentRemoteObservationApplyView(APIView):
    @extend_schema(request=None, responses={200: RemoteObservationSerializer})
    def post(
        self, request: Request, organization_entity_id: UUID, document_entity_id: UUID, observation_id: UUID
    ) -> Response:
        return _apply(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            document_entity_id,
            observation_id,
            request,
        )
