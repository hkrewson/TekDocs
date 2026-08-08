from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import WorkspaceContextSerializer, WorkspaceSearchQuerySerializer, WorkspaceSearchResultSerializer
from .workspaces import resolve_msp_workspace, resolve_organization_workspace, search_organization_workspaces


class MSPWorkspaceContextView(APIView):
    @extend_schema(
        responses={
            200: WorkspaceContextSerializer,
            403: OpenApiResponse(description="Installation membership required"),
            503: OpenApiResponse(description="Installation context unavailable"),
        }
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        workspace = resolve_msp_workspace(request.user)
        return Response(WorkspaceContextSerializer(workspace.as_response_data()).data)


class OrganizationWorkspaceContextView(APIView):
    @extend_schema(
        responses={
            200: WorkspaceContextSerializer,
            403: OpenApiResponse(description="Authorized organization workspace access required"),
            404: OpenApiResponse(description="Organization workspace not found"),
            503: OpenApiResponse(description="Installation context unavailable"),
        }
    )
    def get(self, request, entity_id):  # type: ignore[no-untyped-def]
        workspace = resolve_organization_workspace(request.user, entity_id=entity_id)
        return Response(WorkspaceContextSerializer(workspace.as_response_data()).data)


class OrganizationWorkspaceSearchView(APIView):
    @extend_schema(
        operation_id="workspaces_organizations_search",
        parameters=[WorkspaceSearchQuerySerializer],
        responses={
            200: WorkspaceSearchResultSerializer,
            400: OpenApiResponse(description="Invalid search parameters"),
            403: OpenApiResponse(description="Organization directory permission required"),
        },
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        query = WorkspaceSearchQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        results, has_more = search_organization_workspaces(
            request.user,
            query=values["q"],
            classification=values["classification"],
            page=values["page"],
            page_size=values["page_size"],
        )
        response = {
            "results": results,
            "page": values["page"],
            "page_size": values["page_size"],
            "has_more": has_more,
        }
        return Response(WorkspaceSearchResultSerializer(response).data)
