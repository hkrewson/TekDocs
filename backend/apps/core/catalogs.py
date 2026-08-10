from __future__ import annotations

import hashlib
import json
import re
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
    CatalogModel,
    CatalogModelRevision,
    CatalogProduct,
    CatalogProductDocument,
    CatalogSpecificationDefinition,
    CatalogSpecificationDefinitionVersion,
    Entity,
    EntityVisibility,
    Organization,
    OrganizationKind,
    Tenant,
    workspace_for_owner,
)
from .scoping import DataScope

SUPPLIER_CLASSIFICATIONS = frozenset({OrganizationKind.VENDOR, OrganizationKind.MANUFACTURER})
SCHEMA_MAX_BYTES = 32_768
SCHEMA_MAX_PROPERTIES = 100
ROOT_SCHEMA_KEYS = frozenset(
    {"$schema", "type", "additionalProperties", "properties", "required", "title", "description"}
)
PROPERTY_SCHEMA_KEYS = frozenset(
    {"type", "title", "description", "enum", "items", "minimum", "maximum", "minLength", "maxLength", "uniqueItems"}
)
SPECIFICATION_KEY = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


class CatalogError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StaleCatalogRevision(CatalogError):
    current_revision: CatalogModelRevision

    def __str__(self) -> str:
        return "The model changed after this edit began."


def require_supplier(organization: Organization) -> None:
    kinds = set(organization.classifications.values_list("kind", flat=True))
    if not kinds.intersection(SUPPLIER_CLASSIFICATIONS):
        raise CatalogError("Product catalogs require a vendor or manufacturer workspace.")


def _canonical_checksum(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_property_schema(key: str, schema: Any) -> None:
    if not SPECIFICATION_KEY.fullmatch(key):
        raise CatalogError(
            "Specification keys must start with a letter and use lowercase letters, numbers, or underscores."
        )
    if not isinstance(schema, dict) or set(schema) - PROPERTY_SCHEMA_KEYS:
        raise CatalogError(f"Specification {key} uses an unsupported schema keyword.")
    value_type = schema.get("type")
    if value_type not in {"string", "integer", "number", "boolean", "array"}:
        raise CatalogError(f"Specification {key} uses an unsupported value type.")
    if any(len(str(schema.get(field, ""))) > limit for field, limit in (("title", 160), ("description", 500))):
        raise CatalogError(f"Specification {key} has oversized presentation text.")
    if "enum" in schema:
        options = schema["enum"]
        if value_type != "string" or not isinstance(options, list) or not 1 <= len(options) <= 100:
            raise CatalogError(f"Specification {key} has an invalid choice list.")
        if any(not isinstance(option, str) or not option or len(option) > 160 for option in options):
            raise CatalogError(f"Specification {key} has an invalid choice.")
        if len(set(options)) != len(options):
            raise CatalogError(f"Specification {key} has duplicate choices.")
    if value_type == "array":
        items = schema.get("items")
        if not isinstance(items, dict) or set(items) - {"type", "enum"} or items.get("type") != "string":
            raise CatalogError(f"Specification {key} must use a bounded string-array item schema.")
        options = items.get("enum")
        if options is not None and (
            not isinstance(options, list)
            or not 1 <= len(options) <= 100
            or any(not isinstance(option, str) or not option or len(option) > 160 for option in options)
            or len(set(options)) != len(options)
        ):
            raise CatalogError(f"Specification {key} has an invalid array choice list.")
    elif "items" in schema or "uniqueItems" in schema:
        raise CatalogError(f"Specification {key} uses array rules for a non-array value.")


def validate_specification_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        raise CatalogError("The specification schema must be an object.")
    if len(json.dumps(schema, ensure_ascii=False).encode("utf-8")) > SCHEMA_MAX_BYTES:
        raise CatalogError("The specification schema is too large.")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise CatalogError("The specification schema must be a closed object.")
    if set(schema) - ROOT_SCHEMA_KEYS:
        raise CatalogError("The specification schema uses an unsupported root keyword.")
    properties = schema.get("properties")
    if not isinstance(properties, dict) or len(properties) > SCHEMA_MAX_PROPERTIES:
        raise CatalogError("The specification schema must contain at most 100 named properties.")
    required = schema.get("required", [])
    if not isinstance(required, list) or any(not isinstance(key, str) or key not in properties for key in required):
        raise CatalogError("Every required specification must name a declared property.")
    for key, property_schema in properties.items():
        _validate_property_schema(key, property_schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise CatalogError("The specification schema is not valid Draft 2020-12 JSON Schema.") from exc
    return schema


def validate_specifications(*, schema: dict[str, Any], values: Any) -> dict[str, Any]:
    if not isinstance(values, dict):
        raise CatalogError("Specifications must be an object.")
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(values)
    except JSONSchemaValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path)
        raise CatalogError(f"{path + ': ' if path else ''}{exc.message}") from exc
    return values


def products_for_scope(scope: DataScope, *, query: str = "", kind: str = "") -> QuerySet[CatalogProduct]:
    records = (
        CatalogProduct.scoped.for_scope(scope)
        .filter(archived_at__isnull=True, entity__archived_at__isnull=True)
        .select_related("entity", "organization")
        .prefetch_related(
            Prefetch(
                "models",
                queryset=CatalogModel.objects.filter(archived_at__isnull=True, entity__archived_at__isnull=True)
                .select_related("entity")
                .prefetch_related(
                    Prefetch(
                        "revisions",
                        queryset=CatalogModelRevision.objects.select_related(
                            "specification_version", "specification_version__definition", "created_by"
                        ).order_by("revision"),
                    )
                ),
            ),
            Prefetch(
                "document_associations",
                queryset=CatalogProductDocument.objects.filter(archived_at__isnull=True).select_related(
                    "model", "model__entity", "publication", "publication__entity", "publication__document__entity"
                ),
            ),
        )
    )
    if query:
        records = records.filter(
            Q(entity__display_name__icontains=query)
            | Q(description__icontains=query)
            | Q(models__model_number__icontains=query)
            | Q(models__entity__display_name__icontains=query)
        ).distinct()
    if kind:
        records = records.filter(kind=kind)
    return records.order_by("entity__display_name", "entity_id")


def definitions_for_scope(scope: DataScope) -> QuerySet[CatalogSpecificationDefinition]:
    return (
        CatalogSpecificationDefinition.scoped.for_scope(scope)
        .filter(archived_at__isnull=True)
        .prefetch_related(
            Prefetch(
                "versions",
                queryset=CatalogSpecificationDefinitionVersion.objects.select_related("created_by").order_by("version"),
            )
        )
        .order_by("name", "id")
    )


@transaction.atomic
def create_product(
    *, tenant: Tenant, organization: Organization, actor_id: UUID, name: str, kind: str, description: str
) -> CatalogProduct:
    require_supplier(organization)
    entity = Entity.objects.create(
        tenant=tenant,
        workspace=workspace_for_owner(tenant=tenant, organization=organization),
        organization=organization,
        entity_type="catalog_product",
        display_name=name,
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    product = CatalogProduct.objects.create(
        tenant=tenant, organization=organization, entity=entity, kind=kind, description=description
    )
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="catalog.product.created", entity_id=entity.id, metadata={}
    )
    return product


@transaction.atomic
def update_product(*, product: CatalogProduct, actor_id: UUID, name: str, description: str) -> CatalogProduct:
    locked = CatalogProduct.objects.select_for_update().select_related("entity").get(pk=product.pk)
    locked.entity.display_name = name
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.description = description
    locked.save(update_fields=("description", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="catalog.product.updated",
        entity_id=locked.entity_id,
        metadata={},
    )
    return locked


@transaction.atomic
def archive_product(*, product: CatalogProduct, actor_id: UUID) -> None:
    locked = CatalogProduct.objects.select_for_update().select_related("entity").get(pk=product.pk)
    archived_at = timezone.now()
    locked.archived_at = archived_at
    locked.save(update_fields=("archived_at", "updated_at"))
    locked.entity.archived_at = archived_at
    locked.entity.save(update_fields=("archived_at", "updated_at"))
    for model in (
        CatalogModel.objects.select_for_update()
        .filter(product=locked, archived_at__isnull=True)
        .select_related("entity")
    ):
        model.archived_at = archived_at
        model.save(update_fields=("archived_at", "updated_at"))
        model.entity.archived_at = archived_at
        model.entity.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="catalog.product.archived",
        entity_id=locked.entity_id,
        metadata={},
    )


def _create_definition_version(
    *, definition: CatalogSpecificationDefinition, actor_id: UUID, version: int, schema: dict[str, Any]
) -> CatalogSpecificationDefinitionVersion:
    validated = validate_specification_schema(schema)
    return CatalogSpecificationDefinitionVersion.objects.create(
        tenant=definition.tenant,
        organization=definition.organization,
        definition=definition,
        version=version,
        schema=validated,
        checksum=_canonical_checksum(validated),
        created_by_id=actor_id,
    )


@transaction.atomic
def create_definition(
    *, tenant: Tenant, organization: Organization, actor_id: UUID, name: str, product_kind: str, schema: dict[str, Any]
) -> CatalogSpecificationDefinition:
    require_supplier(organization)
    definition = CatalogSpecificationDefinition.objects.create(
        tenant=tenant, organization=organization, name=name, product_kind=product_kind
    )
    _create_definition_version(definition=definition, actor_id=actor_id, version=1, schema=schema)
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="catalog.specification_definition.created", metadata={}
    )
    return definition


@transaction.atomic
def create_definition_version(
    *, definition: CatalogSpecificationDefinition, actor_id: UUID, schema: dict[str, Any]
) -> CatalogSpecificationDefinitionVersion:
    locked = CatalogSpecificationDefinition.objects.select_for_update().get(pk=definition.pk)
    if locked.archived_at is not None:
        raise CatalogError("Archived specification definitions cannot receive versions.")
    current = CatalogSpecificationDefinitionVersion.objects.filter(definition=locked).order_by("-version").first()
    version = _create_definition_version(
        definition=locked, actor_id=actor_id, version=(current.version + 1 if current else 1), schema=schema
    )
    AuditEvent.objects.create(
        tenant=locked.tenant, actor_id=actor_id, action="catalog.specification_definition.versioned", metadata={}
    )
    return version


def _revision_payload(
    *, lifecycle: str, specifications: dict[str, Any], notes: str, definition_version_id: UUID
) -> dict[str, Any]:
    return {
        "lifecycle": lifecycle,
        "specifications": specifications,
        "notes": notes,
        "specification_version_id": str(definition_version_id),
    }


@transaction.atomic
def create_model(
    *,
    product: CatalogProduct,
    actor_id: UUID,
    name: str,
    model_number: str,
    specification_version: CatalogSpecificationDefinitionVersion,
    lifecycle: str,
    specifications: dict[str, Any],
    notes: str,
) -> CatalogModel:
    locked_product = CatalogProduct.objects.select_for_update().select_related("organization").get(pk=product.pk)
    if locked_product.archived_at is not None:
        raise CatalogError("Archived products cannot receive models.")
    if (
        specification_version.tenant_id != locked_product.tenant_id
        or specification_version.organization_id != locked_product.organization_id
        or specification_version.definition.product_kind != locked_product.kind
    ):
        raise CatalogError("The specification definition does not apply to this product.")
    values = validate_specifications(schema=specification_version.schema, values=specifications)
    entity = Entity.objects.create(
        tenant=locked_product.tenant,
        workspace=locked_product.entity.workspace,
        organization=locked_product.organization,
        entity_type="catalog_model",
        display_name=name,
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    model = CatalogModel.objects.create(
        tenant=locked_product.tenant,
        organization=locked_product.organization,
        entity=entity,
        product=locked_product,
        model_number=model_number,
    )
    payload = _revision_payload(
        lifecycle=lifecycle,
        specifications=values,
        notes=notes,
        definition_version_id=specification_version.id,
    )
    CatalogModelRevision.objects.create(
        tenant=model.tenant,
        organization=model.organization,
        model=model,
        revision=1,
        specification_version=specification_version,
        lifecycle=lifecycle,
        specifications=values,
        notes=notes,
        checksum=_canonical_checksum(payload),
        created_by_id=actor_id,
    )
    AuditEvent.objects.create(
        tenant=model.tenant, actor_id=actor_id, action="catalog.model.created", entity_id=entity.id, metadata={}
    )
    return model


@transaction.atomic
def revise_model(
    *,
    model: CatalogModel,
    actor_id: UUID,
    base_revision_id: UUID,
    name: str,
    model_number: str,
    specification_version: CatalogSpecificationDefinitionVersion,
    lifecycle: str,
    specifications: dict[str, Any],
    notes: str,
) -> CatalogModelRevision:
    locked = CatalogModel.objects.select_for_update().select_related("entity", "product").get(pk=model.pk)
    current = CatalogModelRevision.objects.filter(model=locked).order_by("-revision").first()
    if current is None:
        raise CatalogError("The model has no current revision.")
    if current.id != base_revision_id:
        raise StaleCatalogRevision(current)
    if (
        specification_version.tenant_id != locked.tenant_id
        or specification_version.organization_id != locked.organization_id
        or specification_version.definition.product_kind != locked.product.kind
    ):
        raise CatalogError("The specification definition does not apply to this model.")
    values = validate_specifications(schema=specification_version.schema, values=specifications)
    locked.entity.display_name = name
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.model_number = model_number
    locked.save(update_fields=("model_number", "updated_at"))
    payload = _revision_payload(
        lifecycle=lifecycle,
        specifications=values,
        notes=notes,
        definition_version_id=specification_version.id,
    )
    revision = CatalogModelRevision.objects.create(
        tenant=locked.tenant,
        organization=locked.organization,
        model=locked,
        parent=current,
        revision=current.revision + 1,
        specification_version=specification_version,
        lifecycle=lifecycle,
        specifications=values,
        notes=notes,
        checksum=_canonical_checksum(payload),
        created_by_id=actor_id,
    )
    AuditEvent.objects.create(
        tenant=locked.tenant, actor_id=actor_id, action="catalog.model.revised", entity_id=locked.entity_id, metadata={}
    )
    return revision


@transaction.atomic
def archive_model(*, model: CatalogModel, actor_id: UUID) -> None:
    locked = CatalogModel.objects.select_for_update().select_related("entity").get(pk=model.pk)
    archived_at = timezone.now()
    locked.archived_at = archived_at
    locked.save(update_fields=("archived_at", "updated_at"))
    locked.entity.archived_at = archived_at
    locked.entity.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="catalog.model.archived",
        entity_id=locked.entity_id,
        metadata={},
    )
