"""Declaring key bindings and reporting a document's key state (ADR 0089, `0.8.38`).

A document declares named bindings; content addresses them with
``<tekdocs://key/subject.serial_number>``. Until this module existed, bindings could
only be created directly in the database, so the resolution engine shipped in
`0.8.37` had no way to be used.

Two surfaces live here. Bindings are configuration and are edited with the same
permission that edits document content, because declaring one changes what the
document says. The key report is an authoring aid: it lists every key in the
document with the state it resolves to for the requesting member, so an author can
find a key that resolves to nothing without reading rendered output. It discloses
nothing a rendered marker would not already show the same reader.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, entity_visible_to_audience

from .document_key_fields import ADDRESSABLE_ENTITY_TYPES, addressable_fields
from .document_key_resolution import ResolutionState, audience_for, resolve_markdown_keys
from .document_keys import BINDING_NAME_PATTERN
from .document_views import _document, _msp_workspace, _organization_workspace
from .documents import documents_for_scope, resolve_document
from .models import AuditEvent, DocumentKeyBinding, Entity, workspace_for_owner
from .workspaces import ResolvedWorkspace

#: Bound on related documents reported per record, so one heavily reused asset
#: cannot turn opening the keys panel into an unbounded read.
MAXIMUM_RELATED_DOCUMENTS = 50

#: Bounded browser page, matching the collection convention elsewhere.
BROWSER_PAGE_SIZE = 100


#: Rejecting a name is common — an author types a capitalised word before knowing the
#: grammar — so the refusal states the rule rather than reporting a pattern mismatch.
BINDING_NAME_HELP = (
    "A binding name uses lowercase letters, digits and underscores, and starts with a "
    "letter. For example: subject, primary_switch."
)


class KeyBindingWriteSerializer(serializers.Serializer):
    name = serializers.RegexField(BINDING_NAME_PATTERN, max_length=40, error_messages={"invalid": BINDING_NAME_HELP})
    target_entity_id = serializers.UUIDField()


class BoundDocumentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()


class KeyBindingResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    target_entity_id = serializers.UUIDField(source="target_entity.id")
    target_display_name = serializers.CharField(source="target_entity.display_name")
    target_entity_type = serializers.CharField(source="target_entity.entity_type")
    addressable_fields = serializers.SerializerMethodField()
    also_bound_by = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_addressable_fields(self, binding: DocumentKeyBinding) -> list[str]:
        """Every key path this binding can resolve, so an author need not guess."""
        return addressable_fields(binding.target_entity.entity_type)

    @extend_schema_field(BoundDocumentSerializer(many=True))
    def get_also_bound_by(self, binding: DocumentKeyBinding) -> list[dict[str, str]]:
        """Other documents that resolve values from the same record.

        This is where-used, shown where the decision is made. Once documentation
        derives from inventory, editing one asset silently rewrites every document
        that quotes it, so the blast radius has to be visible while binding rather
        than discovered afterwards.
        """
        usage: Mapping[UUID, list[dict[str, str]]] = self.context.get("also_bound_by", {})
        return usage.get(binding.target_entity_id, [])


class KeyBindingListSerializer(serializers.Serializer):
    results = KeyBindingResultSerializer(many=True)
    count = serializers.IntegerField()
    #: The record kinds a binding may target. The authoring surface reads this rather
    #: than carrying its own copy of the registry, so adding a resolvable record kind
    #: stays a single change on the server.
    addressable_entity_types = serializers.ListField(child=serializers.CharField())


class DocumentKeySerializer(serializers.Serializer):
    expression = serializers.CharField()
    state = serializers.CharField()
    label = serializers.CharField()
    reason = serializers.CharField(allow_null=True)


class DocumentKeyReportSerializer(serializers.Serializer):
    results = DocumentKeySerializer(many=True)
    count = serializers.IntegerField()
    unresolved_count = serializers.IntegerField()


def _live_bindings(workspace: ResolvedWorkspace, document_entity_id: UUID):  # type: ignore[no-untyped-def]
    document = _document(workspace, document_entity_id)
    return document, document.key_bindings.filter(archived_at__isnull=True).select_related("target_entity")


def _also_bound_by(bindings: Sequence[DocumentKeyBinding]) -> dict[UUID, list[dict[str, str]]]:
    """Documents other than the binding's own that target the same records.

    One query for the whole page rather than one per binding, so opening the panel
    costs the same whether a document declares one binding or twenty.
    """
    target_ids = {binding.target_entity_id for binding in bindings}
    if not target_ids:
        return {}
    own_document_ids = {binding.document_id for binding in bindings}
    usage: dict[UUID, list[dict[str, str]]] = {target_id: [] for target_id in target_ids}
    others = (
        DocumentKeyBinding.objects.filter(target_entity_id__in=target_ids, archived_at__isnull=True)
        .exclude(document_id__in=own_document_ids)
        .select_related("document__entity")
        .order_by("document__entity__display_name", "document_id")[:MAXIMUM_RELATED_DOCUMENTS]
    )
    seen: set[tuple[UUID, UUID]] = set()
    for other in others:
        pair = (other.target_entity_id, other.document_id)
        if pair in seen:
            continue
        seen.add(pair)
        usage[other.target_entity_id].append(
            {"id": str(other.document.entity_id), "title": other.document.entity.display_name}
        )
    return usage


def _bindings(workspace: ResolvedWorkspace, document_entity_id: UUID, request: Request) -> Response:
    document, records = _live_bindings(workspace, document_entity_id)
    if request.method != "POST":
        page = list(records)
        context = {"also_bound_by": _also_bound_by(page)}
        return Response(
            {
                "results": KeyBindingResultSerializer(page, many=True, context=context).data,
                "count": len(page),
                "addressable_entity_types": sorted(ADDRESSABLE_ENTITY_TYPES),
            }
        )

    serializer = KeyBindingWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    target = get_object_or_404(
        Entity.objects.select_related("organization"),
        id=serializer.validated_data["target_entity_id"],
        tenant=workspace.member.tenant,
        archived_at__isnull=True,
    )
    # The same visibility gate resolution will apply. Checking it here means a
    # binding cannot be declared against a record the declaring member could not
    # read directly, rather than being declared and then always withheld.
    if not entity_visible_to_audience(
        workspace.member, target, audience=audience_for(workspace.member), organization=workspace.organization
    ):
        return Response({"code": "target_unavailable", "detail": "The selected record is not available."}, status=404)
    if target.entity_type not in ADDRESSABLE_ENTITY_TYPES:
        return Response(
            {
                "code": "target_not_addressable",
                "detail": (
                    "Keys cannot yet read fields from this kind of record. Addressable kinds: "
                    f"{', '.join(sorted(ADDRESSABLE_ENTITY_TYPES))}."
                ),
            },
            status=400,
        )
    if records.filter(name=serializer.validated_data["name"]).exists():
        return Response(
            {"code": "binding_exists", "detail": "This document already declares that binding name."},
            status=409,
        )

    with transaction.atomic():
        binding = DocumentKeyBinding.objects.create(
            tenant=document.tenant,
            workspace=workspace_for_owner(tenant=document.tenant, organization=document.organization),
            organization=document.organization,
            document=document,
            name=serializer.validated_data["name"],
            target_entity=target,
            created_by=request.user,
        )
        AuditEvent.objects.create(
            tenant=document.tenant,
            actor_id=request.user.pk,
            action="document.key_binding.declared",
            entity_id=document.entity_id,
            metadata={"name": binding.name},
        )
    return Response(KeyBindingResultSerializer(binding).data, status=201)


def _archive_binding(workspace: ResolvedWorkspace, document_entity_id: UUID, binding_id: UUID, request: Request):  # type: ignore[no-untyped-def]
    _document_record, records = _live_bindings(workspace, document_entity_id)
    binding = get_object_or_404(records, id=binding_id)
    with transaction.atomic():
        binding.archived_at = timezone.now()
        binding.save(update_fields=("archived_at", "updated_at"))
        AuditEvent.objects.create(
            tenant=binding.tenant,
            actor_id=request.user.pk,
            action="document.key_binding.archived",
            entity_id=binding.document.entity_id,
            metadata={"name": binding.name},
        )
    # Keys naming this binding now render an explicit unresolvable marker rather than
    # a stale value, which is why retiring one is safe without editing content.
    return Response(status=204)


def _key_report(workspace: ResolvedWorkspace, document_entity_id: UUID) -> Response:
    document = _document(workspace, document_entity_id)
    markdown = resolve_document(document).markdown
    resolutions = resolve_markdown_keys(
        markdown,
        context=workspace.member,
        document=document,
        audience=audience_for(workspace.member),
        organization=workspace.organization,
    )
    rows: list[dict[str, str | None]] = sorted(
        (
            {
                "expression": resolution.expression,
                "state": resolution.state.value,
                "label": resolution.label,
                "reason": resolution.reason.value if resolution.reason is not None else None,
            }
            for resolution in resolutions.values()
        ),
        key=lambda row: str(row["expression"]),
    )
    unresolved = sum(1 for resolution in resolutions.values() if resolution.state != ResolutionState.RESOLVED)
    return Response({"results": rows, "count": len(rows), "unresolved_count": unresolved})


class MSPDocumentKeyBindingListCreateView(APIView):
    @extend_schema(operation_id="document_key_bindings_msp_list", responses={200: KeyBindingListSerializer})
    def get(self, request: Request, document_entity_id: UUID) -> Response:
        return _bindings(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id, request)

    @extend_schema(
        operation_id="document_key_bindings_msp_create",
        request=KeyBindingWriteSerializer,
        responses={201: KeyBindingResultSerializer, 409: OpenApiResponse(description="Binding name already declared")},
    )
    def post(self, request: Request, document_entity_id: UUID) -> Response:
        return _bindings(_msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), document_entity_id, request)


class MSPDocumentKeyBindingDetailView(APIView):
    @extend_schema(operation_id="document_key_bindings_msp_archive", request=None, responses={204: None})
    def delete(self, request: Request, document_entity_id: UUID, binding_id: UUID) -> Response:
        return _archive_binding(
            _msp_workspace(request, PermissionKey.DOCUMENTS_EDIT), document_entity_id, binding_id, request
        )


class MSPDocumentKeyReportView(APIView):
    @extend_schema(operation_id="document_keys_msp_list", responses={200: DocumentKeyReportSerializer})
    def get(self, request: Request, document_entity_id: UUID) -> Response:
        return _key_report(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), document_entity_id)


class OrganizationDocumentKeyBindingListCreateView(APIView):
    @extend_schema(operation_id="document_key_bindings_organization_list", responses={200: KeyBindingListSerializer})
    def get(self, request: Request, organization_entity_id: UUID, document_entity_id: UUID) -> Response:
        return _bindings(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
            request,
        )

    @extend_schema(
        operation_id="document_key_bindings_organization_create",
        request=KeyBindingWriteSerializer,
        responses={201: KeyBindingResultSerializer, 409: OpenApiResponse(description="Binding name already declared")},
    )
    def post(self, request: Request, organization_entity_id: UUID, document_entity_id: UUID) -> Response:
        return _bindings(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            document_entity_id,
            request,
        )


class OrganizationDocumentKeyBindingDetailView(APIView):
    @extend_schema(operation_id="document_key_bindings_organization_archive", request=None, responses={204: None})
    def delete(
        self, request: Request, organization_entity_id: UUID, document_entity_id: UUID, binding_id: UUID
    ) -> Response:
        return _archive_binding(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT),
            document_entity_id,
            binding_id,
            request,
        )


class OrganizationDocumentKeyReportView(APIView):
    @extend_schema(operation_id="document_keys_organization_list", responses={200: DocumentKeyReportSerializer})
    def get(self, request: Request, organization_entity_id: UUID, document_entity_id: UUID) -> Response:
        return _key_report(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW),
            document_entity_id,
        )


class WorkspaceKeyBindingSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    document_id = serializers.UUIDField(source="document.entity_id")
    document_title = serializers.CharField(source="document.entity.display_name")
    target_entity_id = serializers.UUIDField(source="target_entity.id")
    target_display_name = serializers.CharField(source="target_entity.display_name")
    target_entity_type = serializers.CharField(source="target_entity.entity_type")


class WorkspaceKeyBindingListSerializer(serializers.Serializer):
    results = WorkspaceKeyBindingSerializer(many=True)
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()


def _binding_browser(workspace: ResolvedWorkspace, request: Request) -> Response:
    """Every live binding in this workspace, so a record's dependents are findable.

    Without this, answering "what breaks if I change this asset" means opening every
    document one at a time. The listing is scoped through the same document queryset
    the rest of the surface uses, so it can never widen what a member may see, and it
    is bounded rather than returning a whole workspace at once.
    """
    query = str(request.query_params.get("q", "")).strip()
    records = (
        DocumentKeyBinding.objects.filter(
            document__in=documents_for_scope(workspace.data_scope), archived_at__isnull=True
        )
        .select_related("document__entity", "target_entity")
        .order_by("target_entity__display_name", "document__entity__display_name", "name")
    )
    if query:
        records = records.filter(
            Q(name__icontains=query)
            | Q(target_entity__display_name__icontains=query)
            | Q(document__entity__display_name__icontains=query)
        )
    page = list(records[: BROWSER_PAGE_SIZE + 1])
    has_more = len(page) > BROWSER_PAGE_SIZE
    page = page[:BROWSER_PAGE_SIZE]
    return Response(
        {
            "results": WorkspaceKeyBindingSerializer(page, many=True).data,
            "count": len(page),
            "has_more": has_more,
        }
    )


class MSPKeyBindingBrowserView(APIView):
    @extend_schema(operation_id="key_bindings_msp_browse", responses={200: WorkspaceKeyBindingListSerializer})
    def get(self, request: Request) -> Response:
        return _binding_browser(_msp_workspace(request, PermissionKey.DOCUMENTS_VIEW), request)


class OrganizationKeyBindingBrowserView(APIView):
    @extend_schema(operation_id="key_bindings_organization_browse", responses={200: WorkspaceKeyBindingListSerializer})
    def get(self, request: Request, organization_entity_id: UUID) -> Response:
        return _binding_browser(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW), request
        )
