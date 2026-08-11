from uuid import UUID

from django.db.models import Exists, OuterRef, Prefetch, QuerySet
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import require_client_portal_member

from .models import (
    DocumentPublication,
    DocumentPublicationArtifact,
    DocumentPublicationControlEvent,
    Entity,
    EntityVisibility,
    PublicationAudience,
    PublicationControlAction,
)
from .publications import PublicationConflict, read_publication_artifact
from .rls import OrganizationRLSMode, bind_local_rls_scope
from .scoping import DataScope
from .serializers import PortalDocumentDetailSerializer, PortalDocumentResultSerializer


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


class ClientPortalDocumentListView(APIView):
    @extend_schema(operation_id="client_portal_documents_list", responses={200: PortalDocumentResultSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        records = [
            publication
            for publication in _portal_publications(request).order_by("title", "entity_id")[:500]
            if _reference_projection_safe(publication)
        ]
        return Response(PortalDocumentResultSerializer({"results": records, "count": len(records)}).data)


class ClientPortalDocumentDetailView(APIView):
    @extend_schema(operation_id="client_portal_documents_retrieve", responses={200: PortalDocumentDetailSerializer})
    def get(self, request, publication_entity_id):  # type: ignore[no-untyped-def]
        return Response(PortalDocumentDetailSerializer(_portal_publication(request, publication_entity_id)).data)


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
