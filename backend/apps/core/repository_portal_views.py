"""Fail-closed client reads of explicitly delivered repository STATIC records."""

from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID

from django.core import signing
from django.core.signing import BadSignature
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import require_client_portal_member

from .models import RepositoryEvidenceAttachment, RepositoryStaticPublication, RepositoryStaticPublicationControlEvent
from .publications import MAX_RETAINED_ATTACHMENT_BYTES
from .repository_publication_render import MAX_RENDERED_PDF_BYTES, verify_retained_pdf_snapshot
from .repository_static_delivery import repository_static_delivery_ready
from .rls import OrganizationRLSMode, bind_local_rls_scope
from .scoping import DataScope

PAGE_SIZE = 10
SCAN_LIMIT = 20
CURSOR_SALT = "tekdocs.portal-repository-publications.v1"


class PortalRepositoryPublicationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    content_id = serializers.UUIDField()
    title = serializers.CharField()
    created_at = serializers.DateTimeField()


class PortalRepositoryAttachmentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    filename = serializers.CharField()
    media_type = serializers.CharField()
    size = serializers.IntegerField()


class PortalRepositoryPublicationDetailSerializer(PortalRepositoryPublicationSerializer):
    rendered_html = serializers.CharField()
    attachments = PortalRepositoryAttachmentSerializer(many=True)


class PortalRepositoryPublicationResultSerializer(serializers.Serializer):
    results = PortalRepositoryPublicationSerializer(many=True)
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    next_cursor = serializers.CharField(allow_null=True)


def _scope(request) -> tuple[UUID, UUID, UUID]:  # type: ignore[no-untyped-def]
    member = require_client_portal_member(request.user)
    organization = member.organization
    if organization is None:
        raise PermissionDenied("Client portal membership is required.")
    bind_local_rls_scope(
        DataScope.organization(member.tenant, organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    )
    return member.tenant.id, member.user.id, organization.id


def _publications(request) -> QuerySet[RepositoryStaticPublication]:  # type: ignore[no-untyped-def]
    tenant_id, _user_id, organization_id = _scope(request)
    released = RepositoryStaticPublicationControlEvent.objects.filter(
        publication_id=OuterRef("pk"), action=RepositoryStaticPublicationControlEvent.Action.RELEASED
    )
    withdrawn = RepositoryStaticPublicationControlEvent.objects.filter(
        publication_id=OuterRef("pk"), action=RepositoryStaticPublicationControlEvent.Action.WITHDRAWN
    )
    superseded = RepositoryStaticPublicationControlEvent.objects.filter(
        supersedes_id=OuterRef("pk"), action=RepositoryStaticPublicationControlEvent.Action.RELEASED
    )
    return (
        RepositoryStaticPublication.objects.filter(
            tenant_id=tenant_id,
            organization_id=organization_id,
            workspace__organization_id=organization_id,
            delivery_authorization__isnull=False,
        )
        .annotate(
            portal_released=Exists(released),
            portal_withdrawn=Exists(withdrawn),
            portal_superseded=Exists(superseded),
        )
        .filter(portal_released=True, portal_withdrawn=False, portal_superseded=False)
        .select_related("authorization__package__decision__evidence")
        .order_by("-created_at", "-id")
    )


def _data(publication: RepositoryStaticPublication) -> dict[str, object]:
    evidence = publication.authorization.package.decision.evidence
    return {
        "id": publication.id,
        "content_id": evidence.content_id,
        "title": evidence.manifest["title"],
        "created_at": publication.created_at,
    }


def _cursor(publication: RepositoryStaticPublication, *, scope: tuple[UUID, UUID, UUID]) -> str:
    return signing.dumps(
        {
            "scope": [str(item) for item in scope],
            "created_at": publication.created_at.isoformat(),
            "id": str(publication.id),
        },
        salt=CURSOR_SALT,
        compress=True,
    )


def _decode_cursor(value: str | None, *, scope: tuple[UUID, UUID, UUID]) -> tuple[datetime, UUID] | None:
    if value is None:
        return None
    if len(value) > 1024:
        raise serializers.ValidationError({"cursor": "Cursor is invalid."})
    try:
        payload = signing.loads(value, salt=CURSOR_SALT, max_age=60 * 60 * 24 * 30)
        if not isinstance(payload, dict) or payload.get("scope") != [str(item) for item in scope]:
            raise BadSignature
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        if created_at.tzinfo is None:
            raise BadSignature
        return created_at, UUID(str(payload["id"]))
    except (BadSignature, KeyError, TypeError, ValueError):
        raise serializers.ValidationError({"cursor": "Cursor is invalid."}) from None


def _publication(request, publication_id: UUID) -> RepositoryStaticPublication:  # type: ignore[no-untyped-def]
    publication = get_object_or_404(_publications(request), pk=publication_id)
    if not repository_static_delivery_ready(publication):
        raise Http404
    return publication


class ClientPortalRepositoryPublicationListView(APIView):
    @extend_schema(
        operation_id="client_portal_repository_publications_list",
        parameters=[OpenApiParameter("cursor", str, required=False)],
        responses={200: PortalRepositoryPublicationResultSerializer},
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        scope = _scope(request)
        after = _decode_cursor(request.query_params.get("cursor"), scope=scope)
        queryset = _publications(request)
        if after is not None:
            created_at, publication_id = after
            queryset = queryset.filter(
                Q(created_at__lt=created_at) | Q(created_at=created_at, id__lt=publication_id)
            )
        scanned = list(queryset[: SCAN_LIMIT + 1])
        safe = [record for record in scanned[:SCAN_LIMIT] if repository_static_delivery_ready(record)]
        page = safe[:PAGE_SIZE]
        if len(safe) > PAGE_SIZE:
            cursor_record = page[-1]
        elif len(scanned) > SCAN_LIMIT:
            cursor_record = scanned[SCAN_LIMIT - 1]
        else:
            cursor_record = None
        response = Response(
            PortalRepositoryPublicationResultSerializer(
                {
                    "results": [_data(record) for record in page],
                    "count": len(page),
                    "has_more": cursor_record is not None,
                    "next_cursor": _cursor(cursor_record, scope=scope) if cursor_record else None,
                }
            ).data
        )
        response["Cache-Control"] = "private, no-store"
        return response


class ClientPortalRepositoryPublicationDetailView(APIView):
    @extend_schema(
        operation_id="client_portal_repository_publications_retrieve",
        responses={200: PortalRepositoryPublicationDetailSerializer},
    )
    def get(self, request, publication_id):  # type: ignore[no-untyped-def]
        publication = _publication(request, publication_id)
        evidence = publication.authorization.package.decision.evidence
        response = Response(
            PortalRepositoryPublicationDetailSerializer(
                {
                    **_data(publication),
                    "rendered_html": evidence.manifest["rendered_snapshot"]["html"],
                    "attachments": [
                        {key: item[key] for key in ("id", "filename", "media_type", "size")}
                        for item in evidence.manifest.get("attachments", [])
                    ],
                }
            ).data
        )
        response["Cache-Control"] = "private, no-store"
        return response


class ClientPortalRepositoryPublicationPDFView(APIView):
    @extend_schema(
        operation_id="client_portal_repository_publications_pdf_download",
        responses={(200, "application/pdf"): bytes, 404: OpenApiResponse(description="Unavailable publication")},
    )
    def get(self, request, publication_id):  # type: ignore[no-untyped-def]
        publication = _publication(request, publication_id)
        evidence = publication.authorization.package.decision.evidence
        try:
            with evidence.pdf_file.storage.open(evidence.pdf_file.name, "rb") as stream:
                content = bytes(stream.read(MAX_RENDERED_PDF_BYTES + 1))
        except (OSError, ValueError, TypeError):
            raise Http404 from None
        if not verify_retained_pdf_snapshot(manifest=evidence.manifest, content=content):
            raise Http404
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="repository-publication.pdf"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ClientPortalRepositoryPublicationAttachmentView(APIView):
    @extend_schema(
        operation_id="client_portal_repository_publications_attachment_download",
        responses={
            (200, "application/octet-stream"): bytes,
            404: OpenApiResponse(description="Unavailable attachment"),
        },
    )
    def get(self, request, publication_id, artifact_id):  # type: ignore[no-untyped-def]
        publication = _publication(request, publication_id)
        evidence = publication.authorization.package.decision.evidence
        artifact = get_object_or_404(
            RepositoryEvidenceAttachment,
            pk=artifact_id,
            evidence=evidence,
            tenant_id=publication.tenant_id,
            organization_id=publication.organization_id,
            workspace_id=publication.workspace_id,
        )
        descriptor = next(
            (
                item for item in evidence.manifest.get("attachments", [])
                if isinstance(item, dict) and item.get("id") == str(artifact.id)
            ),
            None,
        )
        if descriptor is None or artifact.size > MAX_RETAINED_ATTACHMENT_BYTES:
            raise Http404
        try:
            with artifact.file.storage.open(artifact.file.name, "rb") as stream:
                content = bytes(stream.read(MAX_RETAINED_ATTACHMENT_BYTES + 1))
        except (OSError, ValueError, TypeError):
            raise Http404 from None
        if (
            len(content) != artifact.size
            or len(content) > MAX_RETAINED_ATTACHMENT_BYTES
            or hashlib.sha256(content).hexdigest() != artifact.checksum
            or descriptor.get("checksum") != artifact.checksum
            or descriptor.get("size") != artifact.size
            or descriptor.get("source_id") != str(artifact.source_attachment_id)
        ):
            raise Http404
        response = HttpResponse(content, content_type="application/octet-stream")
        response["Content-Disposition"] = 'attachment; filename="repository-publication-attachment"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
