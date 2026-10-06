"""Scoped collection, document and operational-context reads for Git content."""

from __future__ import annotations

from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey

from .content_read import document_collection, document_detail, entity_documentation
from .document_views import _msp_workspace, _organization_workspace
from .workspaces import ResolvedWorkspace


class ContentReadQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    kind = serializers.ChoiceField(choices=("", "document", "fragment"), required=False, default="")
    topic = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    property_key = serializers.RegexField(r"^[a-z][a-z0-9_-]{0,79}$", required=False, allow_blank=True, default="")
    property_value = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    has_findings = serializers.BooleanField(required=False, default=False)
    unresolved_only = serializers.BooleanField(required=False, default=False)
    page = serializers.IntegerField(min_value=1, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False, default=25)


class ContentReadItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    title = serializers.CharField()
    path = serializers.CharField()
    topic = serializers.CharField(allow_null=True)
    finding_count = serializers.IntegerField()


class ContentReadCollectionSerializer(serializers.Serializer):
    results = ContentReadItemSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    accepted_commit = serializers.CharField(allow_null=True)
    indexed_commit = serializers.CharField(allow_null=True)


class ContentEntityContextSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    relationship = serializers.CharField()
    origin = serializers.CharField()
    display_name = serializers.CharField()
    entity_type = serializers.CharField()


class ContentFindingReadSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.CharField()
    detail = serializers.DictField()


class ContentReadDetailSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    title = serializers.CharField()
    path = serializers.CharField()
    indexed_commit = serializers.CharField()
    markdown = serializers.CharField(allow_blank=True)
    sanitized_html = serializers.CharField(allow_blank=True)
    entity_context = ContentEntityContextSerializer(many=True)
    findings = ContentFindingReadSerializer(many=True)


class EntityContentItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    kind = serializers.CharField()
    relationship = serializers.CharField()
    scope = serializers.ChoiceField(choices=("exact", "model", "class"))


class EntityContentSerializer(serializers.Serializer):
    entity_id = serializers.UUIDField()
    documents = EntityContentItemSerializer(many=True)
    indexed_commit = serializers.CharField(allow_null=True)


def _scope(request, organization_entity_id: UUID | None = None) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    resolved = (
        _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW)
        if organization_entity_id is not None
        else _msp_workspace(request, PermissionKey.DOCUMENTS_VIEW)
    )
    if resolved.member.surface == "client_portal":
        raise PermissionDenied("Repository content is unavailable to this audience")
    return resolved


class MSPContentReadCollectionView(APIView):
    @extend_schema(
        operation_id="content_read_msp_list",
        parameters=[ContentReadQuerySerializer],
        responses={200: ContentReadCollectionSerializer},
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        query = ContentReadQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(
            ContentReadCollectionSerializer(document_collection(workspace=_scope(request), **query.validated_data)).data
        )


class OrganizationContentReadCollectionView(APIView):
    @extend_schema(
        operation_id="content_read_organization_list",
        parameters=[ContentReadQuerySerializer],
        responses={200: ContentReadCollectionSerializer},
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        query = ContentReadQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(
            ContentReadCollectionSerializer(
                document_collection(workspace=_scope(request, organization_entity_id), **query.validated_data)
            ).data
        )


class MSPContentReadDetailView(APIView):
    @extend_schema(operation_id="content_read_msp_retrieve", responses={200: ContentReadDetailSerializer})
    def get(self, request, content_id):  # type: ignore[no-untyped-def]
        return Response(
            ContentReadDetailSerializer(
                document_detail(workspace=_scope(request), content_id=content_id, audience="msp_internal")
            ).data
        )


class OrganizationContentReadDetailView(APIView):
    @extend_schema(operation_id="content_read_organization_retrieve", responses={200: ContentReadDetailSerializer})
    def get(self, request, organization_entity_id, content_id):  # type: ignore[no-untyped-def]
        return Response(
            ContentReadDetailSerializer(
                document_detail(
                    workspace=_scope(request, organization_entity_id), content_id=content_id, audience="msp_internal"
                )
            ).data
        )


class MSPEntityContentView(APIView):
    @extend_schema(operation_id="content_entity_msp_retrieve", responses={200: EntityContentSerializer})
    def get(self, request, entity_id):  # type: ignore[no-untyped-def]
        return Response(
            EntityContentSerializer(entity_documentation(workspace=_scope(request), entity_id=entity_id)).data
        )


class OrganizationEntityContentView(APIView):
    @extend_schema(operation_id="content_entity_organization_retrieve", responses={200: EntityContentSerializer})
    def get(self, request, organization_entity_id, entity_id):  # type: ignore[no-untyped-def]
        return Response(
            EntityContentSerializer(
                entity_documentation(workspace=_scope(request, organization_entity_id), entity_id=entity_id)
            ).data
        )
