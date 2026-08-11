from __future__ import annotations

from django.http import StreamingHttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey

from .collection_pagination import paginate
from .network_inventory_views import StrictSerializer, _workspace
from .network_transfer import (
    NETWORK_ENTITY_LABELS,
    NETWORK_ENTITY_SECTIONS,
    network_entities_for_scope,
    stream_network_csv,
)


class NetworkSearchQuerySerializer(StrictSerializer):
    q = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")
    page = serializers.IntegerField(min_value=1, max_value=10_000, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False, default=50)


class NetworkSearchItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    record_type = serializers.CharField()
    type_label = serializers.CharField()
    section = serializers.CharField()


class NetworkSearchResultSerializer(serializers.Serializer):
    results = NetworkSearchItemSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()


class NetworkSearchView(APIView):
    @extend_schema(parameters=[NetworkSearchQuerySerializer], responses={200: NetworkSearchResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        query = NetworkSearchQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        page = paginate(
            network_entities_for_scope(workspace.data_scope, values["q"]),
            page=values["page"],
            page_size=values["page_size"],
        )
        return Response(
            NetworkSearchResultSerializer(
                {
                    "results": [
                        {
                            "id": entity.id,
                            "name": entity.display_name,
                            "record_type": entity.entity_type,
                            "type_label": NETWORK_ENTITY_LABELS[entity.entity_type],
                            "section": NETWORK_ENTITY_SECTIONS[entity.entity_type],
                        }
                        for entity in page.records
                    ],
                    "page": page.page,
                    "page_size": page.page_size,
                    "count": page.count,
                    "has_more": page.has_more,
                }
            ).data
        )


class NetworkCsvExportView(APIView):
    @extend_schema(responses={200: OpenApiResponse(description="Exact-Workspace TekDocs network CSV export")})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        response = StreamingHttpResponse(
            stream_network_csv(workspace.data_scope), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = 'attachment; filename="tekdocs-networks.csv"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
