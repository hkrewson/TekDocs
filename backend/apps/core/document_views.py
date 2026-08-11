from typing import cast
from uuid import UUID

from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from django.utils.text import slugify
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .document_attachments import (
    MAX_MARKDOWN_IMPORT_BYTES,
    archive_document_attachment,
    create_document_attachment,
    open_document_attachment,
)
from .document_reuse import reuse_impact_for_placement
from .documents import (
    PlacementConflict,
    RevisionConflict,
    add_document_placement,
    add_listing_reference,
    archive_document,
    create_document,
    detach_document_placement,
    documents_for_scope,
    instantiate_document_template,
    remove_document_placement,
    remove_listing_reference,
    resolve_document,
    revision_diff,
    revisions_for_document,
    update_document,
    update_document_placement,
    update_shared_block,
)
from .models import (
    Document,
    DocumentationListingReference,
    DocumentAttachment,
    DocumentPublication,
    DocumentPublicationArtifact,
)
from .publications import (
    PublicationConflict,
    approve_publication,
    canonical_json,
    publish_document,
    read_publication_artifact,
    withdraw_publication,
)
from .relationships import search_entities
from .scoping import DataScope
from .serializers import (
    BlockRevisionDetailSerializer,
    BlockRevisionListQuerySerializer,
    BlockRevisionResultSerializer,
    DocumentationReferenceSerializer,
    DocumentationReferenceWriteSerializer,
    DocumentAttachmentSerializer,
    DocumentAttachmentWriteSerializer,
    DocumentCreateSerializer,
    DocumentListQuerySerializer,
    DocumentPlacementUpdateSerializer,
    DocumentPlacementWriteSerializer,
    DocumentPublicationControlWriteSerializer,
    DocumentPublicationDetailSerializer,
    DocumentPublicationResultSerializer,
    DocumentPublicationWriteSerializer,
    DocumentResultSerializer,
    DocumentSerializer,
    DocumentTemplateInstantiateSerializer,
    DocumentUpdateSerializer,
    EntityMentionResultSerializer,
    EntityMentionSearchQuerySerializer,
    MarkdownImportSerializer,
    ReuseImpactSerializer,
    RevisionConflictSerializer,
    SharedBlockUpdateSerializer,
)
from .workspaces import ResolvedWorkspace, resolve_organization_workspace


def _msp_workspace(request, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    member = require_permission(request.user, permission)
    return ResolvedWorkspace(
        member=member,
        kind="msp",
        id=member.tenant.id,
        name=member.tenant.name,
        data_scope=DataScope.tenant(member.tenant),
        classifications=(),
        capabilities=("documentation",),
    )


def _organization_workspace(request, organization_entity_id: UUID, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    workspace = resolve_organization_workspace(request.user, entity_id=organization_entity_id)
    require_permission(request.user, permission, organization=workspace.organization)
    return workspace


def _document(workspace: ResolvedWorkspace, document_entity_id: UUID):  # type: ignore[no-untyped-def]
    return get_object_or_404(documents_for_scope(workspace.data_scope), entity_id=document_entity_id)


def _list(workspace: ResolvedWorkspace, request: Request) -> Response:
    serializer = DocumentListQuerySerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    queryset = documents_for_scope(workspace.data_scope)
    if values["q"]:
        queryset = queryset.filter(entity__display_name__icontains=values["q"])
    if values["category"]:
        queryset = queryset.filter(category=values["category"])
    if values["template"] == "documents":
        queryset = queryset.filter(is_template=False)
    elif values["template"] == "templates":
        queryset = queryset.filter(is_template=True)
    records = list(queryset.order_by("entity__display_name", "entity_id")[:500])
    context = {"workspace_organization_id": workspace.organization.id if workspace.organization else None}
    return Response(DocumentResultSerializer({"results": records, "count": len(records)}, context=context).data)


def _create(workspace: ResolvedWorkspace, request) -> Response:  # type: ignore[no-untyped-def]
    serializer = DocumentCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    document = create_document(
        tenant=workspace.member.tenant,
        organization=workspace.organization,
        actor_id=request.user.pk,
        title=serializer.validated_data["title"],
        markdown=serializer.validated_data.get("markdown", ""),
        category=serializer.validated_data["category"],
        is_template=serializer.validated_data["is_template"],
    )
    return Response(DocumentSerializer(_document(workspace, document.entity_id)).data, status=201)


def _retrieve(workspace: ResolvedWorkspace, document_entity_id: UUID) -> Response:
    context = {"workspace_organization_id": workspace.organization.id if workspace.organization else None}
    return Response(DocumentSerializer(_document(workspace, document_entity_id), context=context).data)


def _mutate_workspace(request, workspace: ResolvedWorkspace, document):  # type: ignore[no-untyped-def]
    if document.organization_id is None and workspace.organization is not None:
        require_permission(request.user, PermissionKey.DOCUMENTS_EDIT)


def _update(workspace: ResolvedWorkspace, document_entity_id: UUID, request) -> Response:  # type: ignore[no-untyped-def]
    document = _document(workspace, document_entity_id)
    _mutate_workspace(request, workspace, document)
    serializer = DocumentUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        update_document(document=document, actor_id=request.user.pk, **serializer.validated_data)
    except RevisionConflict as conflict:
        return _revision_conflict_response(conflict)
    return _retrieve(workspace, document_entity_id)


def _instantiate_template(workspace: ResolvedWorkspace, request: Request) -> Response:
    serializer = DocumentTemplateInstantiateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    source = _document(workspace, serializer.validated_data["source_document_id"])
    try:
        document = instantiate_document_template(
            source=source,
            tenant=workspace.member.tenant,
            organization=workspace.organization,
            actor_id=request.user.pk,
            title=serializer.validated_data["title"],
            category=serializer.validated_data["category"],
        )
    except PlacementConflict as conflict:
        return _placement_conflict(conflict)
    return Response(DocumentSerializer(_document(workspace, document.entity_id)).data, status=201)


def _import_markdown(workspace: ResolvedWorkspace, request: Request) -> Response:
    serializer = MarkdownImportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    upload = serializer.validated_data["file"]
    if not str(upload.name).lower().endswith(".md"):
        return Response({"file": ["Markdown imports must use a .md filename."]}, status=400)
    content = upload.read(MAX_MARKDOWN_IMPORT_BYTES + 1)
    if len(content) > MAX_MARKDOWN_IMPORT_BYTES:
        return Response({"file": ["Markdown imports may not exceed 1 MiB."]}, status=400)
    if b"\x00" in content:
        return Response({"file": ["Markdown imports must not contain binary data."]}, status=400)
    try:
        markdown = content.decode("utf-8")
    except UnicodeDecodeError:
        return Response({"file": ["Markdown imports must use UTF-8."]}, status=400)
    document = create_document(
        tenant=workspace.member.tenant,
        organization=workspace.organization,
        actor_id=request.user.pk,
        title=serializer.validated_data["title"],
        markdown=markdown,
        category=serializer.validated_data["category"],
        is_template=serializer.validated_data["is_template"],
    )
    return Response(DocumentSerializer(_document(workspace, document.entity_id)).data, status=201)


def _export_markdown(workspace: ResolvedWorkspace, document_entity_id: UUID) -> HttpResponse:
    document = _document(workspace, document_entity_id)
    filename = f"{slugify(document.entity.display_name) or 'document'}.md"
    response = HttpResponse(
        resolve_document(document).markdown.encode("utf-8"), content_type="text/markdown; charset=utf-8"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _attachment(
    workspace: ResolvedWorkspace, document_entity_id: UUID, attachment_entity_id: UUID
) -> tuple[Document, DocumentAttachment]:
    document = _document(workspace, document_entity_id)
    attachment = get_object_or_404(
        DocumentAttachment.objects.filter(
            tenant=workspace.member.tenant,
            document=document,
            archived_at__isnull=True,
            scan_status="clean",
        ),
        entity_id=attachment_entity_id,
    )
    return document, attachment


def _upload_attachment(workspace: ResolvedWorkspace, document_entity_id: UUID, request: Request) -> Response:
    document = _document(workspace, document_entity_id)
    _mutate_workspace(request, workspace, document)
    serializer = DocumentAttachmentWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    attachment = create_document_attachment(
        document=document,
        actor_id=request.user.pk,
        upload=serializer.validated_data["file"],
    )
    return Response(DocumentAttachmentSerializer(attachment).data, status=201)


def _download_attachment(
    workspace: ResolvedWorkspace, document_entity_id: UUID, attachment_entity_id: UUID
) -> FileResponse:
    _document_record, attachment = _attachment(workspace, document_entity_id, attachment_entity_id)
    response = FileResponse(
        open_document_attachment(attachment),
        as_attachment=True,
        filename=attachment.original_filename,
        content_type="application/octet-stream",
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _archive_attachment(
    workspace: ResolvedWorkspace, document_entity_id: UUID, attachment_entity_id: UUID, request: Request
) -> Response:
    document, attachment = _attachment(workspace, document_entity_id, attachment_entity_id)
    _mutate_workspace(request, workspace, document)
    archive_document_attachment(attachment=attachment, actor_id=request.user.pk)
    return Response(status=204)


def _publication_records(document: Document):  # type: ignore[no-untyped-def]
    return DocumentPublication.objects.filter(tenant=document.tenant, document=document).select_related(
        "entity", "document", "document__entity", "published_by", "supersedes__entity"
    ).prefetch_related(
        "artifacts",
        "artifacts__entity",
        "artifacts__source_attachment__entity",
        "control_events__actor",
        "successors__control_events",
    )


def _publication(
    workspace: ResolvedWorkspace, document_entity_id: UUID, publication_entity_id: UUID
) -> DocumentPublication:
    document = _document(workspace, document_entity_id)
    return cast(
        DocumentPublication,
        get_object_or_404(_publication_records(document), entity_id=publication_entity_id),
    )


def _list_publications(workspace: ResolvedWorkspace, document_entity_id: UUID) -> Response:
    document = _document(workspace, document_entity_id)
    records = list(_publication_records(document).order_by("-published_at", "id")[:200])
    return Response(DocumentPublicationResultSerializer({"results": records, "count": len(records)}).data)


def _publish(workspace: ResolvedWorkspace, document_entity_id: UUID, request: Request) -> Response:
    document = _document(workspace, document_entity_id)
    workspace_organization_id = workspace.organization.id if workspace.organization is not None else None
    if document.organization_id != workspace_organization_id:
        # A referenced MSP document is readable from a client workspace, but
        # only its owning workspace may freeze dependency projections.
        raise Http404
    require_permission(request.user, PermissionKey.DOCUMENTS_PUBLISH, organization=document.organization)
    serializer = DocumentPublicationWriteSerializer(
        data=request.data,
        context={"organization_scoped": workspace.organization is not None},
    )
    serializer.is_valid(raise_exception=True)
    try:
        publication = publish_document(
            workspace=workspace,
            document=document,
            actor_id=request.user.pk,
            reason=serializer.validated_data["reason"],
            audience=serializer.validated_data["audience"],
            retention=serializer.validated_data["retention"],
            retention_review_on=serializer.validated_data.get("retention_review_on"),
            supersedes_entity_id=serializer.validated_data.get("supersedes_id"),
        )
    except PublicationConflict as conflict:
        return Response({"code": "publication_conflict", "detail": str(conflict)}, status=409)
    return Response(DocumentPublicationDetailSerializer(publication).data, status=201)


def _control_publication(
    workspace: ResolvedWorkspace,
    document_entity_id: UUID,
    publication_entity_id: UUID,
    request: Request,
    *,
    action: str,
) -> Response:
    require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization)
    publication = _publication(workspace, document_entity_id, publication_entity_id)
    serializer = DocumentPublicationControlWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        if action == "approve":
            approve_publication(
                publication=publication,
                actor_id=request.user.pk,
                reason=serializer.validated_data["reason"],
            )
        else:
            withdraw_publication(
                publication=publication,
                actor_id=request.user.pk,
                reason=serializer.validated_data["reason"],
            )
    except PublicationConflict as conflict:
        return Response({"code": "publication_conflict", "detail": str(conflict)}, status=409)
    refreshed = _publication(workspace, document_entity_id, publication_entity_id)
    return Response(DocumentPublicationDetailSerializer(refreshed).data)


def _publication_artifact(
    workspace: ResolvedWorkspace,
    document_entity_id: UUID,
    publication_entity_id: UUID,
    artifact_entity_id: UUID,
) -> DocumentPublicationArtifact:
    publication = _publication(workspace, document_entity_id, publication_entity_id)
    return get_object_or_404(
        DocumentPublicationArtifact.objects.filter(publication=publication).select_related("entity"),
        entity_id=artifact_entity_id,
    )


def _publication_artifact_download(
    workspace: ResolvedWorkspace,
    document_entity_id: UUID,
    publication_entity_id: UUID,
    artifact_entity_id: UUID,
) -> HttpResponse:
    artifact = _publication_artifact(workspace, document_entity_id, publication_entity_id, artifact_entity_id)
    try:
        content = read_publication_artifact(artifact)
    except PublicationConflict as conflict:
        return HttpResponse(str(conflict), status=409, content_type="text/plain; charset=utf-8")
    response = HttpResponse(content, content_type=artifact.media_type)
    content_disposition = content_disposition_header(True, artifact.original_filename)
    if content_disposition is not None:
        response["Content-Disposition"] = content_disposition
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _retrieve_publication(
    workspace: ResolvedWorkspace, document_entity_id: UUID, publication_entity_id: UUID
) -> Response:
    publication = _publication(workspace, document_entity_id, publication_entity_id)
    return Response(DocumentPublicationDetailSerializer(publication).data)


def _publication_markdown(
    workspace: ResolvedWorkspace, document_entity_id: UUID, publication_entity_id: UUID
) -> HttpResponse:
    publication = _publication(workspace, document_entity_id, publication_entity_id)
    filename = f"{slugify(publication.title) or 'publication'}-static.md"
    response = HttpResponse(publication.canonical_markdown.encode("utf-8"), content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _publication_manifest(
    workspace: ResolvedWorkspace, document_entity_id: UUID, publication_entity_id: UUID
) -> HttpResponse:
    publication = _publication(workspace, document_entity_id, publication_entity_id)
    filename = f"{slugify(publication.title) or 'publication'}-manifest.json"
    response = HttpResponse(canonical_json(publication.manifest) + b"\n", content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _revision_list(request: Request, workspace: ResolvedWorkspace, document_entity_id: UUID) -> Response:
    document = _document(workspace, document_entity_id)
    query = BlockRevisionListQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    page = query.validated_data["page"]
    page_size = query.validated_data["page_size"]
    records_query = revisions_for_document(document)
    count = records_query.count()
    offset = (page - 1) * page_size
    records = list(records_query[offset : offset + page_size])
    current_id = document.active_placements[0].block.current_revision_id
    context = {"current_revision_id": current_id}
    return Response(
        BlockRevisionResultSerializer(
            {
                "results": records,
                "count": count,
                "page": page,
                "page_size": page_size,
                "has_more": offset + len(records) < count,
            },
            context=context,
        ).data
    )


def _revision_detail(workspace: ResolvedWorkspace, document_entity_id: UUID, revision_id: UUID) -> Response:
    document = _document(workspace, document_entity_id)
    revision = get_object_or_404(revisions_for_document(document), id=revision_id)
    current_id = document.active_placements[0].block.current_revision_id
    return Response(
        BlockRevisionDetailSerializer(
            revision,
            context={
                "current_revision_id": current_id,
                "diff_from_parent": revision_diff(revision.parent, revision),
            },
        ).data
    )


def _archive(workspace: ResolvedWorkspace, document_entity_id: UUID, request) -> Response:  # type: ignore[no-untyped-def]
    document = _document(workspace, document_entity_id)
    _mutate_workspace(request, workspace, document)
    try:
        archive_document(document=document, actor_id=request.user.pk)
    except PlacementConflict as conflict:
        return _placement_conflict(conflict)
    return Response(status=204)


def _placement_conflict(conflict: PlacementConflict) -> Response:
    return Response({"code": "placement_conflict", "detail": str(conflict)}, status=409)


def _revision_conflict_response(conflict: RevisionConflict) -> Response:
    current = conflict.current_revision
    return Response(
        {
            "code": "revision_conflict",
            "detail": str(conflict),
            "submitted_base_revision_id": conflict.submitted_base_revision_id,
            "current_revision": BlockRevisionDetailSerializer(
                current,
                context={
                    "current_revision_id": current.id,
                    "diff_from_parent": revision_diff(current.parent, current),
                },
            ).data,
            "diff": revision_diff(conflict.base_revision, current),
        },
        status=409,
    )


def _document_placement(workspace: ResolvedWorkspace, document_entity_id: UUID, placement_id: UUID):  # type: ignore[no-untyped-def]
    document = _document(workspace, document_entity_id)
    placement = get_object_or_404(
        document.placements.select_related(
            "document",
            "document__entity",
            "document__organization",
            "document__organization__entity",
            "block",
            "block__entity",
            "block__organization",
            "block__organization__entity",
            "block__current_revision",
            "pinned_revision",
        ),
        id=placement_id,
    )
    return document, placement


def _reuse_impact(workspace: ResolvedWorkspace, document_entity_id: UUID, placement_id: UUID) -> Response:
    _document_record, placement = _document_placement(workspace, document_entity_id, placement_id)
    impact = reuse_impact_for_placement(context=workspace.member, placement=placement)
    return Response(ReuseImpactSerializer(impact).data)


def _update_shared_placement(
    workspace: ResolvedWorkspace, document_entity_id: UUID, placement_id: UUID, request: Request
) -> Response:
    _document_record, placement = _document_placement(workspace, document_entity_id, placement_id)
    require_permission(request.user, PermissionKey.DOCUMENTS_EDIT, organization=placement.block.organization)
    serializer = SharedBlockUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        update_shared_block(placement=placement, actor_id=request.user.pk, **serializer.validated_data)
    except RevisionConflict as conflict:
        return _revision_conflict_response(conflict)
    return _retrieve(workspace, document_entity_id)


def _detach_placement(
    workspace: ResolvedWorkspace, document_entity_id: UUID, placement_id: UUID, request: Request
) -> Response:
    document, placement = _document_placement(workspace, document_entity_id, placement_id)
    _mutate_workspace(request, workspace, document)
    try:
        detach_document_placement(placement=placement, actor_id=request.user.pk)
    except PlacementConflict as conflict:
        return _placement_conflict(conflict)
    return _retrieve(workspace, document_entity_id)


def _mention_search(workspace: ResolvedWorkspace, request: Request) -> Response:
    query = EntityMentionSearchQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    values = query.validated_data
    results, count, has_more = search_entities(
        workspace=workspace,
        query=values["q"],
        entity_type=values["entity_type"],
        page=values["page"],
        page_size=min(values["page_size"], 20),
    )
    return Response(
        EntityMentionResultSerializer(
            {
                "results": results,
                "page": values["page"],
                "page_size": min(values["page_size"], 20),
                "count": count,
                "has_more": has_more,
            }
        ).data
    )


def _add_placement(workspace: ResolvedWorkspace, document_entity_id: UUID, request: Request) -> Response:
    document = _document(workspace, document_entity_id)
    _mutate_workspace(request, workspace, document)
    serializer = DocumentPlacementWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    source_document = _document(workspace, serializer.validated_data["source_document_id"])
    try:
        add_document_placement(
            document=document,
            source_document=source_document,
            actor_id=request.user.pk,
            resolution_mode=serializer.validated_data["resolution_mode"],
            pinned_revision_id=serializer.validated_data.get("pinned_revision_id"),
            parent_id=serializer.validated_data.get("parent_id"),
        )
    except PlacementConflict as conflict:
        return _placement_conflict(conflict)
    return _retrieve(workspace, document_entity_id)


def _update_placement(
    workspace: ResolvedWorkspace, document_entity_id: UUID, placement_id: UUID, request: Request
) -> Response:
    document = _document(workspace, document_entity_id)
    _mutate_workspace(request, workspace, document)
    placement = get_object_or_404(document.placements, id=placement_id)
    serializer = DocumentPlacementUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        update_document_placement(
            placement=placement,
            actor_id=request.user.pk,
            resolution_mode=serializer.validated_data["resolution_mode"],
            pinned_revision_id=serializer.validated_data.get("pinned_revision_id"),
        )
    except PlacementConflict as conflict:
        return _placement_conflict(conflict)
    return _retrieve(workspace, document_entity_id)


def _remove_placement(
    workspace: ResolvedWorkspace, document_entity_id: UUID, placement_id: UUID, request: Request
) -> Response:
    document = _document(workspace, document_entity_id)
    _mutate_workspace(request, workspace, document)
    placement = get_object_or_404(document.placements, id=placement_id)
    try:
        remove_document_placement(placement=placement, actor_id=request.user.pk)
    except PlacementConflict as conflict:
        return _placement_conflict(conflict)
    return _retrieve(workspace, document_entity_id)


class MSPDocumentListCreateView(APIView):
    @extend_schema(operation_id="documents_msp_list", responses={200: DocumentResultSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        return _list(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), request)

    @extend_schema(
        operation_id="documents_msp_create",
        request=DocumentCreateSerializer,
        responses={201: DocumentSerializer},
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        return _create(_msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), request)


class MSPDocumentTemplateInstantiateView(APIView):
    @extend_schema(
        operation_id="document_templates_msp_instantiate",
        request=DocumentTemplateInstantiateSerializer,
        responses={201: DocumentSerializer, 409: OpenApiResponse(description="Template dependency conflict")},
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        return _instantiate_template(_msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), request)


class MSPMarkdownImportView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        operation_id="documents_msp_import", request=MarkdownImportSerializer, responses={201: DocumentSerializer}
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        return _import_markdown(_msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), request)


class MSPDocumentDetailView(APIView):
    @extend_schema(operation_id="documents_msp_retrieve", responses={200: DocumentSerializer})
    def get(self, request, document_entity_id):  # type: ignore[no-untyped-def]
        return _retrieve(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id)

    @extend_schema(
        operation_id="documents_msp_update",
        request=DocumentUpdateSerializer,
        responses={200: DocumentSerializer, 409: RevisionConflictSerializer},
    )
    def put(self, request, document_entity_id):  # type: ignore[no-untyped-def]
        return _update(_msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), document_entity_id, request)

    @extend_schema(
        operation_id="documents_msp_archive",
        request=None,
        responses={204: OpenApiResponse(), 409: OpenApiResponse(description="Placement dependency conflict")},
    )
    def delete(self, request, document_entity_id):  # type: ignore[no-untyped-def]
        return _archive(_msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), document_entity_id, request)


class MSPDocumentExportView(APIView):
    @extend_schema(operation_id="documents_msp_export", responses={(200, "text/markdown"): bytes})
    def get(self, request, document_entity_id):  # type: ignore[no-untyped-def]
        return _export_markdown(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id)


class MSPDocumentAttachmentListCreateView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        operation_id="document_attachments_msp_create",
        request=DocumentAttachmentWriteSerializer,
        responses={201: DocumentAttachmentSerializer},
    )
    def post(self, request, document_entity_id):  # type: ignore[no-untyped-def]
        return _upload_attachment(_msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), document_entity_id, request)


class MSPDocumentAttachmentDetailView(APIView):
    @extend_schema(operation_id="document_attachments_msp_archive", request=None, responses={204: OpenApiResponse()})
    def delete(self, request, document_entity_id, attachment_entity_id):  # type: ignore[no-untyped-def]
        return _archive_attachment(
            _msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), document_entity_id, attachment_entity_id, request
        )


class MSPDocumentAttachmentDownloadView(APIView):
    @extend_schema(
        operation_id="document_attachments_msp_download", responses={(200, "application/octet-stream"): bytes}
    )
    def get(self, request, document_entity_id, attachment_entity_id):  # type: ignore[no-untyped-def]
        return _download_attachment(
            _msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id, attachment_entity_id
        )


class MSPDocumentPublicationListCreateView(APIView):
    @extend_schema(operation_id="document_publications_msp_list", responses={200: DocumentPublicationResultSerializer})
    def get(self, request, document_entity_id):  # type: ignore[no-untyped-def]
        return _list_publications(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id)

    @extend_schema(
        operation_id="document_publications_msp_create",
        request=DocumentPublicationWriteSerializer,
        responses={201: DocumentPublicationDetailSerializer, 409: OpenApiResponse(description="Dependency conflict")},
    )
    def post(self, request, document_entity_id):  # type: ignore[no-untyped-def]
        return _publish(_msp_workspace(request, PermissionKey.DOCUMENTS_PUBLISH), document_entity_id, request)


class MSPDocumentPublicationDetailView(APIView):
    @extend_schema(
        operation_id="document_publications_msp_retrieve",
        responses={200: DocumentPublicationDetailSerializer},
    )
    def get(self, request, document_entity_id, publication_entity_id):  # type: ignore[no-untyped-def]
        return _retrieve_publication(
            _msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id, publication_entity_id
        )


class MSPDocumentPublicationApproveView(APIView):
    @extend_schema(
        operation_id="document_publications_msp_approve",
        request=DocumentPublicationControlWriteSerializer,
        responses={200: DocumentPublicationDetailSerializer, 409: OpenApiResponse(description="State conflict")},
    )
    def post(self, request, document_entity_id, publication_entity_id):  # type: ignore[no-untyped-def]
        return _control_publication(
            _msp_workspace(request, PermissionKey.DOCUMENTS_APPROVE),
            document_entity_id,
            publication_entity_id,
            request,
            action="approve",
        )


class MSPDocumentPublicationWithdrawView(APIView):
    @extend_schema(
        operation_id="document_publications_msp_withdraw",
        request=DocumentPublicationControlWriteSerializer,
        responses={200: DocumentPublicationDetailSerializer, 409: OpenApiResponse(description="State conflict")},
    )
    def post(self, request, document_entity_id, publication_entity_id):  # type: ignore[no-untyped-def]
        return _control_publication(
            _msp_workspace(request, PermissionKey.DOCUMENTS_WITHDRAW),
            document_entity_id,
            publication_entity_id,
            request,
            action="withdraw",
        )


class MSPDocumentPublicationMarkdownView(APIView):
    @extend_schema(operation_id="document_publications_msp_markdown", responses={(200, "text/markdown"): bytes})
    def get(self, request, document_entity_id, publication_entity_id):  # type: ignore[no-untyped-def]
        return _publication_markdown(
            _msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id, publication_entity_id
        )


class MSPDocumentPublicationManifestView(APIView):
    @extend_schema(operation_id="document_publications_msp_manifest", responses={(200, "application/json"): bytes})
    def get(self, request, document_entity_id, publication_entity_id):  # type: ignore[no-untyped-def]
        return _publication_manifest(
            _msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id, publication_entity_id
        )


class MSPDocumentPublicationArtifactDownloadView(APIView):
    @extend_schema(
        operation_id="document_publication_artifacts_msp_download",
        responses={(200, "application/octet-stream"): bytes},
    )
    def get(self, request, document_entity_id, publication_entity_id, artifact_entity_id):  # type: ignore[no-untyped-def]
        return _publication_artifact_download(
            _msp_workspace(request, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
            publication_entity_id,
            artifact_entity_id,
        )


class MSPDocumentPlacementListCreateView(APIView):
    @extend_schema(
        operation_id="document_placements_msp_create",
        request=DocumentPlacementWriteSerializer,
        responses={200: DocumentSerializer, 409: OpenApiResponse(description="Placement conflict")},
    )
    def post(self, request, document_entity_id):  # type: ignore[no-untyped-def]
        return _add_placement(_msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), document_entity_id, request)


class MSPDocumentPlacementDetailView(APIView):
    @extend_schema(
        operation_id="document_placements_msp_update",
        request=DocumentPlacementUpdateSerializer,
        responses={200: DocumentSerializer, 409: OpenApiResponse(description="Placement conflict")},
    )
    def patch(self, request, document_entity_id, placement_id):  # type: ignore[no-untyped-def]
        return _update_placement(
            _msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), document_entity_id, placement_id, request
        )

    @extend_schema(
        operation_id="document_placements_msp_destroy",
        request=None,
        responses={200: DocumentSerializer, 409: OpenApiResponse(description="Placement conflict")},
    )
    def delete(self, request, document_entity_id, placement_id):  # type: ignore[no-untyped-def]
        return _remove_placement(
            _msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), document_entity_id, placement_id, request
        )


class MSPDocumentPlacementReuseView(APIView):
    @extend_schema(operation_id="document_placement_reuse_msp_retrieve", responses={200: ReuseImpactSerializer})
    def get(self, request, document_entity_id, placement_id):  # type: ignore[no-untyped-def]
        return _reuse_impact(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id, placement_id)

    @extend_schema(
        operation_id="document_placement_shared_block_msp_update",
        request=SharedBlockUpdateSerializer,
        responses={200: DocumentSerializer, 409: RevisionConflictSerializer},
    )
    def put(self, request, document_entity_id, placement_id):  # type: ignore[no-untyped-def]
        return _update_shared_placement(
            _msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id, placement_id, request
        )


class MSPDocumentPlacementDetachView(APIView):
    @extend_schema(
        operation_id="document_placement_msp_detach",
        request=None,
        responses={200: DocumentSerializer, 409: OpenApiResponse(description="Placement conflict")},
    )
    def post(self, request, document_entity_id, placement_id):  # type: ignore[no-untyped-def]
        return _detach_placement(
            _msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), document_entity_id, placement_id, request
        )


class MSPDocumentMentionSearchView(APIView):
    @extend_schema(
        operation_id="document_mentions_msp_search",
        parameters=[EntityMentionSearchQuerySerializer],
        responses={200: EntityMentionResultSerializer},
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        return _mention_search(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), request)


class OrganizationDocumentListCreateView(APIView):
    @extend_schema(operation_id="documents_organization_list", responses={200: DocumentResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _list(_organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW), request)

    @extend_schema(
        operation_id="documents_organization_create",
        request=DocumentCreateSerializer,
        responses={201: DocumentSerializer},
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _create(_organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT), request)


class OrganizationDocumentTemplateInstantiateView(APIView):
    @extend_schema(
        operation_id="document_templates_organization_instantiate",
        request=DocumentTemplateInstantiateSerializer,
        responses={201: DocumentSerializer, 409: OpenApiResponse(description="Template dependency conflict")},
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _instantiate_template(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT), request
        )


class OrganizationMarkdownImportView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        operation_id="documents_organization_import",
        request=MarkdownImportSerializer,
        responses={201: DocumentSerializer},
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _import_markdown(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT), request
        )


class OrganizationDocumentDetailView(APIView):
    @extend_schema(operation_id="documents_organization_retrieve", responses={200: DocumentSerializer})
    def get(self, request, organization_entity_id, document_entity_id):  # type: ignore[no-untyped-def]
        return _retrieve(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW), document_entity_id
        )

    @extend_schema(
        operation_id="documents_organization_update",
        request=DocumentUpdateSerializer,
        responses={200: DocumentSerializer, 409: RevisionConflictSerializer},
    )
    def put(self, request, organization_entity_id, document_entity_id):  # type: ignore[no-untyped-def]
        return _update(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            document_entity_id,
            request,
        )

    @extend_schema(
        operation_id="documents_organization_archive",
        request=None,
        responses={204: OpenApiResponse(), 409: OpenApiResponse(description="Placement dependency conflict")},
    )
    def delete(self, request, organization_entity_id, document_entity_id):  # type: ignore[no-untyped-def]
        return _archive(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            document_entity_id,
            request,
        )


class OrganizationDocumentExportView(APIView):
    @extend_schema(operation_id="documents_organization_export", responses={(200, "text/markdown"): bytes})
    def get(self, request, organization_entity_id, document_entity_id):  # type: ignore[no-untyped-def]
        return _export_markdown(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
        )


class OrganizationDocumentAttachmentListCreateView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        operation_id="document_attachments_organization_create",
        request=DocumentAttachmentWriteSerializer,
        responses={201: DocumentAttachmentSerializer},
    )
    def post(self, request, organization_entity_id, document_entity_id):  # type: ignore[no-untyped-def]
        return _upload_attachment(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            document_entity_id,
            request,
        )


class OrganizationDocumentAttachmentDetailView(APIView):
    @extend_schema(
        operation_id="document_attachments_organization_archive", request=None, responses={204: OpenApiResponse()}
    )
    def delete(self, request, organization_entity_id, document_entity_id, attachment_entity_id):  # type: ignore[no-untyped-def]
        return _archive_attachment(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            document_entity_id,
            attachment_entity_id,
            request,
        )


class OrganizationDocumentAttachmentDownloadView(APIView):
    @extend_schema(
        operation_id="document_attachments_organization_download", responses={(200, "application/octet-stream"): bytes}
    )
    def get(self, request, organization_entity_id, document_entity_id, attachment_entity_id):  # type: ignore[no-untyped-def]
        return _download_attachment(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
            attachment_entity_id,
        )


class OrganizationDocumentPublicationListCreateView(APIView):
    @extend_schema(
        operation_id="document_publications_organization_list",
        responses={200: DocumentPublicationResultSerializer},
    )
    def get(self, request, organization_entity_id, document_entity_id):  # type: ignore[no-untyped-def]
        return _list_publications(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
        )

    @extend_schema(
        operation_id="document_publications_organization_create",
        request=DocumentPublicationWriteSerializer,
        responses={201: DocumentPublicationDetailSerializer, 409: OpenApiResponse(description="Dependency conflict")},
    )
    def post(self, request, organization_entity_id, document_entity_id):  # type: ignore[no-untyped-def]
        return _publish(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_PUBLISH),
            document_entity_id,
            request,
        )


class OrganizationDocumentPublicationDetailView(APIView):
    @extend_schema(
        operation_id="document_publications_organization_retrieve",
        responses={200: DocumentPublicationDetailSerializer},
    )
    def get(self, request, organization_entity_id, document_entity_id, publication_entity_id):  # type: ignore[no-untyped-def]
        return _retrieve_publication(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
            publication_entity_id,
        )


class OrganizationDocumentPublicationApproveView(APIView):
    @extend_schema(
        operation_id="document_publications_organization_approve",
        request=DocumentPublicationControlWriteSerializer,
        responses={200: DocumentPublicationDetailSerializer, 409: OpenApiResponse(description="State conflict")},
    )
    def post(self, request, organization_entity_id, document_entity_id, publication_entity_id):  # type: ignore[no-untyped-def]
        return _control_publication(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            document_entity_id,
            publication_entity_id,
            request,
            action="approve",
        )


class OrganizationDocumentPublicationWithdrawView(APIView):
    @extend_schema(
        operation_id="document_publications_organization_withdraw",
        request=DocumentPublicationControlWriteSerializer,
        responses={200: DocumentPublicationDetailSerializer, 409: OpenApiResponse(description="State conflict")},
    )
    def post(self, request, organization_entity_id, document_entity_id, publication_entity_id):  # type: ignore[no-untyped-def]
        return _control_publication(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_WITHDRAW),
            document_entity_id,
            publication_entity_id,
            request,
            action="withdraw",
        )


class OrganizationDocumentPublicationMarkdownView(APIView):
    @extend_schema(
        operation_id="document_publications_organization_markdown", responses={(200, "text/markdown"): bytes}
    )
    def get(self, request, organization_entity_id, document_entity_id, publication_entity_id):  # type: ignore[no-untyped-def]
        return _publication_markdown(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
            publication_entity_id,
        )


class OrganizationDocumentPublicationManifestView(APIView):
    @extend_schema(
        operation_id="document_publications_organization_manifest", responses={(200, "application/json"): bytes}
    )
    def get(self, request, organization_entity_id, document_entity_id, publication_entity_id):  # type: ignore[no-untyped-def]
        return _publication_manifest(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
            publication_entity_id,
        )


class OrganizationDocumentPublicationArtifactDownloadView(APIView):
    @extend_schema(
        operation_id="document_publication_artifacts_organization_download",
        responses={(200, "application/octet-stream"): bytes},
    )
    def get(
        self,
        request: Request,
        organization_entity_id: UUID,
        document_entity_id: UUID,
        publication_entity_id: UUID,
        artifact_entity_id: UUID,
    ) -> HttpResponse:
        return _publication_artifact_download(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
            publication_entity_id,
            artifact_entity_id,
        )


class OrganizationDocumentPlacementListCreateView(APIView):
    @extend_schema(
        operation_id="document_placements_organization_create",
        request=DocumentPlacementWriteSerializer,
        responses={200: DocumentSerializer, 409: OpenApiResponse(description="Placement conflict")},
    )
    def post(self, request, organization_entity_id, document_entity_id):  # type: ignore[no-untyped-def]
        return _add_placement(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            document_entity_id,
            request,
        )


class OrganizationDocumentPlacementDetailView(APIView):
    @extend_schema(
        operation_id="document_placements_organization_update",
        request=DocumentPlacementUpdateSerializer,
        responses={200: DocumentSerializer, 409: OpenApiResponse(description="Placement conflict")},
    )
    def patch(self, request, organization_entity_id, document_entity_id, placement_id):  # type: ignore[no-untyped-def]
        return _update_placement(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            document_entity_id,
            placement_id,
            request,
        )

    @extend_schema(
        operation_id="document_placements_organization_destroy",
        request=None,
        responses={200: DocumentSerializer, 409: OpenApiResponse(description="Placement conflict")},
    )
    def delete(self, request, organization_entity_id, document_entity_id, placement_id):  # type: ignore[no-untyped-def]
        return _remove_placement(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            document_entity_id,
            placement_id,
            request,
        )


class OrganizationDocumentPlacementReuseView(APIView):
    @extend_schema(
        operation_id="document_placement_reuse_organization_retrieve",
        responses={200: ReuseImpactSerializer},
    )
    def get(self, request, organization_entity_id, document_entity_id, placement_id):  # type: ignore[no-untyped-def]
        return _reuse_impact(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
            placement_id,
        )

    @extend_schema(
        operation_id="document_placement_shared_block_organization_update",
        request=SharedBlockUpdateSerializer,
        responses={200: DocumentSerializer, 409: RevisionConflictSerializer},
    )
    def put(self, request, organization_entity_id, document_entity_id, placement_id):  # type: ignore[no-untyped-def]
        return _update_shared_placement(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
            placement_id,
            request,
        )


class OrganizationDocumentPlacementDetachView(APIView):
    @extend_schema(
        operation_id="document_placement_organization_detach",
        request=None,
        responses={200: DocumentSerializer, 409: OpenApiResponse(description="Placement conflict")},
    )
    def post(self, request, organization_entity_id, document_entity_id, placement_id):  # type: ignore[no-untyped-def]
        return _detach_placement(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            document_entity_id,
            placement_id,
            request,
        )


class OrganizationDocumentMentionSearchView(APIView):
    @extend_schema(
        operation_id="document_mentions_organization_search",
        parameters=[EntityMentionSearchQuerySerializer],
        responses={200: EntityMentionResultSerializer},
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _mention_search(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW), request
        )


class MSPDocumentRevisionListView(APIView):
    @extend_schema(
        operation_id="document_revisions_msp_list",
        parameters=[BlockRevisionListQuerySerializer],
        responses={200: BlockRevisionResultSerializer},
    )
    def get(self, request, document_entity_id):  # type: ignore[no-untyped-def]
        return _revision_list(request, _msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id)


class MSPDocumentRevisionDetailView(APIView):
    @extend_schema(operation_id="document_revisions_msp_retrieve", responses={200: BlockRevisionDetailSerializer})
    def get(self, request, document_entity_id, revision_id):  # type: ignore[no-untyped-def]
        return _revision_detail(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id, revision_id)


class OrganizationDocumentRevisionListView(APIView):
    @extend_schema(
        operation_id="document_revisions_organization_list",
        parameters=[BlockRevisionListQuerySerializer],
        responses={200: BlockRevisionResultSerializer},
    )
    def get(self, request, organization_entity_id, document_entity_id):  # type: ignore[no-untyped-def]
        return _revision_list(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
        )


class OrganizationDocumentRevisionDetailView(APIView):
    @extend_schema(
        operation_id="document_revisions_organization_retrieve", responses={200: BlockRevisionDetailSerializer}
    )
    def get(self, request, organization_entity_id, document_entity_id, revision_id):  # type: ignore[no-untyped-def]
        return _revision_detail(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
            revision_id,
        )


class MSPDocumentReferenceListCreateView(APIView):
    @extend_schema(
        operation_id="document_references_list", responses={200: DocumentationReferenceSerializer(many=True)}
    )
    def get(self, request, document_entity_id):  # type: ignore[no-untyped-def]
        workspace = _msp_workspace(request, PermissionKey.DOCUMENTS_VIEW)
        document = _document(workspace, document_entity_id)
        refs = document.listing_references.filter(archived_at__isnull=True).select_related(
            "organization", "organization__entity"
        )
        return Response(DocumentationReferenceSerializer(refs, many=True).data)

    @extend_schema(
        operation_id="document_references_create",
        request=DocumentationReferenceWriteSerializer,
        responses={201: DocumentationReferenceSerializer},
    )
    def post(self, request, document_entity_id):  # type: ignore[no-untyped-def]
        workspace = _msp_workspace(request, PermissionKey.DOCUMENTS_EDIT)
        document = _document(workspace, document_entity_id)
        serializer = DocumentationReferenceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = get_object_or_404(
            workspace.member.tenant.organizations.select_related("entity"),
            entity_id=serializer.validated_data["organization_id"],
            entity__archived_at__isnull=True,
        )
        require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=organization)
        reference = add_listing_reference(document=document, organization=organization, actor_id=request.user.pk)
        return Response(DocumentationReferenceSerializer(reference).data, status=201)


class MSPDocumentReferenceDetailView(APIView):
    @extend_schema(
        operation_id="document_references_archive",
        request=None,
        responses={204: OpenApiResponse(), 409: OpenApiResponse(description="Placement dependency conflict")},
    )
    def delete(self, request, document_entity_id, reference_id):  # type: ignore[no-untyped-def]
        workspace = _msp_workspace(request, PermissionKey.DOCUMENTS_EDIT)
        document = _document(workspace, document_entity_id)
        reference = get_object_or_404(
            DocumentationListingReference.objects.filter(tenant=workspace.member.tenant),
            id=reference_id,
            document=document,
            archived_at__isnull=True,
        )
        try:
            remove_listing_reference(reference=reference, actor_id=request.user.pk)
        except PlacementConflict as conflict:
            return _placement_conflict(conflict)
        return Response(status=204)
