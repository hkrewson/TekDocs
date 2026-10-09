"""Scoped collection, document and operational-context reads for Git content."""

from __future__ import annotations

from uuid import UUID

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey

from .content_index_models import ContentNode
from .content_read import document_collection, document_detail, entity_documentation, repository_for_reader
from .document_exports import export_docx, export_html
from .document_views import _msp_workspace, _organization_workspace
from .models import AuditEvent
from .rendering import render_pdf
from .workspaces import ResolvedWorkspace

MAX_HTML_EXPORT_BYTES = 4 * 1024 * 1024
MAX_PDF_EXPORT_BYTES = 8 * 1024 * 1024
MAX_DOCX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_DOCX_EXPORT_BYTES = 8 * 1024 * 1024


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
        workspace = _scope(request)
        query = ContentReadQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(
            ContentReadCollectionSerializer(document_collection(workspace=workspace, **query.validated_data)).data
        )


class OrganizationContentReadCollectionView(APIView):
    @extend_schema(
        operation_id="content_read_organization_list",
        parameters=[ContentReadQuerySerializer],
        responses={200: ContentReadCollectionSerializer},
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _scope(request, organization_entity_id)
        query = ContentReadQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(
            ContentReadCollectionSerializer(
                document_collection(workspace=workspace, **query.validated_data)
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


def _export_document_html(request, workspace: ResolvedWorkspace, content_id: UUID) -> HttpResponse | Response:  # type: ignore[no-untyped-def]
    """Export one staff-visible accepted/indexed projection, never a STATIC artifact."""

    repository = repository_for_reader(workspace)
    get_object_or_404(ContentNode.objects.filter(repository=repository, kind="document"), content_id=content_id)
    accepted = repository.accepted_commit
    if accepted is None or accepted.id != repository.indexed_commit_id:
        return Response({"detail": "Repository content is not fully indexed"}, status=409)
    revision = accepted.object_id
    detail = document_detail(workspace=workspace, content_id=content_id, audience="msp_internal")
    repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
    current = repository.accepted_commit
    if (
        current is None
        or current.id != repository.indexed_commit_id
        or current.object_id != revision
        or detail["indexed_commit"] != revision
    ):
        return Response({"detail": "Repository content changed during export"}, status=409)
    content = export_html(
        title=detail["title"], markdown=detail["markdown"], retained_html=detail["sanitized_html"]
    )
    if len(content) > MAX_HTML_EXPORT_BYTES:
        return Response({"detail": "Repository HTML export exceeds the size limit"}, status=409)
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor=request.user,
        action="repository_document.exported",
        entity_id=content_id,
        request_id=getattr(request, "request_id", None),
        metadata={"format": "html", "accepted_commit": revision},
    )
    response = HttpResponse(content, content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="repository-document.html"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    response["X-TekDocs-Export-Class"] = "live_repository_revision"
    response["X-TekDocs-Repository-Commit"] = revision
    return response


class MSPContentReadHTMLExportView(APIView):
    @extend_schema(
        operation_id="content_read_msp_html_export",
        responses={(200, "text/html"): bytes, 409: OpenApiResponse(description="Repository revision conflict")},
    )
    def get(self, request, content_id):  # type: ignore[no-untyped-def]
        return _export_document_html(request, _scope(request), content_id)


class OrganizationContentReadHTMLExportView(APIView):
    @extend_schema(
        operation_id="content_read_organization_html_export",
        responses={(200, "text/html"): bytes, 409: OpenApiResponse(description="Repository revision conflict")},
    )
    def get(self, request, organization_entity_id, content_id):  # type: ignore[no-untyped-def]
        return _export_document_html(request, _scope(request, organization_entity_id), content_id)


def _export_document_pdf(request, workspace: ResolvedWorkspace, content_id: UUID) -> HttpResponse | Response:  # type: ignore[no-untyped-def]
    """Export the same staff-authorized projection as HTML, never a retained STATIC publication."""

    repository = repository_for_reader(workspace)
    get_object_or_404(ContentNode.objects.filter(repository=repository, kind="document"), content_id=content_id)
    accepted = repository.accepted_commit
    if accepted is None or accepted.id != repository.indexed_commit_id:
        return Response({"detail": "Repository content is not fully indexed"}, status=409)
    revision = accepted.object_id
    detail = document_detail(
        workspace=workspace, content_id=content_id, audience="msp_internal", include_render_context=True
    )
    repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
    current = repository.accepted_commit
    if (
        current is None
        or current.id != repository.indexed_commit_id
        or current.object_id != revision
        or detail["indexed_commit"] != revision
    ):
        return Response({"detail": "Repository content changed during export"}, status=409)
    if len(detail["markdown"].encode("utf-8")) > MAX_HTML_EXPORT_BYTES:
        return Response({"detail": "Repository PDF source exceeds the size limit"}, status=409)
    content = render_pdf(detail["markdown"], title=detail["title"], **detail["_render_context"])
    if not content.startswith(b"%PDF-") or len(content) > MAX_PDF_EXPORT_BYTES:
        return Response({"detail": "Repository PDF export exceeds the size limit"}, status=409)
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor=request.user,
        action="repository_document.exported",
        entity_id=content_id,
        request_id=getattr(request, "request_id", None),
        metadata={"format": "pdf", "accepted_commit": revision},
    )
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="repository-document.pdf"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-TekDocs-Export-Class"] = "live_repository_revision"
    response["X-TekDocs-Repository-Commit"] = revision
    return response


class MSPContentReadPDFExportView(APIView):
    @extend_schema(
        operation_id="content_read_msp_pdf_export",
        responses={(200, "application/pdf"): bytes, 409: OpenApiResponse(description="Repository revision conflict")},
    )
    def get(self, request, content_id):  # type: ignore[no-untyped-def]
        return _export_document_pdf(request, _scope(request), content_id)


class OrganizationContentReadPDFExportView(APIView):
    @extend_schema(
        operation_id="content_read_organization_pdf_export",
        responses={(200, "application/pdf"): bytes, 409: OpenApiResponse(description="Repository revision conflict")},
    )
    def get(self, request, organization_entity_id, content_id):  # type: ignore[no-untyped-def]
        return _export_document_pdf(request, _scope(request, organization_entity_id), content_id)


def _export_document_docx(request, workspace: ResolvedWorkspace, content_id: UUID) -> HttpResponse | Response:  # type: ignore[no-untyped-def]
    """Export a staff-authorized live revision, not a retained STATIC publication."""

    repository = repository_for_reader(workspace)
    get_object_or_404(ContentNode.objects.filter(repository=repository, kind="document"), content_id=content_id)
    accepted = repository.accepted_commit
    if accepted is None or accepted.id != repository.indexed_commit_id:
        return Response({"detail": "Repository content is not fully indexed"}, status=409)
    revision = accepted.object_id
    detail = document_detail(
        workspace=workspace, content_id=content_id, audience="msp_internal", include_render_context=True
    )
    repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
    current = repository.accepted_commit
    if (
        current is None
        or current.id != repository.indexed_commit_id
        or current.object_id != revision
        or detail["indexed_commit"] != revision
    ):
        return Response({"detail": "Repository content changed during export"}, status=409)
    if len(detail["markdown"].encode("utf-8")) > MAX_DOCX_SOURCE_BYTES:
        return Response({"detail": "Repository DOCX source exceeds the size limit"}, status=409)
    content = export_docx(title=detail["title"], markdown=detail["markdown"], **detail["_render_context"])
    if not content.startswith(b"PK\x03\x04") or len(content) > MAX_DOCX_EXPORT_BYTES:
        return Response({"detail": "Repository DOCX export exceeds the size limit"}, status=409)
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor=request.user,
        action="repository_document.exported",
        entity_id=content_id,
        request_id=getattr(request, "request_id", None),
        metadata={"format": "docx", "accepted_commit": revision},
    )
    response = HttpResponse(
        content, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    response["Content-Disposition"] = 'attachment; filename="repository-document.docx"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-TekDocs-Export-Class"] = "live_repository_revision"
    response["X-TekDocs-Repository-Commit"] = revision
    return response


class MSPContentReadDOCXExportView(APIView):
    @extend_schema(
        operation_id="content_read_msp_docx_export",
        responses={
            (200, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"): bytes,
            409: OpenApiResponse(description="Repository revision conflict"),
        },
    )
    def get(self, request, content_id):  # type: ignore[no-untyped-def]
        return _export_document_docx(request, _scope(request), content_id)


class OrganizationContentReadDOCXExportView(APIView):
    @extend_schema(
        operation_id="content_read_organization_docx_export",
        responses={
            (200, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"): bytes,
            409: OpenApiResponse(description="Repository revision conflict"),
        },
    )
    def get(self, request, organization_entity_id, content_id):  # type: ignore[no-untyped-def]
        return _export_document_docx(request, _scope(request, organization_entity_id), content_id)


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
