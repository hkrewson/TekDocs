from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError

from .models import (
    AuditEvent,
    CustomFieldDefinition,
    CustomFieldDefinitionVersion,
    CustomFieldType,
    Entity,
    Organization,
    Tenant,
)
from .scoping import DataScope

SUPPORTED_ENTITY_TYPES = ("organization", "person", "site", "location")
ORGANIZATION_OWNED_ENTITY_TYPES = ("site", "location")


class CustomFieldConfigurationError(ValueError):
    pass


class CustomFieldValueError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MigrationImpact:
    total: int
    compatible: int
    incompatible: int


def build_schema(*, field_type: str, options: list[str]) -> dict[str, Any]:
    if field_type == CustomFieldType.TEXT:
        schema: dict[str, Any] = {"type": "string", "maxLength": 5000}
    elif field_type == CustomFieldType.INTEGER:
        schema = {"type": "integer"}
    elif field_type == CustomFieldType.NUMBER:
        schema = {"type": "number"}
    elif field_type == CustomFieldType.BOOLEAN:
        schema = {"type": "boolean"}
    elif field_type == CustomFieldType.DATE:
        schema = {"type": "string", "format": "date"}
    elif field_type == CustomFieldType.URL:
        schema = {"type": "string", "format": "uri", "pattern": "^https?://"}
    elif field_type == CustomFieldType.EMAIL:
        schema = {"type": "string", "format": "email"}
    elif field_type == CustomFieldType.CHOICE:
        schema = {"type": "string", "enum": options}
    elif field_type == CustomFieldType.MULTI_CHOICE:
        schema = {"type": "array", "items": {"type": "string", "enum": options}, "uniqueItems": True}
    else:
        raise CustomFieldConfigurationError("Unsupported custom-field type.")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise CustomFieldConfigurationError("The generated validation schema is invalid.") from exc
    return schema


def validate_custom_field_value(*, schema: dict[str, Any], value: Any) -> None:
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
    except JSONSchemaValidationError as exc:
        raise CustomFieldValueError(exc.message) from exc


def definition_versions_queryset(tenant: Tenant | UUID) -> QuerySet[CustomFieldDefinitionVersion]:
    return CustomFieldDefinitionVersion.scoped.for_tenant(tenant).order_by("version")


def definitions_for_scope(*, scope: DataScope, include_archived: bool = False) -> QuerySet[CustomFieldDefinition]:
    records = CustomFieldDefinition.scoped.for_tenant(scope.tenant_id)
    if scope.organization_id is None:
        records = records.filter(organization__isnull=True)
    else:
        records = records.filter(Q(organization__isnull=True) | Q(organization_id=scope.organization_id))
    if not include_archived:
        records = records.filter(archived_at__isnull=True)
    return records.select_related("organization", "organization__entity").prefetch_related(
        Prefetch("versions", queryset=definition_versions_queryset(scope.tenant_id))
    )


def owned_definitions_for_scope(*, scope: DataScope, include_archived: bool = False) -> QuerySet[CustomFieldDefinition]:
    records = CustomFieldDefinition.scoped.for_tenant(scope.tenant_id)
    if scope.organization_id is None:
        records = records.filter(organization__isnull=True)
    else:
        records = records.filter(organization_id=scope.organization_id)
    if not include_archived:
        records = records.filter(archived_at__isnull=True)
    return records.select_related("organization", "organization__entity").prefetch_related(
        Prefetch("versions", queryset=definition_versions_queryset(scope.tenant_id))
    )


def latest_version(definition: CustomFieldDefinition) -> CustomFieldDefinitionVersion:
    versions = list(definition.versions.all())
    if not versions:
        raise CustomFieldConfigurationError("Custom-field definition has no versions.")
    return max(versions, key=lambda item: item.version)


def _create_version(
    *,
    definition: CustomFieldDefinition,
    version: int,
    actor_id: UUID,
    label: str,
    description: str,
    required: bool,
    field_type: str,
    display_order: int,
    options: list[str],
) -> CustomFieldDefinitionVersion:
    return CustomFieldDefinitionVersion.objects.create(
        tenant=definition.tenant,
        definition=definition,
        version=version,
        label=label,
        description=description,
        required=required,
        field_type=field_type,
        schema=build_schema(field_type=field_type, options=options),
        display_order=display_order,
        created_by_id=actor_id,
    )


@transaction.atomic
def create_definition(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    key: str,
    entity_type: str,
    label: str,
    description: str,
    required: bool,
    field_type: str,
    display_order: int,
    options: list[str],
) -> CustomFieldDefinition:
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        raise CustomFieldConfigurationError("Unsupported target record type.")
    if organization is not None and entity_type not in ORGANIZATION_OWNED_ENTITY_TYPES:
        raise CustomFieldConfigurationError("Organization fields currently support Site and Location records.")
    definition = CustomFieldDefinition.objects.create(
        tenant=tenant,
        organization=organization,
        key=key,
        entity_type=entity_type,
    )
    _create_version(
        definition=definition,
        version=1,
        actor_id=actor_id,
        label=label,
        description=description,
        required=required,
        field_type=field_type,
        display_order=display_order,
        options=options,
    )
    AuditEvent.objects.create(
        tenant=tenant,
        actor_id=actor_id,
        action="custom_field.definition.created",
        metadata={},
    )
    return owned_definitions_for_scope(scope=DataScope.owner(tenant, organization)).get(id=definition.id)


def _definition_values(definition: CustomFieldDefinition) -> list[Any]:
    key = str(definition.id)
    entities = Entity.scoped.for_tenant(definition.tenant_id).filter(
        entity_type=definition.entity_type,
        custom_fields__has_key=key,
    )
    if definition.organization_id is not None:
        entities = entities.filter(organization_id=definition.organization_id)
    values: list[Any] = []
    for custom_fields in entities.values_list("custom_fields", flat=True).iterator():
        envelope = custom_fields.get(key)
        if isinstance(envelope, dict) and "value" in envelope:
            values.append(envelope["value"])
    return values


@transaction.atomic
def create_definition_version(
    *,
    definition: CustomFieldDefinition,
    actor_id: UUID,
    label: str,
    description: str,
    required: bool,
    field_type: str,
    display_order: int,
    options: list[str],
) -> tuple[CustomFieldDefinition, MigrationImpact]:
    locked = CustomFieldDefinition.scoped.for_tenant(definition.tenant_id).select_for_update().get(id=definition.id)
    prior_versions = list(definition_versions_queryset(definition.tenant_id).filter(definition=locked))
    next_version = max((item.version for item in prior_versions), default=0) + 1
    created = _create_version(
        definition=locked,
        version=next_version,
        actor_id=actor_id,
        label=label,
        description=description,
        required=required,
        field_type=field_type,
        display_order=display_order,
        options=options,
    )
    values = _definition_values(locked)
    compatible = 0
    for value in values:
        try:
            validate_custom_field_value(schema=created.schema, value=value)
        except CustomFieldValueError:
            continue
        compatible += 1
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="custom_field.definition.versioned",
        metadata={},
    )
    scope = DataScope.owner(locked.tenant, locked.organization)
    refreshed = owned_definitions_for_scope(scope=scope).get(id=locked.id)
    return refreshed, MigrationImpact(total=len(values), compatible=compatible, incompatible=len(values) - compatible)


@transaction.atomic
def archive_definition(*, definition: CustomFieldDefinition, actor_id: UUID) -> None:
    archived_at = timezone.now()
    CustomFieldDefinition.scoped.for_tenant(definition.tenant_id).filter(id=definition.id).update(
        archived_at=archived_at,
        updated_at=archived_at,
    )
    AuditEvent.objects.create(
        tenant=definition.tenant,
        actor_id=actor_id,
        action="custom_field.definition.archived",
        metadata={},
    )


def entity_for_scope(*, scope: DataScope, entity_id: UUID) -> Entity:
    return Entity.scoped.for_scope(scope).get(id=entity_id, archived_at__isnull=True)


def effective_definitions_for_entity(*, scope: DataScope, entity: Entity) -> list[CustomFieldDefinition]:
    referenced_ids = []
    for key in entity.custom_fields:
        try:
            referenced_ids.append(UUID(key))
        except (TypeError, ValueError):
            continue
    records = definitions_for_scope(scope=scope, include_archived=True).filter(
        entity_type=entity.entity_type,
    )
    records = records.filter(Q(archived_at__isnull=True) | Q(id__in=referenced_ids))
    return sorted(
        records,
        key=lambda item: (latest_version(item).display_order, latest_version(item).label, str(item.id)),
    )


def definition_for_entity(
    *, scope: DataScope, entity: Entity, definition_id: UUID, active_only: bool = True
) -> CustomFieldDefinition:
    records = definitions_for_scope(scope=scope, include_archived=not active_only).filter(
        entity_type=entity.entity_type,
    )
    if active_only:
        records = records.filter(archived_at__isnull=True)
    return records.get(id=definition_id)


@transaction.atomic
def set_entity_value(*, scope: DataScope, entity_id: UUID, definition_id: UUID, value: Any, actor_id: UUID) -> Entity:
    scoped_entity = entity_for_scope(scope=scope, entity_id=entity_id)
    entity = Entity.scoped.for_scope(scope).select_for_update().get(id=scoped_entity.id)
    definition = definition_for_entity(scope=scope, entity=entity, definition_id=definition_id)
    version = latest_version(definition)
    validate_custom_field_value(schema=version.schema, value=value)
    custom_fields = dict(entity.custom_fields)
    custom_fields[str(definition.id)] = {
        "definition_version_id": str(version.id),
        "version": version.version,
        "value": value,
    }
    entity.custom_fields = custom_fields
    entity.save(update_fields=("custom_fields", "updated_at"))
    AuditEvent.objects.create(
        tenant=entity.tenant,
        actor_id=actor_id,
        action="custom_field.value.updated",
        entity_id=entity.id,
        metadata={},
    )
    return entity


@transaction.atomic
def clear_entity_value(*, scope: DataScope, entity_id: UUID, definition_id: UUID, actor_id: UUID) -> Entity:
    scoped_entity = entity_for_scope(scope=scope, entity_id=entity_id)
    entity = Entity.scoped.for_scope(scope).select_for_update().get(id=scoped_entity.id)
    definition = definition_for_entity(scope=scope, entity=entity, definition_id=definition_id, active_only=False)
    custom_fields = dict(entity.custom_fields)
    custom_fields.pop(str(definition.id), None)
    entity.custom_fields = custom_fields
    entity.save(update_fields=("custom_fields", "updated_at"))
    AuditEvent.objects.create(
        tenant=entity.tenant,
        actor_id=actor_id,
        action="custom_field.value.cleared",
        entity_id=entity.id,
        metadata={},
    )
    return entity
