from uuid import UUID

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

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
    remove_document_placement,
    remove_listing_reference,
    revision_diff,
    revisions_for_document,
    update_document,
    update_document_placement,
    update_shared_block,
)
from .models import DocumentationListingReference
from .relationships import search_entities
from .scoping import DataScope
from .serializers import (
    BlockRevisionDetailSerializer,
    BlockRevisionResultSerializer,
    DocumentationReferenceSerializer,
    DocumentationReferenceWriteSerializer,
    DocumentCreateSerializer,
    DocumentPlacementUpdateSerializer,
    DocumentPlacementWriteSerializer,
    DocumentResultSerializer,
    DocumentSerializer,
    DocumentUpdateSerializer,
    EntityMentionResultSerializer,
    EntityMentionSearchQuerySerializer,
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


def _list(workspace: ResolvedWorkspace) -> Response:
    records = list(documents_for_scope(workspace.data_scope).order_by("entity__display_name", "entity_id")[:500])
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


def _revision_list(workspace: ResolvedWorkspace, document_entity_id: UUID) -> Response:
    document = _document(workspace, document_entity_id)
    records = list(revisions_for_document(document)[:200])
    current_id = document.active_placements[0].block.current_revision_id
    context = {"current_revision_id": current_id}
    return Response(BlockRevisionResultSerializer({"results": records, "count": len(records)}, context=context).data)


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
        return _list(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW))

    @extend_schema(
        operation_id="documents_msp_create",
        request=DocumentCreateSerializer,
        responses={201: DocumentSerializer},
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        return _create(_msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), request)


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
        return _list(_organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW))

    @extend_schema(
        operation_id="documents_organization_create",
        request=DocumentCreateSerializer,
        responses={201: DocumentSerializer},
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _create(_organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT), request)


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
    @extend_schema(operation_id="document_revisions_msp_list", responses={200: BlockRevisionResultSerializer})
    def get(self, request, document_entity_id):  # type: ignore[no-untyped-def]
        return _revision_list(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id)


class MSPDocumentRevisionDetailView(APIView):
    @extend_schema(operation_id="document_revisions_msp_retrieve", responses={200: BlockRevisionDetailSerializer})
    def get(self, request, document_entity_id, revision_id):  # type: ignore[no-untyped-def]
        return _revision_detail(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id, revision_id)


class OrganizationDocumentRevisionListView(APIView):
    @extend_schema(operation_id="document_revisions_organization_list", responses={200: BlockRevisionResultSerializer})
    def get(self, request, organization_entity_id, document_entity_id):  # type: ignore[no-untyped-def]
        return _revision_list(
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
