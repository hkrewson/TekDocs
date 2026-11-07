from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_installation_member, require_permission

from .diagram_exports import DiagramRenderError, render_diagram_exports
from .document_attachments import resolve_rendered_attachments
from .document_key_freeze import expand_rendered_content_keys
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


class DiagramPreviewThrottle(UserRateThrottle):
    scope = "diagram_previews"


class DiagramPreviewRequestSerializer(serializers.Serializer):
    source = serializers.CharField(allow_blank=False, max_length=50_000, trim_whitespace=False)


class DiagramPreviewResponseSerializer(serializers.Serializer):
    svg = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    renderer_version = serializers.CharField()


class DiagramPreviewView(APIView):
    throttle_classes = [DiagramPreviewThrottle]

    @extend_schema(
        request=DiagramPreviewRequestSerializer,
        responses={
            200: DiagramPreviewResponseSerializer,
            400: OpenApiResponse(description="Invalid or oversized Mermaid source"),
            403: OpenApiResponse(description="Installation membership required"),
            429: OpenApiResponse(description="Diagram preview rate exceeded"),
            503: OpenApiResponse(description="Isolated diagram renderer unavailable"),
        },
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        require_installation_member(request.user)
        serializer = DiagramPreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source = serializer.validated_data["source"]
        if "```" in source:
            raise serializers.ValidationError({"source": ["Diagram source contains an invalid fence."]})
        try:
            artifacts = render_diagram_exports(f"```mermaid\n{source}\n```\n", required=True)
        except DiagramRenderError as error:
            unavailable = error.code in {
                "diagram.renderer.busy",
                "diagram.renderer.timeout",
                "diagram.renderer.unavailable",
                "diagram.renderer.invalid_response",
            }
            return Response(
                {"code": error.code, "detail": str(error)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE if unavailable else status.HTTP_400_BAD_REQUEST,
            )
        if len(artifacts) != 1:
            return Response(
                {
                    "code": "diagram.renderer.invalid_response",
                    "detail": "The isolated diagram renderer returned an invalid preview.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        artifact = artifacts[0]
        if artifact.svg is None:
            return Response(
                {
                    "code": "diagram.renderer.invalid_response",
                    "detail": "The isolated diagram renderer returned an invalid preview.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        response = DiagramPreviewResponseSerializer(
            {
                "svg": artifact.svg.decode("utf-8"),
                "title": artifact.source.title,
                "description": artifact.source.description,
                "renderer_version": artifact.renderer_version,
            }
        )
        return Response(response.data)


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
        rendered_markdown = expand_rendered_content_keys(
            workspace=workspace, document=document, markdown=markdown
        )
        response = MarkdownRenderResponseSerializer(
            {
                "html": render_markdown(
                    rendered_markdown,
                    entity_mentions=resolve_entity_mentions(workspace=workspace, markdown=rendered_markdown),
                    attachments=resolve_rendered_attachments(
                        workspace=workspace,
                        document=document,
                        markdown=rendered_markdown,
                    ),
                    key_resolutions=resolve_rendered_keys(
                        workspace=workspace,
                        document=document,
                        markdown=rendered_markdown,
                    ),
                )
            }
        )
        return Response(response.data)
