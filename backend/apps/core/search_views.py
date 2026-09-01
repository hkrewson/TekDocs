from django.db import DatabaseError, connection, transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from .search_serializers import UnifiedWorkspaceSearchQuerySerializer, UnifiedWorkspaceSearchResultSerializer
from .workspace_search import search_workspace
from .workspaces import resolve_msp_workspace, resolve_organization_workspace


class WorkspaceSearchUnavailable(APIException):
    status_code = 503
    default_detail = "Search could not complete within its execution budget."
    default_code = "search_unavailable"


class WorkspaceSearchView(APIView):
    @extend_schema(
        operation_id="workspace_search",
        parameters=[UnifiedWorkspaceSearchQuerySerializer],
        responses={
            200: UnifiedWorkspaceSearchResultSerializer,
            400: OpenApiResponse(description="Invalid or over-broad search parameters"),
            403: OpenApiResponse(description="Workspace access required"),
            404: OpenApiResponse(description="Organization workspace not found"),
            503: OpenApiResponse(description="Search execution budget exceeded"),
        },
    )
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = (
            resolve_msp_workspace(request.user)
            if organization_entity_id is None
            else resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        )
        query = UnifiedWorkspaceSearchQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                if connection.vendor == "postgresql":
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL statement_timeout = %s", ["2000ms"])
                payload = search_workspace(
                    workspace=workspace,
                    query=query.validated_data.pop("q"),
                    **query.validated_data,
                )
        except DatabaseError as caught:
            raise WorkspaceSearchUnavailable from caught
        return Response(UnifiedWorkspaceSearchResultSerializer(payload).data)


@extend_schema_view(get=extend_schema(operation_id="workspace_search_msp"))
class MSPWorkspaceSearchView(WorkspaceSearchView):
    pass


@extend_schema_view(get=extend_schema(operation_id="workspace_search_organization"))
class OrganizationUnifiedSearchView(WorkspaceSearchView):
    pass
