from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.db.models import QuerySet
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import require_installation_owner

from .custom_field_serializers import (
    CustomFieldDefinitionResultSerializer,
    CustomFieldDefinitionSerializer,
    CustomFieldDefinitionVersionResultSerializer,
    CustomFieldDefinitionWriteSerializer,
    CustomFieldValueWriteSerializer,
    CustomFieldVersionWriteSerializer,
    EntityCustomFieldResultSerializer,
    serialize_entity_custom_fields,
)
from .custom_fields import (
    CustomFieldConfigurationError,
    CustomFieldValueError,
    archive_definition,
    clear_entity_value,
    create_definition,
    create_definition_version,
    definitions_for_scope,
    effective_definitions_for_entity,
    latest_version,
    owned_definitions_for_scope,
    set_entity_value,
)
from .models import CustomFieldDefinition, Entity
from .scoping import DataScope
from .workspaces import ResolvedWorkspace, resolve_organization_workspace


def _msp_workspace(request) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    member = require_installation_owner(request.user)
    return ResolvedWorkspace(
        member=member,
        kind="msp",
        id=member.tenant.id,
        name=member.tenant.name,
        data_scope=DataScope.tenant(member.tenant),
        classifications=(),
        capabilities=("custom_fields",),
    )


def _organization_workspace(request, organization_entity_id: UUID) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    return resolve_organization_workspace(request.user, entity_id=organization_entity_id)


def _definition_context(workspace: ResolvedWorkspace) -> dict[str, object]:
    return {"organization_id": workspace.organization.id if workspace.organization is not None else None}


def _list_definitions(workspace: ResolvedWorkspace) -> Response:
    records = sorted(
        definitions_for_scope(scope=workspace.data_scope),
        key=lambda item: (
            latest_version(item).display_order,
            latest_version(item).label.casefold(),
            str(item.id),
        ),
    )
    payload = {"results": records, "count": len(records)}
    return Response(CustomFieldDefinitionResultSerializer(payload, context=_definition_context(workspace)).data)


def _create_definition(workspace: ResolvedWorkspace, request) -> Response:  # type: ignore[no-untyped-def]
    serializer = CustomFieldDefinitionWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        definition = create_definition(
            tenant=workspace.member.tenant,
            organization=workspace.organization,
            actor_id=request.user.pk,
            **serializer.validated_data,
        )
    except CustomFieldConfigurationError as exc:
        raise serializers.ValidationError({"entity_type": str(exc)}) from exc
    except IntegrityError as exc:
        raise serializers.ValidationError({"key": "That key is already used for this record type and scope."}) from exc
    return Response(
        CustomFieldDefinitionSerializer(definition, context=_definition_context(workspace)).data,
        status=201,
    )


def _owned_definition(workspace: ResolvedWorkspace, definition_id: UUID) -> CustomFieldDefinition:
    return get_object_or_404(owned_definitions_for_scope(scope=workspace.data_scope), id=definition_id)


def _version_definition(workspace: ResolvedWorkspace, definition_id: UUID, request: Request) -> Response:
    definition = _owned_definition(workspace, definition_id)
    serializer = CustomFieldVersionWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        updated, impact = create_definition_version(
            definition=definition,
            actor_id=request.user.pk,
            **serializer.validated_data,
        )
    except CustomFieldConfigurationError as exc:
        raise serializers.ValidationError({"field_type": str(exc)}) from exc
    payload = {
        "definition": updated,
        "migration_impact": {
            "total": impact.total,
            "compatible": impact.compatible,
            "incompatible": impact.incompatible,
        },
    }
    return Response(CustomFieldDefinitionVersionResultSerializer(payload, context=_definition_context(workspace)).data)


def _archive_definition(workspace: ResolvedWorkspace, definition_id: UUID, request: Request) -> Response:
    archive_definition(definition=_owned_definition(workspace, definition_id), actor_id=request.user.pk)
    return Response(status=204)


def _entity_fields(workspace: ResolvedWorkspace, entity_id: UUID) -> Response:
    entity = get_object_or_404(entity_for_scope_query(workspace), id=entity_id)
    definitions = effective_definitions_for_entity(scope=workspace.data_scope, entity=entity)
    data = serialize_entity_custom_fields(
        entity=entity,
        definitions=definitions,
    )
    return Response(EntityCustomFieldResultSerializer(data, context=_definition_context(workspace)).data)


def entity_for_scope_query(workspace: ResolvedWorkspace) -> QuerySet[Entity]:
    return Entity.scoped.for_scope(workspace.data_scope).filter(archived_at__isnull=True)


def _set_entity_field(
    workspace: ResolvedWorkspace,
    entity_id: UUID,
    definition_id: UUID,
    request: Request,
) -> Response:
    serializer = CustomFieldValueWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        set_entity_value(
            scope=workspace.data_scope,
            entity_id=entity_id,
            definition_id=definition_id,
            value=serializer.validated_data["value"],
            actor_id=request.user.pk,
        )
    except (CustomFieldValueError, CustomFieldConfigurationError) as exc:
        raise serializers.ValidationError({"value": str(exc)}) from exc
    except ObjectDoesNotExist as exc:
        raise Http404 from exc
    return _entity_fields(workspace, entity_id)


def _clear_entity_field(
    workspace: ResolvedWorkspace,
    entity_id: UUID,
    definition_id: UUID,
    request: Request,
) -> Response:
    try:
        clear_entity_value(
            scope=workspace.data_scope,
            entity_id=entity_id,
            definition_id=definition_id,
            actor_id=request.user.pk,
        )
    except ObjectDoesNotExist as exc:
        raise Http404 from exc
    return Response(status=204)


class MSPCustomFieldDefinitionListCreateView(APIView):
    @extend_schema(operation_id="custom_fields_msp_list", responses={200: CustomFieldDefinitionResultSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        return _list_definitions(_msp_workspace(request))

    @extend_schema(
        operation_id="custom_fields_msp_create",
        request=CustomFieldDefinitionWriteSerializer,
        responses={201: CustomFieldDefinitionSerializer},
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        return _create_definition(_msp_workspace(request), request)


class MSPCustomFieldDefinitionDetailView(APIView):
    @extend_schema(
        operation_id="custom_fields_msp_version",
        request=CustomFieldVersionWriteSerializer,
        responses={200: CustomFieldDefinitionVersionResultSerializer},
    )
    def patch(self, request, definition_id):  # type: ignore[no-untyped-def]
        return _version_definition(_msp_workspace(request), definition_id, request)

    @extend_schema(operation_id="custom_fields_msp_archive", request=None, responses={204: OpenApiResponse()})
    def delete(self, request, definition_id):  # type: ignore[no-untyped-def]
        return _archive_definition(_msp_workspace(request), definition_id, request)


class OrganizationCustomFieldDefinitionListCreateView(APIView):
    @extend_schema(
        operation_id="custom_fields_organization_list",
        responses={200: CustomFieldDefinitionResultSerializer},
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _list_definitions(_organization_workspace(request, organization_entity_id))

    @extend_schema(
        operation_id="custom_fields_organization_create",
        request=CustomFieldDefinitionWriteSerializer,
        responses={201: CustomFieldDefinitionSerializer},
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _create_definition(_organization_workspace(request, organization_entity_id), request)


class OrganizationCustomFieldDefinitionDetailView(APIView):
    @extend_schema(
        operation_id="custom_fields_organization_version",
        request=CustomFieldVersionWriteSerializer,
        responses={200: CustomFieldDefinitionVersionResultSerializer},
    )
    def patch(self, request, organization_entity_id, definition_id):  # type: ignore[no-untyped-def]
        return _version_definition(_organization_workspace(request, organization_entity_id), definition_id, request)

    @extend_schema(operation_id="custom_fields_organization_archive", request=None, responses={204: OpenApiResponse()})
    def delete(self, request, organization_entity_id, definition_id):  # type: ignore[no-untyped-def]
        return _archive_definition(_organization_workspace(request, organization_entity_id), definition_id, request)


class MSPEntityCustomFieldListView(APIView):
    @extend_schema(operation_id="entity_custom_fields_msp_list", responses={200: EntityCustomFieldResultSerializer})
    def get(self, request, entity_id):  # type: ignore[no-untyped-def]
        return _entity_fields(_msp_workspace(request), entity_id)


class MSPEntityCustomFieldDetailView(APIView):
    @extend_schema(
        operation_id="entity_custom_fields_msp_set",
        request=CustomFieldValueWriteSerializer,
        responses={200: EntityCustomFieldResultSerializer},
    )
    def patch(self, request, entity_id, definition_id):  # type: ignore[no-untyped-def]
        return _set_entity_field(_msp_workspace(request), entity_id, definition_id, request)

    @extend_schema(operation_id="entity_custom_fields_msp_clear", request=None, responses={204: OpenApiResponse()})
    def delete(self, request, entity_id, definition_id):  # type: ignore[no-untyped-def]
        return _clear_entity_field(_msp_workspace(request), entity_id, definition_id, request)


class OrganizationEntityCustomFieldListView(APIView):
    @extend_schema(
        operation_id="entity_custom_fields_organization_list",
        responses={200: EntityCustomFieldResultSerializer},
    )
    def get(self, request, organization_entity_id, entity_id):  # type: ignore[no-untyped-def]
        return _entity_fields(_organization_workspace(request, organization_entity_id), entity_id)


class OrganizationEntityCustomFieldDetailView(APIView):
    @extend_schema(
        operation_id="entity_custom_fields_organization_set",
        request=CustomFieldValueWriteSerializer,
        responses={200: EntityCustomFieldResultSerializer},
    )
    def patch(self, request, organization_entity_id, entity_id, definition_id):  # type: ignore[no-untyped-def]
        return _set_entity_field(
            _organization_workspace(request, organization_entity_id), entity_id, definition_id, request
        )

    @extend_schema(
        operation_id="entity_custom_fields_organization_clear",
        request=None,
        responses={204: OpenApiResponse()},
    )
    def delete(self, request, organization_entity_id, entity_id, definition_id):  # type: ignore[no-untyped-def]
        return _clear_entity_field(
            _organization_workspace(request, organization_entity_id), entity_id, definition_id, request
        )
