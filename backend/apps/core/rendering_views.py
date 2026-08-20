from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_installation_member, require_permission

from .document_attachments import resolve_rendered_attachments
from .document_key_resolution import resolve_rendered_keys
from .documents import documents_for_scope
from .entity_mentions import resolve_entity_mentions
from .rendering import render_markdown
from .workspaces import resolve_msp_workspace, resolve_organization_workspace


class MarkdownRenderRequestSerializer(serializers.Serializer):
    markdown = serializers.CharField(allow_blank=True, max_length=1_000_000, trim_whitespace=False)
    organization_id = serializers.UUIDField(required=False, allow_null=True)
    document_id = serializers.UUIDField(required=False, allow_null=True)


class MarkdownRenderResponseSerializer(serializers.Serializer):
    html = serializers.CharField(allow_blank=True)


class MarkdownRenderView(APIView):
    @extend_schema(
        request=MarkdownRenderRequestSerializer,
        responses={
            200: MarkdownRenderResponseSerializer,
            400: OpenApiResponse(description="Invalid or oversized Markdown"),
            403: OpenApiResponse(description="Documentation view permission required"),
        },
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        require_installation_member(request.user)
        serializer = MarkdownRenderRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization_id = serializer.validated_data.get("organization_id")
        workspace = (
            resolve_organization_workspace(request.user, entity_id=organization_id)
            if organization_id is not None
            else resolve_msp_workspace(request.user)
        )
        require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization)
        markdown = serializer.validated_data["markdown"]
        document_id = serializer.validated_data.get("document_id")
        document = (
            get_object_or_404(documents_for_scope(workspace.data_scope), entity_id=document_id)
            if document_id is not None
            else None
        )
        response = MarkdownRenderResponseSerializer(
            {
                "html": render_markdown(
                    markdown,
                    entity_mentions=resolve_entity_mentions(workspace=workspace, markdown=markdown),
                    attachments=resolve_rendered_attachments(
                        workspace=workspace,
                        document=document,
                        markdown=markdown,
                    ),
                    key_resolutions=resolve_rendered_keys(
                        workspace=workspace,
                        document=document,
                        markdown=markdown,
                    ),
                )
            }
        )
        return Response(response.data)
