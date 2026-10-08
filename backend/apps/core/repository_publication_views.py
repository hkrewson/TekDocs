"""Staff-only review entry point for signed repository publication evidence."""

from __future__ import annotations

from typing import cast
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
    PublicationAudience,
    RepositoryEvidenceReviewDecision,
    RepositoryPublicationEvidence,
    WorkspaceRepository,
    workspace_for_owner,
)
from .repository_publication_evidence import (
    RepositoryPublicationEvidenceError,
    retain_repository_publication_evidence,
    verify_repository_publication_evidence,
)
from .repository_publication_render import MAX_RENDERED_PDF_BYTES, verify_retained_pdf_snapshot
from .repository_service import RepositoryServiceError
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
    page = serializers.IntegerField(min_value=1, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False, default=25)


class RepositoryEvidencePageSerializer(serializers.Serializer):
    results = RepositoryEvidenceSummarySerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()


class RepositoryEvidenceReviewSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    content_id = serializers.UUIDField()
    audience = serializers.ChoiceField(choices=PublicationAudience.choices)
    title = serializers.CharField()
    source_commit = serializers.CharField()
    signed_at = serializers.DateTimeField()
    canonical_markdown = serializers.CharField()
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
