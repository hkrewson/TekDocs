from __future__ import annotations

from typing import cast
from uuid import UUID

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .collection_pagination import BoundedCollectionQuerySerializer, paginate
from .compliance_evidence import (
    ComplianceEvidenceError,
    EvidenceInput,
    create_evidence,
    evidence_for_scope,
    evidence_links_for_assignment,
    link_evidence,
    review_evidence,
)
from .compliance_operations import assignments_for_scope
from .models import ComplianceControlAssignment, ComplianceEvidence
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        if isinstance(data, dict):
            unexpected = set(data) - set(self.fields)
            if unexpected:
                raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class ComplianceEvidenceWriteSerializer(StrictSerializer):
    title = serializers.CharField(max_length=240, trim_whitespace=True)
    kind = serializers.ChoiceField(choices=("note", "url", "entity"))
    summary = serializers.CharField(max_length=20_000, allow_blank=True, required=False, default="")
    source_url = serializers.URLField(max_length=500, allow_blank=True, required=False, default="")
    source_entity_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    collection_start = serializers.DateField(required=False, allow_null=True, default=None)
    collection_end = serializers.DateField(required=False, allow_null=True, default=None)


class ComplianceEvidenceReviewWriteSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=("collected", "accepted", "rejected", "expired"))
    decision = serializers.CharField(max_length=120, trim_whitespace=True)
    note = serializers.CharField(max_length=20_000, allow_blank=True, required=False, default="")


class ComplianceEvidenceLinkWriteSerializer(StrictSerializer):
    evidence_id = serializers.UUIDField()


class ComplianceEvidenceReviewSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    decision = serializers.CharField()
    note = serializers.CharField()
    reviewed_by = serializers.CharField(source="reviewed_by.display_name")
    reviewed_at = serializers.DateTimeField()


class ComplianceEvidenceControlLinkSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    assignment_id = serializers.UUIDField()
    control_id = serializers.UUIDField(source="assignment.control.entity_id")
    control_revision = serializers.IntegerField(source="control_revision.revision_number")
    linked_by = serializers.CharField(source="linked_by.display_name")
    linked_at = serializers.DateTimeField()


class ComplianceEvidenceSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    title = serializers.CharField(source="entity.display_name")
    kind = serializers.CharField()
    summary = serializers.CharField()
    source_url = serializers.URLField()
    source_entity_id = serializers.UUIDField(allow_null=True)
    source_entity_name = serializers.CharField(source="source_entity.display_name", allow_null=True)
    collection_start = serializers.DateField(allow_null=True)
    collection_end = serializers.DateField(allow_null=True)
    created_by = serializers.CharField(source="created_by.display_name")
    created_at = serializers.DateTimeField()
    reviews = ComplianceEvidenceReviewSerializer(many=True)
    control_links = ComplianceEvidenceControlLinkSerializer(many=True)


class ComplianceEvidenceResultSerializer(serializers.Serializer):
    results = ComplianceEvidenceSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()


def _workspace(request, organization_entity_id: UUID | None, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    workspace = (
        resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        if organization_entity_id is not None
        else resolve_msp_workspace(request.user)
    )
    require_permission(request.user, permission, organization=workspace.organization)
    return workspace


def _evidence(workspace: ResolvedWorkspace, entity_id: UUID) -> ComplianceEvidence:
    return cast(
        ComplianceEvidence,
        get_object_or_404(evidence_for_scope(workspace.data_scope), entity_id=entity_id),
    )


def _assignment(workspace: ResolvedWorkspace, assignment_id: UUID) -> ComplianceControlAssignment:
    return cast(
        ComplianceControlAssignment,
        get_object_or_404(assignments_for_scope(workspace.data_scope), pk=assignment_id),
    )


class ComplianceEvidenceListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: ComplianceEvidenceResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.COMPLIANCE_VIEW)
        query = BoundedCollectionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        page = paginate(evidence_for_scope(workspace.data_scope), page=values["page"], page_size=values["page_size"])
        return Response(
            {
                "results": ComplianceEvidenceSerializer(page.records, many=True).data,
                "page": page.page,
                "page_size": page.page_size,
                "count": page.count,
                "has_more": page.has_more,
            }
        )

    @extend_schema(request=ComplianceEvidenceWriteSerializer, responses={201: ComplianceEvidenceSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.COMPLIANCE_EDIT)
        serializer = ComplianceEvidenceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            evidence = create_evidence(
                workspace=workspace,
                actor_id=request.user.pk,
                value=EvidenceInput(**serializer.validated_data),
            )
        except ComplianceEvidenceError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(ComplianceEvidenceSerializer(_evidence(workspace, evidence.entity_id)).data, status=201)


class ComplianceEvidenceReviewView(APIView):
    @extend_schema(request=ComplianceEvidenceReviewWriteSerializer, responses={201: ComplianceEvidenceReviewSerializer})
    def post(self, request, evidence_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.COMPLIANCE_EDIT)
        evidence = _evidence(workspace, evidence_entity_id)
        serializer = ComplianceEvidenceReviewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = review_evidence(evidence=evidence, actor_id=request.user.pk, **serializer.validated_data)
        return Response(ComplianceEvidenceReviewSerializer(review).data, status=201)


class ComplianceAssignmentEvidenceLinkView(APIView):
    @extend_schema(
        request=ComplianceEvidenceLinkWriteSerializer,
        responses={201: ComplianceEvidenceControlLinkSerializer},
    )
    def post(self, request, assignment_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.COMPLIANCE_EDIT)
        assignment = _assignment(workspace, assignment_id)
        serializer = ComplianceEvidenceLinkWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        evidence = _evidence(workspace, serializer.validated_data["evidence_id"])
        try:
            link = link_evidence(assignment=assignment, evidence=evidence, actor_id=request.user.pk)
        except ComplianceEvidenceError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        refreshed = next(item for item in evidence_links_for_assignment(assignment) if item.pk == link.pk)
        return Response(ComplianceEvidenceControlLinkSerializer(refreshed).data, status=201)


@extend_schema_view(
    get=extend_schema(operation_id="msp_compliance_evidence_list"),
    post=extend_schema(operation_id="msp_compliance_evidence_create"),
)
class MSPComplianceEvidenceListCreateView(ComplianceEvidenceListCreateView):
    pass


@extend_schema_view(post=extend_schema(operation_id="msp_compliance_evidence_review"))
class MSPComplianceEvidenceReviewView(ComplianceEvidenceReviewView):
    pass


@extend_schema_view(post=extend_schema(operation_id="msp_compliance_assignment_evidence_link"))
class MSPComplianceAssignmentEvidenceLinkView(ComplianceAssignmentEvidenceLinkView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="organization_compliance_evidence_list"),
    post=extend_schema(operation_id="organization_compliance_evidence_create"),
)
class OrganizationComplianceEvidenceListCreateView(ComplianceEvidenceListCreateView):
    pass


@extend_schema_view(post=extend_schema(operation_id="organization_compliance_evidence_review"))
class OrganizationComplianceEvidenceReviewView(ComplianceEvidenceReviewView):
    pass


@extend_schema_view(post=extend_schema(operation_id="organization_compliance_assignment_evidence_link"))
class OrganizationComplianceAssignmentEvidenceLinkView(ComplianceAssignmentEvidenceLinkView):
    pass
