from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .rendering import render_markdown


class MarkdownRenderRequestSerializer(serializers.Serializer):
    markdown = serializers.CharField(allow_blank=True, max_length=1_000_000, trim_whitespace=False)


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
        require_permission(request.user, PermissionKey.DOCUMENTS_VIEW)
        serializer = MarkdownRenderRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = MarkdownRenderResponseSerializer(
            {"html": render_markdown(serializer.validated_data["markdown"])}
        )
        return Response(response.data)
