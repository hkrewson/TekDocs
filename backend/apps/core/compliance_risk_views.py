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
from .compliance_risks import (
    ComplianceRiskError,
    RiskInput,
    create_risk,
    review_risk,
    risk_owner_choices,
    risk_summary,
    risks_for_scope,
)
from .models import ComplianceRisk
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        if isinstance(data, dict):
            unexpected = set(data) - set(self.fields)
            if unexpected:
                raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class ComplianceRiskWriteSerializer(StrictSerializer):
    title = serializers.CharField(max_length=240, trim_whitespace=True)
    description = serializers.CharField(max_length=20_000, allow_blank=True, required=False, default="")
    likelihood = serializers.IntegerField(min_value=1, max_value=5)
    impact = serializers.IntegerField(min_value=1, max_value=5)
    status = serializers.ChoiceField(choices=("open", "monitoring", "accepted", "closed"))
    treatment = serializers.ChoiceField(choices=("mitigate", "avoid", "transfer", "accept"))
    treatment_plan = serializers.CharField(max_length=20_000, allow_blank=True, required=False, default="")
    assignment_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    owner_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    due_date = serializers.DateField(required=False, allow_null=True, default=None)
    decision = serializers.CharField(max_length=120, trim_whitespace=True)
    note = serializers.CharField(max_length=20_000, allow_blank=True, required=False, default="")


class ComplianceRiskEventSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    control_revision = serializers.IntegerField(source="control_revision.revision_number", allow_null=True)
    likelihood = serializers.IntegerField()
    impact = serializers.IntegerField()
    status = serializers.CharField()
    treatment = serializers.CharField()
    treatment_plan = serializers.CharField()
    due_date = serializers.DateField(allow_null=True)
    decision = serializers.CharField()
    note = serializers.CharField()
    recorded_by = serializers.CharField(source="recorded_by.display_name")
    recorded_at = serializers.DateTimeField()


class ComplianceRiskSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    title = serializers.CharField(source="entity.display_name")
    description = serializers.CharField()
    assignment_id = serializers.UUIDField(allow_null=True)
    control = serializers.CharField(source="assignment.control.entity.display_name", allow_null=True)
    likelihood = serializers.IntegerField()
    impact = serializers.IntegerField()
    score = serializers.IntegerField()
    reporting_band = serializers.CharField()
    status = serializers.CharField()
    treatment = serializers.CharField()
    treatment_plan = serializers.CharField()
    owner_id = serializers.UUIDField(allow_null=True)
    owner = serializers.CharField(source="owner.display_name", allow_null=True)
    due_date = serializers.DateField(allow_null=True)
    accepted_by = serializers.CharField(source="accepted_by.display_name", allow_null=True)
    accepted_at = serializers.DateTimeField(allow_null=True)
    events = ComplianceRiskEventSerializer(many=True)


class ComplianceRiskResultSerializer(serializers.Serializer):
    results = ComplianceRiskSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    owner_choices = serializers.ListField(child=serializers.DictField())
    summary = serializers.DictField()


def _workspace(request, organization_entity_id: UUID | None, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    workspace = (
        resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        if organization_entity_id is not None
        else resolve_msp_workspace(request.user)
    )
    require_permission(request.user, permission, organization=workspace.organization)
    return workspace


def _risk(workspace: ResolvedWorkspace, entity_id: UUID) -> ComplianceRisk:
    return cast(ComplianceRisk, get_object_or_404(risks_for_scope(workspace.data_scope), entity_id=entity_id))


class ComplianceRiskListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: ComplianceRiskResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.COMPLIANCE_VIEW)
        query = BoundedCollectionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        page = paginate(risks_for_scope(workspace.data_scope), page=values["page"], page_size=values["page_size"])
        return Response(
            {
                "results": ComplianceRiskSerializer(page.records, many=True).data,
                "page": page.page,
                "page_size": page.page_size,
                "count": page.count,
                "has_more": page.has_more,
                "owner_choices": risk_owner_choices(workspace),
                "summary": risk_summary(workspace.data_scope),
            }
        )

    @extend_schema(request=ComplianceRiskWriteSerializer, responses={201: ComplianceRiskSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.COMPLIANCE_EDIT)
        serializer = ComplianceRiskWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            risk = create_risk(
                workspace=workspace, actor_id=request.user.pk, value=RiskInput(**serializer.validated_data)
            )
        except ComplianceRiskError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(ComplianceRiskSerializer(_risk(workspace, risk.entity_id)).data, status=201)


class ComplianceRiskReviewView(APIView):
    @extend_schema(request=ComplianceRiskWriteSerializer, responses={200: ComplianceRiskSerializer})
    def post(self, request, risk_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.COMPLIANCE_EDIT)
        risk = _risk(workspace, risk_entity_id)
        serializer = ComplianceRiskWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            risk = review_risk(
                risk=risk, workspace=workspace, actor_id=request.user.pk, value=RiskInput(**serializer.validated_data)
            )
        except ComplianceRiskError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(ComplianceRiskSerializer(_risk(workspace, risk.entity_id)).data)


@extend_schema_view(
    get=extend_schema(operation_id="msp_compliance_risk_list"),
    post=extend_schema(operation_id="msp_compliance_risk_create"),
)
class MSPComplianceRiskListCreateView(ComplianceRiskListCreateView):
    pass


@extend_schema_view(post=extend_schema(operation_id="msp_compliance_risk_review"))
class MSPComplianceRiskReviewView(ComplianceRiskReviewView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="organization_compliance_risk_list"),
    post=extend_schema(operation_id="organization_compliance_risk_create"),
)
class OrganizationComplianceRiskListCreateView(ComplianceRiskListCreateView):
    pass


@extend_schema_view(post=extend_schema(operation_id="organization_compliance_risk_review"))
class OrganizationComplianceRiskReviewView(ComplianceRiskReviewView):
    pass
