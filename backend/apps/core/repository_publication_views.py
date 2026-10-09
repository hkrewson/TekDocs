"""Staff-only review entry point for signed repository publication evidence."""

from __future__ import annotations

import hashlib
from typing import Literal, cast
from uuid import UUID

from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .content_publication_sources import ContentPublicationSourceError
from .document_views import _msp_workspace, _organization_workspace
from .models import (
    AuditEvent,
    PublicationAudience,
    RepositoryEvidenceAttachment,
    RepositoryEvidenceReviewDecision,
    RepositoryPackageAuthorization,
    RepositoryPublicationEvidence,
    RepositoryPublicationPackage,
    RepositoryStaticDeliveryAuthorization,
    RepositoryStaticPublication,
    RepositoryStaticPublicationControlEvent,
    WorkspaceRepository,
    workspace_for_owner,
)
from .publications import MAX_RETAINED_ATTACHMENT_BYTES
from .repository_package_authorization import (
    RepositoryPackageAuthorizationError,
    decide_repository_package,
)
from .repository_publication_evidence import (
    RepositoryPublicationEvidenceError,
    retain_repository_publication_evidence,
    verify_repository_publication_evidence,
)
from .repository_publication_packages import (
    RepositoryPublicationPackageError,
    create_repository_publication_package,
    verify_repository_publication_package,
)
from .repository_publication_render import (
    MAX_RENDERED_PDF_BYTES,
    verify_retained_pdf_snapshot,
    verify_retained_rendered_snapshot,
)
from .repository_service import RepositoryServiceError
from .repository_static_controls import (
    RepositoryStaticControlError,
    record_repository_static_control,
    repository_static_state,
)
from .repository_static_delivery import (
    RepositoryStaticDeliveryError,
    authorize_repository_static_delivery,
    repository_static_delivery_ready,
)
from .repository_static_publications import (
    RepositoryStaticPublicationError,
    create_repository_static_publication,
    verify_repository_static_publication,
)
from .workspaces import ResolvedWorkspace


class RepositoryEvidenceWriteSerializer(serializers.Serializer):
    content_id = serializers.UUIDField()
    audience = serializers.ChoiceField(choices=PublicationAudience.choices)


class RepositoryEvidenceSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    content_id = serializers.UUIDField()
    audience = serializers.ChoiceField(choices=PublicationAudience.choices)
    title = serializers.CharField()
    source_commit = serializers.CharField()
    signed_at = serializers.DateTimeField()
    signed_by_id = serializers.UUIDField()
    verified = serializers.BooleanField(required=False)


class RepositoryEvidenceQuerySerializer(serializers.Serializer):
    content_id = serializers.UUIDField(required=False)
    page = serializers.IntegerField(min_value=1, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False, default=25)


class RepositoryEvidencePageSerializer(serializers.Serializer):
    results = RepositoryEvidenceSummarySerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()


class RepositoryEvidenceReviewAttachmentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    source_id = serializers.UUIDField()
    filename = serializers.CharField()
    media_type = serializers.CharField()
    size = serializers.IntegerField()


class RepositoryEvidenceReviewSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    content_id = serializers.UUIDField()
    audience = serializers.ChoiceField(choices=PublicationAudience.choices)
    title = serializers.CharField()
    source_commit = serializers.CharField()
    signed_at = serializers.DateTimeField()
    canonical_markdown = serializers.CharField()
    attachments = RepositoryEvidenceReviewAttachmentSerializer(many=True)
    verified = serializers.BooleanField()


class RepositoryEvidenceDecisionWriteSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=RepositoryEvidenceReviewDecision.Outcome.choices)
    reason = serializers.CharField(max_length=500, allow_blank=False, trim_whitespace=True)


class RepositoryEvidenceDecisionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    evidence_id = serializers.UUIDField()
    outcome = serializers.ChoiceField(choices=RepositoryEvidenceReviewDecision.Outcome.choices)
    reason = serializers.CharField()
    actor_id = serializers.UUIDField()
    occurred_at = serializers.DateTimeField()
    permits_distribution = serializers.BooleanField()


class RepositoryPackageSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    evidence_id = serializers.UUIDField()
    decision_id = serializers.UUIDField()
    source_commit = serializers.CharField()
    manifest_digest = serializers.CharField()
    created_by_id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    verified = serializers.BooleanField()
    permits_distribution = serializers.BooleanField()


class RepositoryPackageAuthorizationWriteSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=RepositoryPackageAuthorization.Outcome.choices)
    reason = serializers.CharField(max_length=500, allow_blank=False, trim_whitespace=True)


class RepositoryPackageAuthorizationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    package_id = serializers.UUIDField()
    outcome = serializers.ChoiceField(choices=RepositoryPackageAuthorization.Outcome.choices)
    reason = serializers.CharField()
    actor_id = serializers.UUIDField()
    occurred_at = serializers.DateTimeField()
    permits_distribution = serializers.BooleanField()


class RepositoryStaticPublicationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    authorization_id = serializers.UUIDField()
    package_id = serializers.UUIDField()
    source_commit = serializers.CharField()
    content_digest = serializers.CharField()
    created_by_id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    verified = serializers.BooleanField()
    permits_distribution = serializers.BooleanField()


class RepositoryStaticControlWriteSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=RepositoryStaticPublicationControlEvent.Action.choices)
    reason = serializers.CharField(max_length=500, allow_blank=False, trim_whitespace=True)
    supersedes_id = serializers.UUIDField(required=False, allow_null=True)


class RepositoryStaticControlEventSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=RepositoryStaticPublicationControlEvent.Action.choices)
    supersedes_id = serializers.UUIDField(allow_null=True)
    reason = serializers.CharField()
    actor_id = serializers.UUIDField()
    occurred_at = serializers.DateTimeField()


class RepositoryStaticControlSerializer(serializers.Serializer):
    publication_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["recorded", "released", "superseded", "withdrawn"])
    events = RepositoryStaticControlEventSerializer(many=True)
    verified = serializers.BooleanField()
    permits_distribution = serializers.BooleanField()


class RepositoryStaticDeliveryWriteSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, allow_blank=False, trim_whitespace=True)


class RepositoryStaticDeliverySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    publication_id = serializers.UUIDField()
    reason = serializers.CharField()
    actor_id = serializers.UUIDField()
    occurred_at = serializers.DateTimeField()
    currently_effective = serializers.BooleanField()
    permits_distribution = serializers.BooleanField()


def _repository(workspace: ResolvedWorkspace) -> WorkspaceRepository:
    if workspace.member.surface == "client_portal":
        raise PermissionDenied("Repository publication evidence is unavailable to this audience")
    owner = workspace_for_owner(tenant=workspace.member.tenant, organization=workspace.organization)
    return get_object_or_404(WorkspaceRepository, workspace=owner)


def _summary(evidence: RepositoryPublicationEvidence, *, verify: bool = False) -> dict[str, object]:
    summary: dict[str, object] = {
        "id": evidence.id,
        "content_id": evidence.content_id,
        "audience": evidence.audience,
        "title": evidence.manifest.get("title", ""),
        "source_commit": evidence.source_commit.object_id,
        "signed_at": evidence.signed_at,
        "signed_by_id": evidence.signed_by_id,
    }
    if verify:
        summary["verified"] = verify_repository_publication_evidence(evidence)["valid"]
    return cast(dict[str, object], RepositoryEvidenceSummarySerializer(summary).data)


def _collection(request, workspace: ResolvedWorkspace) -> Response:  # type: ignore[no-untyped-def]
    repository = _repository(workspace)
    records = RepositoryPublicationEvidence.objects.filter(repository=repository, workspace=repository.workspace)
    if request.method == "GET":
        query = RepositoryEvidenceQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        if content_id := query.validated_data.get("content_id"):
            records = records.filter(content_id=content_id)
        page = query.validated_data["page"]
        page_size = query.validated_data["page_size"]
        count = records.count()
        start = (page - 1) * page_size
        return Response(
            RepositoryEvidencePageSerializer(
                {
                    "results": [
                        _summary(item) for item in records.select_related("source_commit")[start : start + page_size]
                    ],
                    "page": page,
                    "page_size": page_size,
                    "count": count,
                    "has_more": start + page_size < count,
                }
            ).data
        )
    serializer = RepositoryEvidenceWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        evidence = retain_repository_publication_evidence(
            repository_id=repository.id,
            content_id=serializer.validated_data["content_id"],
            audience=serializer.validated_data["audience"],
            actor=request.user,
        )
    except (ContentPublicationSourceError, RepositoryPublicationEvidenceError, RepositoryServiceError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(_summary(evidence, verify=True), status=status.HTTP_201_CREATED)


def _evidence(workspace: ResolvedWorkspace, evidence_id: UUID) -> RepositoryPublicationEvidence:
    repository = _repository(workspace)
    return get_object_or_404(
        RepositoryPublicationEvidence.objects.select_related("source_commit"),
        pk=evidence_id,
        repository=repository,
        workspace=repository.workspace,
    )


def _detail(workspace: ResolvedWorkspace, evidence_id: UUID) -> Response:
    return Response(_summary(_evidence(workspace, evidence_id), verify=True))


def _review(request, workspace: ResolvedWorkspace, evidence_id: UUID) -> Response:  # type: ignore[no-untyped-def]
    require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization)
    evidence = _evidence(workspace, evidence_id)
    if not verify_repository_publication_evidence(evidence)["valid"]:
        return Response(
            {"detail": "Retained publication evidence failed verification"}, status=status.HTTP_409_CONFLICT
        )
    return Response(
        RepositoryEvidenceReviewSerializer(
            {
                "id": evidence.id,
                "content_id": evidence.content_id,
                "audience": evidence.audience,
                "title": evidence.manifest["title"],
                "source_commit": evidence.source_commit.object_id,
                "signed_at": evidence.signed_at,
                "canonical_markdown": evidence.canonical_markdown,
                "attachments": [
                    {
                        "id": item["id"],
                        "source_id": item["source_id"],
                        "filename": item["filename"],
                        "media_type": item["media_type"],
                        "size": item["size"],
                    }
                    for item in evidence.manifest.get("attachments", [])
                ],
                "verified": True,
            }
        ).data
    )


def _review_pdf(request, workspace: ResolvedWorkspace, evidence_id: UUID) -> HttpResponse:  # type: ignore[no-untyped-def]
    require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization)
    evidence = _evidence(workspace, evidence_id)
    if not verify_repository_publication_evidence(evidence)["pdf_snapshot_attested"]:
        response = HttpResponse("Retained publication evidence failed verification", status=409)
    else:
        try:
            with evidence.pdf_file.storage.open(evidence.pdf_file.name, "rb") as stream:
                content = bytes(stream.read(MAX_RENDERED_PDF_BYTES + 1))
        except (OSError, ValueError, TypeError):
            content = b""
        if not verify_retained_pdf_snapshot(manifest=evidence.manifest, content=content):
            response = HttpResponse("Retained publication PDF failed verification", status=409)
        else:
            response = HttpResponse(content, content_type="application/pdf")
            response["Content-Disposition"] = 'attachment; filename="repository-evidence-snapshot.pdf"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _review_html(request, workspace: ResolvedWorkspace, evidence_id: UUID) -> HttpResponse:  # type: ignore[no-untyped-def]
    require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization)
    evidence = _evidence(workspace, evidence_id)
    if not verify_repository_publication_evidence(evidence)["rendered_snapshot_attested"]:
        response = HttpResponse("Retained publication evidence failed verification", status=409)
    elif not verify_retained_rendered_snapshot(manifest=evidence.manifest):
        response = HttpResponse("Retained publication HTML failed verification", status=409)
    else:
        content = evidence.manifest["rendered_snapshot"]["html"].encode("utf-8")
        response = HttpResponse(content, content_type="text/html; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="repository-evidence-snapshot.html"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response


def _review_attachment(  # type: ignore[no-untyped-def]
    request, workspace: ResolvedWorkspace, evidence_id: UUID, artifact_id: UUID
) -> HttpResponse:
    require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization)
    evidence = _evidence(workspace, evidence_id)
    artifact = get_object_or_404(
        RepositoryEvidenceAttachment, pk=artifact_id, evidence=evidence,
        workspace=evidence.workspace, tenant=evidence.tenant, organization=evidence.organization,
    )
    if not verify_repository_publication_evidence(evidence)["valid"]:
        response = HttpResponse("Retained publication evidence failed verification", status=409)
    else:
        descriptors = evidence.manifest.get("attachments", [])
        descriptor = next(
            (item for item in descriptors if isinstance(item, dict) and item.get("id") == str(artifact.id)), None
        )
        content = b""
        if descriptor is not None and 0 <= artifact.size <= MAX_RETAINED_ATTACHMENT_BYTES:
            try:
                with artifact.file.storage.open(artifact.file.name, "rb") as stream:
                    content = bytes(stream.read(MAX_RETAINED_ATTACHMENT_BYTES + 1))
            except (OSError, ValueError, TypeError):
                pass
        if (
            descriptor is None
            or len(content) != artifact.size
            or len(content) > MAX_RETAINED_ATTACHMENT_BYTES
            or hashlib.sha256(content).hexdigest() != descriptor.get("checksum")
            or descriptor.get("size") != artifact.size
            or descriptor.get("source_id") != str(artifact.source_attachment_id)
        ):
            response = HttpResponse("Retained publication attachment failed verification", status=409)
        else:
            response = HttpResponse(content, content_type="application/octet-stream")
            response["Content-Disposition"] = 'attachment; filename="repository-evidence-attachment"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _decision(request, workspace: ResolvedWorkspace, evidence_id: UUID) -> Response:  # type: ignore[no-untyped-def]
    require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization)
    evidence = _evidence(workspace, evidence_id)
    if request.method == "GET":
        decision = RepositoryEvidenceReviewDecision.objects.filter(evidence=evidence).first()
        if decision is None:
            return Response({"detail": "No review decision exists"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_decision_data(decision))
    serializer = RepositoryEvidenceDecisionWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if evidence.audience != PublicationAudience.CLIENT_VISIBLE:
        return Response(
            {"detail": "Only client-visible evidence requires this review"}, status=status.HTTP_409_CONFLICT
        )
    if (
        serializer.validated_data["outcome"] == RepositoryEvidenceReviewDecision.Outcome.ACCEPTED_FOR_PACKAGING
        and evidence.signed_by_id == request.user.id
    ):
        return Response(
            {"detail": "The evidence signer cannot accept their own snapshot"}, status=status.HTTP_409_CONFLICT
        )
    if not verify_repository_publication_evidence(evidence)["valid"]:
        return Response(
            {"detail": "Retained publication evidence failed verification"}, status=status.HTTP_409_CONFLICT
        )
    try:
        with transaction.atomic():
            decision = RepositoryEvidenceReviewDecision.objects.create(
                tenant_id=evidence.tenant_id,
                organization_id=evidence.organization_id,
                workspace_id=evidence.workspace_id,
                evidence=evidence,
                outcome=serializer.validated_data["outcome"],
                reason=serializer.validated_data["reason"],
                actor=request.user,
            )
    except IntegrityError:
        return Response({"detail": "Evidence already has a final review decision"}, status=status.HTTP_409_CONFLICT)
    return Response(_decision_data(decision), status=status.HTTP_201_CREATED)


def _decision_data(decision: RepositoryEvidenceReviewDecision) -> dict[str, object]:
    return cast(
        dict[str, object],
        RepositoryEvidenceDecisionSerializer(
            {
                "id": decision.id,
                "evidence_id": decision.evidence_id,
                "outcome": decision.outcome,
                "reason": decision.reason,
                "actor_id": decision.actor_id,
                "occurred_at": decision.occurred_at,
                "permits_distribution": False,
            }
        ).data,
    )


def _package_data(package: RepositoryPublicationPackage) -> dict[str, object]:
    return cast(
        dict[str, object],
        RepositoryPackageSerializer(
            {
                "id": package.id,
                "evidence_id": package.decision.evidence_id,
                "decision_id": package.decision_id,
                "source_commit": package.manifest.get("source_commit", ""),
                "manifest_digest": package.manifest_digest,
                "created_by_id": package.created_by_id,
                "created_at": package.created_at,
                "verified": verify_repository_publication_package(package),
                "permits_distribution": False,
            }
        ).data,
    )


def _package(request, workspace: ResolvedWorkspace, evidence_id: UUID) -> Response:  # type: ignore[no-untyped-def]
    require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization)
    evidence = _evidence(workspace, evidence_id)
    decision = RepositoryEvidenceReviewDecision.objects.filter(evidence=evidence).first()
    if decision is None:
        return Response({"detail": "Accepted review decision is required"}, status=status.HTTP_409_CONFLICT)
    if request.method == "GET":
        package = RepositoryPublicationPackage.objects.filter(decision=decision).first()
        if package is None:
            return Response({"detail": "No package exists"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_package_data(package))
    try:
        package = create_repository_publication_package(decision_id=decision.id, actor=request.user)
    except (RepositoryPublicationPackageError, IntegrityError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(_package_data(package), status=status.HTTP_201_CREATED)


def _authorization_data(authorization: RepositoryPackageAuthorization) -> dict[str, object]:
    return cast(
        dict[str, object],
        RepositoryPackageAuthorizationSerializer(
            {
                "id": authorization.id,
                "package_id": authorization.package_id,
                "outcome": authorization.outcome,
                "reason": authorization.reason,
                "actor_id": authorization.actor_id,
                "occurred_at": authorization.occurred_at,
                "permits_distribution": False,
            }
        ).data,
    )


def _authorization(request, workspace: ResolvedWorkspace, evidence_id: UUID) -> Response:  # type: ignore[no-untyped-def]
    require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization)
    evidence = _evidence(workspace, evidence_id)
    package = RepositoryPublicationPackage.objects.filter(decision__evidence=evidence).first()
    if package is None:
        return Response({"detail": "Verified package is required"}, status=status.HTTP_409_CONFLICT)
    if request.method == "GET":
        authorization = RepositoryPackageAuthorization.objects.filter(package=package).first()
        if authorization is None:
            return Response({"detail": "No authorization decision exists"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_authorization_data(authorization))
    serializer = RepositoryPackageAuthorizationWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        authorization = decide_repository_package(
            package_id=package.id,
            outcome=serializer.validated_data["outcome"],
            reason=serializer.validated_data["reason"],
            actor=request.user,
        )
    except (RepositoryPackageAuthorizationError, IntegrityError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(_authorization_data(authorization), status=status.HTTP_201_CREATED)


def _static_publication_data(publication: RepositoryStaticPublication) -> dict[str, object]:
    return cast(
        dict[str, object],
        RepositoryStaticPublicationSerializer(
            {
                "id": publication.id,
                "authorization_id": publication.authorization_id,
                "package_id": publication.authorization.package_id,
                "source_commit": publication.manifest.get("source_commit", ""),
                "content_digest": publication.content_digest,
                "created_by_id": publication.created_by_id,
                "created_at": publication.created_at,
                "verified": verify_repository_static_publication(publication),
                "permits_distribution": False,
            }
        ).data,
    )


def _static_publication(request, workspace: ResolvedWorkspace, evidence_id: UUID) -> Response:  # type: ignore[no-untyped-def]
    require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization)
    evidence = _evidence(workspace, evidence_id)
    authorization = RepositoryPackageAuthorization.objects.filter(package__decision__evidence=evidence).first()
    if authorization is None:
        return Response({"detail": "Authorized package is required"}, status=status.HTTP_409_CONFLICT)
    if request.method == "GET":
        publication = RepositoryStaticPublication.objects.filter(authorization=authorization).first()
        if publication is None:
            return Response({"detail": "No STATIC record exists"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_static_publication_data(publication))
    try:
        publication = create_repository_static_publication(authorization_id=authorization.id, actor=request.user)
    except (RepositoryStaticPublicationError, IntegrityError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(_static_publication_data(publication), status=status.HTTP_201_CREATED)


def _static_export(  # type: ignore[no-untyped-def]
    request, workspace: ResolvedWorkspace, evidence_id: UUID, format_name: Literal["md", "html", "pdf"]
) -> HttpResponse:
    require_permission(request.user, PermissionKey.DOCUMENTS_APPROVE, organization=workspace.organization)
    evidence = _evidence(workspace, evidence_id)
    publication = get_object_or_404(
        RepositoryStaticPublication,
        authorization__package__decision__evidence=evidence,
        workspace=evidence.workspace,
        tenant=evidence.tenant,
        organization=evidence.organization,
    )
    if not verify_repository_static_publication(publication):
        response = HttpResponse("Retained STATIC publication failed verification", status=409)
    else:
        content: bytes | None
        if format_name == "md":
            content = evidence.canonical_markdown.encode("utf-8")
            media_type = "text/markdown; charset=utf-8"
        elif format_name == "html":
            snapshot = evidence.manifest.get("rendered_snapshot")
            content = (
                snapshot["html"].encode("utf-8")
                if isinstance(snapshot, dict) and verify_retained_rendered_snapshot(manifest=evidence.manifest)
                else None
            )
            media_type = "text/html; charset=utf-8"
        else:
            content = None
            if evidence.pdf_file.name:
                try:
                    with evidence.pdf_file.storage.open(evidence.pdf_file.name, "rb") as stream:
                        candidate = bytes(stream.read(MAX_RENDERED_PDF_BYTES + 1))
                    if verify_retained_pdf_snapshot(manifest=evidence.manifest, content=candidate):
                        content = candidate
                except (OSError, ValueError, TypeError):
                    pass
            media_type = "application/pdf"
        if content is None:
            response = HttpResponse("Retained STATIC publication export failed verification", status=409)
        else:
            AuditEvent.objects.create(
                tenant=workspace.member.tenant,
                actor=request.user,
                action="repository_static_publication.exported",
                entity_id=publication.id,
                request_id=getattr(request, "request_id", None),
                metadata={"format": format_name, "publication_digest": publication.content_digest},
            )
            response = HttpResponse(content, content_type=media_type)
            response["Content-Disposition"] = (
                f'attachment; filename="repository-static-publication.{format_name}"'
            )
            response["X-TekDocs-Export-Class"] = "immutable_static_publication"
            response["X-TekDocs-Publication-Digest"] = publication.content_digest
            if format_name == "html":
                response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _static_control_data(publication: RepositoryStaticPublication) -> dict[str, object]:
    return cast(
        dict[str, object],
        RepositoryStaticControlSerializer(
            {
                "publication_id": publication.id,
                "state": repository_static_state(publication),
                "events": [
                    {
                        "id": event.id,
                        "action": event.action,
                        "supersedes_id": event.supersedes_id,
                        "reason": event.reason,
                        "actor_id": event.actor_id,
                        "occurred_at": event.occurred_at,
                    }
                    for event in publication.control_events.all()
                ],
                "verified": verify_repository_static_publication(publication),
                "permits_distribution": False,
            }
        ).data,
    )


def _static_control(request, workspace: ResolvedWorkspace, evidence_id: UUID) -> Response:  # type: ignore[no-untyped-def]
    require_permission(request.user, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization)
    evidence = _evidence(workspace, evidence_id)
    publication = RepositoryStaticPublication.objects.filter(
        authorization__package__decision__evidence=evidence
    ).first()
    if publication is None:
        return Response({"detail": "No STATIC record exists"}, status=status.HTTP_404_NOT_FOUND)
    if request.method == "GET":
        return Response(_static_control_data(publication))
    serializer = RepositoryStaticControlWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        record_repository_static_control(
            publication_id=publication.id,
            action=serializer.validated_data["action"],
            reason=serializer.validated_data["reason"],
            actor=request.user,
            supersedes_id=serializer.validated_data.get("supersedes_id"),
        )
    except (RepositoryStaticControlError, IntegrityError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(_static_control_data(publication), status=status.HTTP_201_CREATED)


def _static_delivery_data(authorization: RepositoryStaticDeliveryAuthorization) -> dict[str, object]:
    effective = repository_static_delivery_ready(authorization.publication)
    return cast(
        dict[str, object],
        RepositoryStaticDeliverySerializer(
            {
                "id": authorization.id,
                "publication_id": authorization.publication_id,
                "reason": authorization.reason,
                "actor_id": authorization.actor_id,
                "occurred_at": authorization.occurred_at,
                "currently_effective": effective,
                "permits_distribution": effective,
            }
        ).data,
    )


def _static_delivery(request, workspace: ResolvedWorkspace, evidence_id: UUID) -> Response:  # type: ignore[no-untyped-def]
    require_permission(request.user, PermissionKey.DOCUMENTS_APPROVE, organization=workspace.organization)
    evidence = _evidence(workspace, evidence_id)
    publication = RepositoryStaticPublication.objects.filter(
        authorization__package__decision__evidence=evidence
    ).first()
    if publication is None:
        return Response({"detail": "No STATIC record exists"}, status=status.HTTP_404_NOT_FOUND)
    if request.method == "GET":
        authorization = RepositoryStaticDeliveryAuthorization.objects.filter(publication=publication).first()
        if authorization is None:
            return Response({"detail": "Delivery authorization does not exist"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_static_delivery_data(authorization))
    serializer = RepositoryStaticDeliveryWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        authorization = authorize_repository_static_delivery(
            publication_id=publication.id, reason=serializer.validated_data["reason"], actor=request.user
        )
    except (RepositoryStaticDeliveryError, IntegrityError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(_static_delivery_data(authorization), status=status.HTTP_201_CREATED)


class MSPRepositoryEvidenceCollectionView(APIView):
    @extend_schema(
        operation_id="repository_evidence_msp_list",
        parameters=[RepositoryEvidenceQuerySerializer],
        responses={200: RepositoryEvidencePageSerializer},
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        return _collection(request, _msp_workspace(request, PermissionKey.DOCUMENTS_PUBLISH))

    @extend_schema(
        operation_id="repository_evidence_msp_create",
        request=RepositoryEvidenceWriteSerializer,
        responses={201: RepositoryEvidenceSummarySerializer},
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        return _collection(request, _msp_workspace(request, PermissionKey.DOCUMENTS_PUBLISH))


class MSPRepositoryEvidenceDetailView(APIView):
    @extend_schema(
        operation_id="repository_evidence_msp_retrieve", responses={200: RepositoryEvidenceSummarySerializer}
    )
    def get(self, request, evidence_id):  # type: ignore[no-untyped-def]
        return _detail(_msp_workspace(request, PermissionKey.DOCUMENTS_PUBLISH), evidence_id)


class MSPRepositoryEvidenceReviewView(APIView):
    @extend_schema(operation_id="repository_evidence_msp_review", responses={200: RepositoryEvidenceReviewSerializer})
    def get(self, request, evidence_id):  # type: ignore[no-untyped-def]
        return _review(request, _msp_workspace(request, PermissionKey.DOCUMENTS_APPROVE), evidence_id)


class MSPRepositoryEvidenceReviewPDFView(APIView):
    @extend_schema(
        operation_id="repository_evidence_msp_review_pdf",
        responses={(200, "application/pdf"): bytes, 409: OpenApiResponse(description="Integrity conflict")},
    )
    def get(self, request, evidence_id):  # type: ignore[no-untyped-def]
        return _review_pdf(request, _msp_workspace(request, PermissionKey.DOCUMENTS_APPROVE), evidence_id)


class MSPRepositoryEvidenceReviewHTMLView(APIView):
    @extend_schema(
        operation_id="repository_evidence_msp_review_html",
        responses={(200, "text/html"): bytes, 409: OpenApiResponse(description="Integrity conflict")},
    )
    def get(self, request, evidence_id):  # type: ignore[no-untyped-def]
        return _review_html(request, _msp_workspace(request, PermissionKey.DOCUMENTS_APPROVE), evidence_id)


class MSPRepositoryEvidenceReviewAttachmentView(APIView):
    @extend_schema(
        operation_id="repository_evidence_msp_review_attachment",
        responses={(200, "application/octet-stream"): bytes, 409: OpenApiResponse(description="Integrity conflict")},
    )
    def get(self, request, evidence_id, artifact_id):  # type: ignore[no-untyped-def]
        return _review_attachment(
            request, _msp_workspace(request, PermissionKey.DOCUMENTS_APPROVE), evidence_id, artifact_id
        )


class OrganizationRepositoryEvidenceCollectionView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_list",
        parameters=[RepositoryEvidenceQuerySerializer],
        responses={200: RepositoryEvidencePageSerializer},
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _collection(
            request, _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_PUBLISH)
        )

    @extend_schema(
        operation_id="repository_evidence_organization_create",
        request=RepositoryEvidenceWriteSerializer,
        responses={201: RepositoryEvidenceSummarySerializer},
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _collection(
            request, _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_PUBLISH)
        )


class OrganizationRepositoryEvidenceDetailView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_retrieve",
        responses={200: RepositoryEvidenceSummarySerializer},
    )
    def get(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _detail(
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_PUBLISH), evidence_id
        )


class OrganizationRepositoryEvidenceReviewView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_review", responses={200: RepositoryEvidenceReviewSerializer}
    )
    def get(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _review(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
        )


class OrganizationRepositoryEvidenceReviewPDFView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_review_pdf",
        responses={(200, "application/pdf"): bytes, 409: OpenApiResponse(description="Integrity conflict")},
    )
    def get(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _review_pdf(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
        )


class OrganizationRepositoryEvidenceReviewHTMLView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_review_html",
        responses={(200, "text/html"): bytes, 409: OpenApiResponse(description="Integrity conflict")},
    )
    def get(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _review_html(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
        )


class OrganizationRepositoryEvidenceReviewAttachmentView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_review_attachment",
        responses={(200, "application/octet-stream"): bytes, 409: OpenApiResponse(description="Integrity conflict")},
    )
    def get(self, request, organization_entity_id, evidence_id, artifact_id):  # type: ignore[no-untyped-def]
        return _review_attachment(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
            artifact_id,
        )


class OrganizationRepositoryEvidenceDecisionView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_decision_retrieve",
        responses={200: RepositoryEvidenceDecisionSerializer},
    )
    def get(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _decision(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
        )

    @extend_schema(
        operation_id="repository_evidence_organization_decision_create",
        request=RepositoryEvidenceDecisionWriteSerializer,
        responses={201: RepositoryEvidenceDecisionSerializer},
    )
    def post(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _decision(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
        )


class OrganizationRepositoryEvidencePackageView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_package_retrieve",
        responses={200: RepositoryPackageSerializer},
    )
    def get(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _package(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_PUBLISH),
            evidence_id,
        )

    @extend_schema(
        operation_id="repository_evidence_organization_package_create",
        request=None,
        responses={201: RepositoryPackageSerializer},
    )
    def post(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _package(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_PUBLISH),
            evidence_id,
        )


class OrganizationRepositoryPackageAuthorizationView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_package_authorization_retrieve",
        responses={200: RepositoryPackageAuthorizationSerializer},
    )
    def get(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _authorization(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
        )

    @extend_schema(
        operation_id="repository_evidence_organization_package_authorization_create",
        request=RepositoryPackageAuthorizationWriteSerializer,
        responses={201: RepositoryPackageAuthorizationSerializer},
    )
    def post(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _authorization(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
        )


class OrganizationRepositoryStaticPublicationView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_static_publication_retrieve",
        responses={200: RepositoryStaticPublicationSerializer},
    )
    def get(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _static_publication(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_PUBLISH),
            evidence_id,
        )

    @extend_schema(
        operation_id="repository_evidence_organization_static_publication_create",
        request=None,
        responses={201: RepositoryStaticPublicationSerializer},
    )
    def post(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _static_publication(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_PUBLISH),
            evidence_id,
        )


class OrganizationRepositoryStaticMarkdownExportView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_static_markdown_export",
        responses={(200, "text/markdown"): bytes, 409: OpenApiResponse(description="Integrity conflict")},
    )
    def get(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _static_export(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
            "md",
        )


class OrganizationRepositoryStaticHTMLExportView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_static_html_export",
        responses={(200, "text/html"): bytes, 409: OpenApiResponse(description="Integrity conflict")},
    )
    def get(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _static_export(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
            "html",
        )


class OrganizationRepositoryStaticPDFExportView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_static_pdf_export",
        responses={(200, "application/pdf"): bytes, 409: OpenApiResponse(description="Integrity conflict")},
    )
    def get(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _static_export(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
            "pdf",
        )


class OrganizationRepositoryStaticControlView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_static_control_retrieve",
        responses={200: RepositoryStaticControlSerializer},
    )
    def get(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _static_control(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
        )

    @extend_schema(
        operation_id="repository_evidence_organization_static_control_create",
        request=RepositoryStaticControlWriteSerializer,
        responses={201: RepositoryStaticControlSerializer},
    )
    def post(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _static_control(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
        )


class OrganizationRepositoryStaticDeliveryView(APIView):
    @extend_schema(
        operation_id="repository_evidence_organization_static_delivery_retrieve",
        responses={200: RepositoryStaticDeliverySerializer},
    )
    def get(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _static_delivery(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
        )

    @extend_schema(
        operation_id="repository_evidence_organization_static_delivery_authorize",
        request=RepositoryStaticDeliveryWriteSerializer,
        responses={201: RepositoryStaticDeliverySerializer},
    )
    def post(self, request, organization_entity_id, evidence_id):  # type: ignore[no-untyped-def]
        return _static_delivery(
            request,
            _organization_workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_APPROVE),
            evidence_id,
        )
