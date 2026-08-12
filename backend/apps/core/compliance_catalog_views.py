from __future__ import annotations

from typing import cast
from uuid import UUID

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.utils.serializer_helpers import ReturnDict
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission, require_permission

from .collection_pagination import BoundedCollectionQuerySerializer, paginate
from .compliance_catalogs import (
    ComplianceCatalogError,
    ControlInput,
    create_catalog_version,
    create_framework,
    frameworks_for_scope,
)
from .models import ComplianceFramework
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        if isinstance(data, dict):
            unexpected = set(data) - set(self.fields)
            if unexpected:
                raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class ComplianceControlWriteSerializer(StrictSerializer):
    control_id = serializers.UUIDField(required=False, allow_null=True)
    identifier = serializers.CharField(max_length=100, trim_whitespace=True)
    title = serializers.CharField(max_length=240, trim_whitespace=True)
    description = serializers.CharField(max_length=20_000, allow_blank=True, required=False, default="")
    guidance = serializers.CharField(max_length=20_000, allow_blank=True, required=False, default="")


class ComplianceCatalogWriteSerializer(StrictSerializer):
    version_label = serializers.CharField(max_length=100, trim_whitespace=True)
    description = serializers.CharField(max_length=20_000, allow_blank=True, required=False, default="")
    source_url = serializers.URLField(max_length=500, allow_blank=True, required=False, default="")
    controls = ComplianceControlWriteSerializer(many=True, required=False, default=list, max_length=1_000)

    def control_inputs(self) -> list[ControlInput]:
        return [ControlInput(**value) for value in self.validated_data["controls"]]


class ComplianceFrameworkWriteSerializer(ComplianceCatalogWriteSerializer):
    name = serializers.CharField(max_length=240, trim_whitespace=True)


class ComplianceControlRevisionSerializer(serializers.Serializer):
    control_id = serializers.UUIDField(source="control.entity_id")
    revision_number = serializers.IntegerField()
    identifier = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    guidance = serializers.CharField()
    content_digest = serializers.CharField()
    created_at = serializers.DateTimeField()


class ComplianceCatalogEntrySerializer(serializers.Serializer):
    position = serializers.IntegerField()
    control = ComplianceControlRevisionSerializer(source="control_revision")


class ComplianceCatalogRevisionSerializer(serializers.Serializer):
    revision_number = serializers.IntegerField()
    version_label = serializers.CharField()
    description = serializers.CharField()
    source_url = serializers.URLField()
    content_digest = serializers.CharField()
    created_at = serializers.DateTimeField()
    created_by = serializers.CharField(source="created_by.display_name")
    entries = ComplianceCatalogEntrySerializer(many=True)


class ComplianceFrameworkSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    current_revision = ComplianceCatalogRevisionSerializer()
    revision_count = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()

    def get_revision_count(self, framework: ComplianceFramework) -> int:
        return len(framework.revisions.all())

    def get_can_manage(self, framework: ComplianceFramework) -> bool:
        workspace = self.context["workspace"]
        return context_has_permission(
            workspace.member, PermissionKey.COMPLIANCE_EDIT, organization=workspace.organization
        )


class ComplianceFrameworkResultSerializer(serializers.Serializer):
    results = ComplianceFrameworkSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    can_manage = serializers.BooleanField()


class ComplianceFrameworkQuerySerializer(BoundedCollectionQuerySerializer):
    q = serializers.CharField(max_length=240, required=False, allow_blank=True, trim_whitespace=True, default="")


def _workspace(request, organization_entity_id: UUID | None, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    workspace = (
        resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        if organization_entity_id is not None
        else resolve_msp_workspace(request.user)
    )
    require_permission(request.user, permission, organization=workspace.organization)
    return workspace


def _records(workspace: ResolvedWorkspace, query: str = "") -> QuerySet[ComplianceFramework]:
    records = frameworks_for_scope(workspace.data_scope)
    return records.filter(entity__display_name__icontains=query) if query else records


def _record(workspace: ResolvedWorkspace, entity_id: UUID) -> ComplianceFramework:
    return get_object_or_404(_records(workspace), entity_id=entity_id)


def _serialize(framework: ComplianceFramework, workspace: ResolvedWorkspace) -> ReturnDict:
    return cast(ReturnDict, ComplianceFrameworkSerializer(framework, context={"workspace": workspace}).data)


class ComplianceFrameworkListCreateView(APIView):
    @extend_schema(
        parameters=[ComplianceFrameworkQuerySerializer],
        responses={200: ComplianceFrameworkResultSerializer},
    )
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.COMPLIANCE_VIEW)
        query = ComplianceFrameworkQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        page = paginate(_records(workspace, values["q"]), page=values["page"], page_size=values["page_size"])
        return Response(
            {
                "results": [_serialize(record, workspace) for record in page.records],
                "page": page.page,
                "page_size": page.page_size,
                "count": page.count,
                "has_more": page.has_more,
                "can_manage": context_has_permission(
                    workspace.member, PermissionKey.COMPLIANCE_EDIT, organization=workspace.organization
                ),
            }
        )

    @extend_schema(
        request=ComplianceFrameworkWriteSerializer,
        responses={201: ComplianceFrameworkSerializer},
    )
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.COMPLIANCE_EDIT)
        serializer = ComplianceFrameworkWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        values.pop("controls", None)
        try:
            framework = create_framework(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                controls=serializer.control_inputs(),
                **values,
            )
        except ComplianceCatalogError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(_serialize(_record(workspace, framework.entity_id), workspace), status=201)


class ComplianceFrameworkDetailView(APIView):
    @extend_schema(responses={200: ComplianceFrameworkSerializer})
    def get(self, request, framework_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.COMPLIANCE_VIEW)
        return Response(_serialize(_record(workspace, framework_entity_id), workspace))


class ComplianceCatalogRevisionListCreateView(APIView):
    @extend_schema(responses={200: ComplianceCatalogRevisionSerializer(many=True)})
    def get(self, request, framework_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.COMPLIANCE_VIEW)
        framework = _record(workspace, framework_entity_id)
        return Response(ComplianceCatalogRevisionSerializer(framework.revisions.all(), many=True).data)

    @extend_schema(
        request=ComplianceCatalogWriteSerializer,
        responses={201: ComplianceCatalogRevisionSerializer},
    )
    def post(self, request, framework_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.COMPLIANCE_EDIT)
        framework = _record(workspace, framework_entity_id)
        serializer = ComplianceCatalogWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        values.pop("controls", None)
        try:
            revision = create_catalog_version(
                framework=framework,
                actor_id=request.user.pk,
                controls=serializer.control_inputs(),
                **values,
            )
        except ComplianceCatalogError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        refreshed = _record(workspace, framework_entity_id)
        created = next(item for item in refreshed.revisions.all() if item.pk == revision.pk)
        return Response(ComplianceCatalogRevisionSerializer(created).data, status=201)


class ComplianceCatalogRevisionDetailView(APIView):
    @extend_schema(responses={200: ComplianceCatalogRevisionSerializer})
    def get(self, request, framework_entity_id, revision_number, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.COMPLIANCE_VIEW)
        framework = _record(workspace, framework_entity_id)
        revision = get_object_or_404(framework.revisions.all(), revision_number=revision_number)
        return Response(ComplianceCatalogRevisionSerializer(revision).data)


@extend_schema_view(
    get=extend_schema(operation_id="msp_compliance_framework_list"),
    post=extend_schema(operation_id="msp_compliance_framework_create"),
)
class MSPComplianceFrameworkListCreateView(ComplianceFrameworkListCreateView):
    pass


@extend_schema_view(get=extend_schema(operation_id="msp_compliance_framework_retrieve"))
class MSPComplianceFrameworkDetailView(ComplianceFrameworkDetailView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="msp_compliance_catalog_revision_list"),
    post=extend_schema(operation_id="msp_compliance_catalog_revision_create"),
)
class MSPComplianceCatalogRevisionListCreateView(ComplianceCatalogRevisionListCreateView):
    pass


@extend_schema_view(get=extend_schema(operation_id="msp_compliance_catalog_revision_retrieve"))
class MSPComplianceCatalogRevisionDetailView(ComplianceCatalogRevisionDetailView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="organization_compliance_framework_list"),
    post=extend_schema(operation_id="organization_compliance_framework_create"),
)
class OrganizationComplianceFrameworkListCreateView(ComplianceFrameworkListCreateView):
    pass


@extend_schema_view(get=extend_schema(operation_id="organization_compliance_framework_retrieve"))
class OrganizationComplianceFrameworkDetailView(ComplianceFrameworkDetailView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="organization_compliance_catalog_revision_list"),
    post=extend_schema(operation_id="organization_compliance_catalog_revision_create"),
)
class OrganizationComplianceCatalogRevisionListCreateView(ComplianceCatalogRevisionListCreateView):
    pass


@extend_schema_view(get=extend_schema(operation_id="organization_compliance_catalog_revision_retrieve"))
class OrganizationComplianceCatalogRevisionDetailView(ComplianceCatalogRevisionDetailView):
    pass
