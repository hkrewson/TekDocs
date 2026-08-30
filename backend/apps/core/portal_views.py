from datetime import date, datetime
from uuid import UUID

from django.core import signing
from django.core.signing import BadSignature
from django.db.models import Exists, OuterRef, Prefetch, Q, QuerySet
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import require_client_portal_member

from .invoice_views import InvoiceSerializer, _invoice_download_response
from .models import (
    DocumentPublication,
    DocumentPublicationArtifact,
    DocumentPublicationControlEvent,
    Entity,
    EntityVisibility,
    Invoice,
    InvoiceState,
    PublicationAudience,
    PublicationControlAction,
)
from .publications import PublicationConflict, read_publication_artifact
from .rls import OrganizationRLSMode, bind_local_rls_scope
from .scoping import DataScope
from .serializers import PortalDocumentDetailSerializer, PortalDocumentResultSerializer

PORTAL_DOCUMENT_PAGE_SIZE = 50
PORTAL_DOCUMENT_SCAN_LIMIT = 100


class PortalInvoiceResultSerializer(serializers.Serializer):
    results = InvoiceSerializer(many=True)
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    next_cursor = serializers.CharField(allow_null=True)


def _decode_portal_invoice_cursor(value: str | None, *, member):  # type: ignore[no-untyped-def]
    if value is None:
        return None
    if len(value) > 1024:
        raise serializers.ValidationError({"cursor": "Cursor is invalid."})
    try:
        payload = signing.loads(value, salt="tekdocs.portal-invoices.v1", max_age=60 * 60 * 24 * 30)
        if not isinstance(payload, dict) or payload.get("scope") != [
            str(member.tenant.id),
            str(member.user.id),
            str(member.organization.id),
        ]:
            raise BadSignature
        return (
            date.fromisoformat(str(payload["invoice_date"])),
            datetime.fromisoformat(str(payload["created_at"])),
            UUID(str(payload["id"])),
        )
    except (BadSignature, KeyError, TypeError, ValueError):
        raise serializers.ValidationError({"cursor": "Cursor is invalid."}) from None


def _portal_invoice_cursor(invoice: Invoice, *, member) -> str:  # type: ignore[no-untyped-def]
    return signing.dumps(
        {
            "scope": [str(member.tenant.id), str(member.user.id), str(member.organization.id)],
            "invoice_date": invoice.invoice_date.isoformat(),
            "created_at": invoice.created_at.isoformat(),
            "id": str(invoice.id),
        },
        salt="tekdocs.portal-invoices.v1",
        compress=True,
    )


def _portal_invoices(request) -> QuerySet[Invoice]:  # type: ignore[no-untyped-def]
    member = require_client_portal_member(request.user)
    organization = member.organization
    if organization is None:
        raise PermissionDenied("Client portal membership is required.")
    bind_local_rls_scope(
        DataScope.organization(member.tenant, organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    )
    return (
        Invoice.objects.filter(
            tenant=member.tenant,
            organization=organization,
            state=InvoiceState.ISSUED,
        )
        .select_related("entity", "organization", "artifact")
        .prefetch_related("lines")
        .order_by("-invoice_date", "-created_at", "id")
    )


def _portal_invoice(request, invoice_entity_id: UUID) -> Invoice:  # type: ignore[no-untyped-def]
    return get_object_or_404(_portal_invoices(request), entity_id=invoice_entity_id)


class ClientPortalInvoiceListView(APIView):
    @extend_schema(
        operation_id="client_portal_invoices_list",
        parameters=[OpenApiParameter("cursor", str, required=False)],
        responses={200: PortalInvoiceResultSerializer},
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        member = require_client_portal_member(request.user)
        after = _decode_portal_invoice_cursor(request.query_params.get("cursor"), member=member)
        queryset = _portal_invoices(request)
        if after is not None:
            invoice_date, created_at, invoice_id = after
            queryset = queryset.filter(
                Q(invoice_date__lt=invoice_date)
                | Q(invoice_date=invoice_date, created_at__lt=created_at)
                | Q(invoice_date=invoice_date, created_at=created_at, id__gt=invoice_id)
            )
        scanned = list(queryset[:51])
        records = scanned[:50]
        has_more = len(scanned) > 50
        response = Response(
            PortalInvoiceResultSerializer(
                {
                    "results": records,
                    "count": len(records),
                    "has_more": has_more,
                    "next_cursor": _portal_invoice_cursor(records[-1], member=member) if has_more else None,
                }
            ).data
        )
        response["Cache-Control"] = "private, no-store"
        return response


class ClientPortalInvoiceDetailView(APIView):
    @extend_schema(operation_id="client_portal_invoices_retrieve", responses={200: InvoiceSerializer})
    def get(self, request, invoice_entity_id):  # type: ignore[no-untyped-def]
        response = Response(InvoiceSerializer(_portal_invoice(request, invoice_entity_id)).data)
        response["Cache-Control"] = "private, no-store"
        return response


class ClientPortalInvoicePDFDownloadView(APIView):
    @extend_schema(
        operation_id="client_portal_invoice_pdf_download",
        responses={(200, "application/pdf"): bytes, 409: OpenApiResponse(description="Integrity conflict")},
    )
    def get(self, request, invoice_entity_id):  # type: ignore[no-untyped-def]
        return _invoice_download_response(_portal_invoice(request, invoice_entity_id), "pdf")


class ClientPortalInvoiceCSVDownloadView(APIView):
    @extend_schema(
        operation_id="client_portal_invoice_csv_download",
        responses={(200, "text/csv"): bytes, 409: OpenApiResponse(description="Export conflict")},
    )
    def get(self, request, invoice_entity_id):  # type: ignore[no-untyped-def]
        return _invoice_download_response(_portal_invoice(request, invoice_entity_id), "csv")


def _portal_publications(request) -> QuerySet[DocumentPublication]:  # type: ignore[no-untyped-def]
    member = require_client_portal_member(request.user)
    organization = member.organization
    if organization is None:
        raise PermissionDenied("Client portal membership is required.")
    bind_local_rls_scope(
        DataScope.organization(member.tenant, organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    )
    approved = DocumentPublicationControlEvent.objects.filter(
        publication_id=OuterRef("pk"),
        action=PublicationControlAction.APPROVED,
    )
    withdrawn = DocumentPublicationControlEvent.objects.filter(
        publication_id=OuterRef("pk"),
        action=PublicationControlAction.WITHDRAWN,
    )
    approved_successor = DocumentPublicationControlEvent.objects.filter(
        publication__supersedes_id=OuterRef("pk"),
        action=PublicationControlAction.APPROVED,
    )
    control_events = DocumentPublicationControlEvent.objects.select_related("actor").order_by("occurred_at", "id")
    return (
        DocumentPublication.objects.filter(
            tenant=member.tenant,
            organization=organization,
            audience=PublicationAudience.CLIENT_VISIBLE,
        )
        .annotate(
            portal_approved=Exists(approved),
            portal_withdrawn=Exists(withdrawn),
            portal_superseded=Exists(approved_successor),
        )
        .filter(portal_approved=True, portal_withdrawn=False, portal_superseded=False)
        .select_related("entity", "document", "document__entity", "published_by", "supersedes__entity")
        .prefetch_related(Prefetch("control_events", queryset=control_events), "artifacts", "artifacts__entity")
    )


def _portal_publication(request, publication_entity_id: UUID) -> DocumentPublication:  # type: ignore[no-untyped-def]
    publication = get_object_or_404(_portal_publications(request), entity_id=publication_entity_id)
    if not _reference_projection_safe(publication):
        raise Http404
    return publication


def _reference_ids(publication: DocumentPublication) -> set[UUID] | None:
    entities = publication.manifest.get("entities", [])
    if not isinstance(entities, list):
        return None
    try:
        return {UUID(str(item["id"])) for item in entities if isinstance(item, dict)}
    except (KeyError, TypeError, ValueError):
        return None


def _reference_projection_safe(publication: DocumentPublication) -> bool:
    reference_ids = _reference_ids(publication)
    if reference_ids is None:
        return False
    if not reference_ids:
        return True
    visible_ids = set(
        Entity.objects.filter(
            id__in=reference_ids,
            tenant=publication.tenant,
            organization=publication.organization,
            visibility=EntityVisibility.CLIENT_VISIBLE,
        ).values_list("id", flat=True)
    )
    return visible_ids == reference_ids


def _safe_portal_publications(records: list[DocumentPublication]) -> list[DocumentPublication]:
    reference_ids_by_publication: dict[UUID, set[UUID]] = {}
    all_reference_ids: set[UUID] = set()
    for publication in records:
        reference_ids = _reference_ids(publication)
        if reference_ids is None:
            continue
        reference_ids_by_publication[publication.id] = reference_ids
        all_reference_ids.update(reference_ids)
    visible_ids = set(
        Entity.objects.filter(
            id__in=all_reference_ids,
            tenant=records[0].tenant,
            organization=records[0].organization,
            visibility=EntityVisibility.CLIENT_VISIBLE,
        ).values_list("id", flat=True)
    ) if records else set()
    return [
        publication
        for publication in records
        if publication.id in reference_ids_by_publication
        and reference_ids_by_publication[publication.id].issubset(visible_ids)
    ]


def _decode_portal_cursor(value: str | None, *, member) -> tuple[str, UUID] | None:  # type: ignore[no-untyped-def]
    if value is None:
        return None
    if len(value) > 1024:
        raise serializers.ValidationError({"cursor": "Cursor is invalid."})
    try:
        payload = signing.loads(value, salt="tekdocs.portal-documents.v1", max_age=60 * 60 * 24 * 30)
        if not isinstance(payload, dict) or payload.get("scope") != [
            str(member.tenant.id),
            str(member.user.id),
            str(member.organization.id),
        ]:
            raise BadSignature
        title = str(payload["title"])
        publication_id = UUID(str(payload["id"]))
        if len(title) > 240:
            raise BadSignature
    except (BadSignature, KeyError, TypeError, ValueError):
        raise serializers.ValidationError({"cursor": "Cursor is invalid."}) from None
    return title, publication_id


def _portal_cursor(publication: DocumentPublication, *, member) -> str:  # type: ignore[no-untyped-def]
    return signing.dumps(
        {
            "scope": [str(member.tenant.id), str(member.user.id), str(member.organization.id)],
            "title": publication.title,
            "id": str(publication.id),
        },
        salt="tekdocs.portal-documents.v1",
        compress=True,
    )


class ClientPortalDocumentListView(APIView):
    @extend_schema(
        operation_id="client_portal_documents_list",
        parameters=[OpenApiParameter("cursor", str, required=False)],
        responses={200: PortalDocumentResultSerializer},
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        member = require_client_portal_member(request.user)
        if member.organization is None:
            raise PermissionDenied("Client portal membership is required.")
        after = _decode_portal_cursor(request.query_params.get("cursor"), member=member)
        queryset = _portal_publications(request).order_by("title", "id")
        if after is not None:
            title, publication_id = after
            queryset = queryset.filter(Q(title__gt=title) | Q(title=title, id__gt=publication_id))
        scanned = list(queryset[: PORTAL_DOCUMENT_SCAN_LIMIT + 1])
        safe = _safe_portal_publications(scanned[:PORTAL_DOCUMENT_SCAN_LIMIT])
        page = safe[:PORTAL_DOCUMENT_PAGE_SIZE]
        if len(safe) > PORTAL_DOCUMENT_PAGE_SIZE:
            cursor_record = page[-1]
            has_more = True
        elif len(scanned) > PORTAL_DOCUMENT_SCAN_LIMIT and scanned:
            cursor_record = scanned[PORTAL_DOCUMENT_SCAN_LIMIT - 1]
            has_more = True
        else:
            cursor_record = None
            has_more = False
        response = Response(
            PortalDocumentResultSerializer(
                {
                    "results": page,
                    "count": len(page),
                    "has_more": has_more,
                    "next_cursor": _portal_cursor(cursor_record, member=member) if cursor_record else None,
                }
            ).data
        )
        response["Cache-Control"] = "private, no-store"
        return response


class ClientPortalDocumentDetailView(APIView):
    @extend_schema(operation_id="client_portal_documents_retrieve", responses={200: PortalDocumentDetailSerializer})
    def get(self, request, publication_entity_id):  # type: ignore[no-untyped-def]
        response = Response(PortalDocumentDetailSerializer(_portal_publication(request, publication_entity_id)).data)
        response["Cache-Control"] = "private, no-store"
        return response


class ClientPortalDocumentArtifactDownloadView(APIView):
    @extend_schema(
        operation_id="client_portal_document_artifacts_download",
        responses={(200, "application/octet-stream"): bytes, 409: OpenApiResponse(description="Integrity conflict")},
    )
    def get(self, request, publication_entity_id, artifact_entity_id):  # type: ignore[no-untyped-def]
        publication = _portal_publication(request, publication_entity_id)
        artifact = get_object_or_404(
            DocumentPublicationArtifact.objects.filter(publication=publication).select_related("entity"),
            entity_id=artifact_entity_id,
        )
        try:
            content = read_publication_artifact(artifact)
        except PublicationConflict as conflict:
            return HttpResponse(str(conflict), status=409, content_type="text/plain; charset=utf-8")
        response = HttpResponse(content, content_type="application/octet-stream")
        disposition = content_disposition_header(True, artifact.original_filename)
        if disposition is not None:
            response["Content-Disposition"] = disposition
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
