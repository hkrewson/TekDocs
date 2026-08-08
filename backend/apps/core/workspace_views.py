from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import WorkspaceContextSerializer
from .workspaces import resolve_msp_workspace, resolve_organization_workspace


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
            403: OpenApiResponse(description="Installation owner with MFA required"),
            404: OpenApiResponse(description="Organization workspace not found"),
            503: OpenApiResponse(description="Installation context unavailable"),
        }
    )
    def get(self, request, entity_id):  # type: ignore[no-untyped-def]
        workspace = resolve_organization_workspace(request.user, entity_id=entity_id)
        return Response(WorkspaceContextSerializer(workspace.as_response_data()).data)
