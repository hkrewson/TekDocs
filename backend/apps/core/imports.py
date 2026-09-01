from __future__ import annotations

import csv
import hashlib
import io
import ipaddress
import json
import re
import time
import zipfile
from collections import Counter
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from .catalogs import create_definition, create_model, create_product, revise_model, update_product
from .credential_references import create_credential_reference, update_credential_reference
from .documents import create_document, update_document
from .inventory import create_client_asset, update_hardware_details
from .models import (
    AuditEvent,
    CatalogModel,
    CatalogModelLifecycle,
    CatalogModelRevision,
    CatalogProduct,
    CatalogProductKind,
    CatalogSpecificationDefinition,
    ClientAsset,
    CredentialReference,
    Document,
    DocumentCategory,
    Entity,
    ImportBatch,
    ImportBatchState,
    ImportExternalKey,
    ImportRow,
    ImportRowAction,
    Location,
    NetworkSubnet,
    NetworkVLAN,
    Organization,
    OrganizationKind,
    PersonAssociation,
    Site,
    SoftwareLicense,
    SoftwareLicenseKind,
    SoftwareLicenseStatus,
    SoftwareRenewalInterval,
)
from .network_addressing import create_subnet, create_vlan, update_subnet
from .organizations import create_organization, update_organization
from .people import create_person, update_person
from .scoping import DataScope
from .sites import create_location, create_site, update_location, update_site
from .software_inventory import create_license, update_license
from .workspaces import ResolvedWorkspace

IMPORT_SCHEMA_VERSION = 1
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_ROWS = 10_000
MAX_ARCHIVE_MEMBERS = 64
MAX_FIELD_BYTES = 64 * 1024
MAX_COLUMNS = 80
STAGING_LIFETIME = timedelta(hours=24)
MAX_PROCESSING_SECONDS = 60
SOURCE_FORMATS = frozenset({"tekdocs_bundle", "tekdocs_csv", "itflow_csv", "itglue_csv", "hudu_csv"})
SOURCE_SYSTEM = {
    "tekdocs_bundle": "tekdocs",
    "tekdocs_csv": "tekdocs",
    "itflow_csv": "itflow",
    "itglue_csv": "itglue",
    "hudu_csv": "hudu",
}
RECORD_TYPES = (
    "organizations",
    "vendors",
    "people",
    "sites",
    "locations",
    "products",
    "models",
    "assets",
    "software_licenses",
    "networks",
    "documents",
    "document_metadata",
    "credential_references",
)
IMPLEMENTED_TYPES = frozenset(RECORD_TYPES)
RECORD_PRIORITY = {record_type: index for index, record_type in enumerate(RECORD_TYPES)}
SECRET_FIELD = re.compile(
    r"(?:password|passwd|secret|api[_ -]?key|private[_ -]?key|recovery|token|credential[_ -]?value)", re.I
)
SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
FORMULA_PREFIXES = ("=", "+", "-", "@")

TEMPLATE_FIELDS: dict[str, tuple[str, ...]] = {
    "organizations": ("external_key", "name", "legal_name", "website", "classification"),
    "vendors": ("external_key", "name", "legal_name", "website", "classification"),
    "people": (
        "external_key",
        "full_name",
        "preferred_name",
        "kind",
        "role",
        "responsibility",
        "phone",
        "email",
        "site_external_key",
        "location_external_key",
    ),
    "sites": (
        "external_key",
        "name",
        "code",
        "address_line_1",
        "address_line_2",
        "city",
        "region",
        "postal_code",
        "country_code",
        "timezone",
        "phone",
    ),
    "locations": ("external_key", "site_external_key", "name", "kind", "code", "parent_external_key"),
    "products": ("external_key", "name", "kind", "description"),
    "models": ("external_key", "product_external_key", "name", "model_number", "lifecycle"),
    "assets": ("external_key", "model_entity_id", "name", "serial_number", "asset_tag"),
    "software_licenses": ("external_key", "asset_external_key", "name", "kind", "status", "seat_limit", "reference"),
    "networks": ("external_key", "name", "cidr", "vlan_id", "description"),
    "documents": ("external_key", "title", "markdown", "category"),
    "document_metadata": ("external_key", "document_external_key", "collection", "tags"),
    "credential_references": ("external_key", "title", "provider", "reference_url"),
}

ALIASES = {
    "id": "external_key",
    "organization_id": "external_key",
    "company_id": "external_key",
    "client_id": "external_key",
    "organization_name": "name",
    "company_name": "name",
    "client_name": "name",
    "primary_email": "email",
    "contact_email": "email",
    "notes": "markdown",
    "content": "markdown",
    "network": "cidr",
    "subnet": "cidr",
    "vault_url": "reference_url",
}


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _safe_filename(name: str) -> str:
    cleaned = "".join(character for character in name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] if ord(character) >= 32)
    return cleaned[:240] or "import"


def _read_upload(upload: Any) -> bytes:
    size = getattr(upload, "size", None)
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise ValidationError({"file": "The import exceeds the 25 MiB upload limit."})
    payload = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValidationError({"file": "The import exceeds the 25 MiB upload limit."})
    if not payload:
        raise ValidationError({"file": "Choose a non-empty import file."})
    return bytes(payload)


def _decode_csv(payload: bytes, *, record_type: str) -> list[dict[str, Any]]:
    if record_type not in TEMPLATE_FIELDS:
        raise ValidationError({"record_type": "Choose a supported CSV record type."})
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError({"file": "CSV imports must be UTF-8 encoded."}) from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames or len(reader.fieldnames) > MAX_COLUMNS:
        raise ValidationError({"file": "The CSV header is missing or exceeds the 80-column limit."})
    normalized_headers = [_normalize_header(header) for header in reader.fieldnames]
    if len(normalized_headers) != len(set(normalized_headers)):
        raise ValidationError({"file": "The CSV contains duplicate or equivalent headers."})
    if any(SECRET_FIELD.search(header) for header in normalized_headers):
        raise ValidationError({"file": "The CSV contains a secret-shaped column that cannot be imported."})
    if set(normalized_headers) - set(TEMPLATE_FIELDS[record_type]):
        raise ValidationError({"file": "The CSV contains unsupported columns. Map it to the downloaded template."})
    rows: list[dict[str, Any]] = []
    for number, source in enumerate(reader, start=2):
        if len(rows) >= MAX_ROWS:
            raise ValidationError({"file": "The import exceeds the 10,000-row limit."})
        normalized = {_normalize_header(key): value for key, value in source.items() if key is not None}
        normalized["record_type"] = record_type
        normalized["_row_number"] = number
        rows.append(normalized)
    return rows


def _decode_bundle(payload: bytes) -> list[dict[str, Any]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ValidationError({"file": "The TekDocs bundle is not a valid ZIP archive."}) from exc
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        raise ValidationError({"file": "The bundle contains too many files."})
    expanded = 0
    member_names = {info.filename.replace("\\", "/") for info in infos if not info.is_dir()}
    if member_names != {"manifest.json", "records.jsonl"}:
        raise ValidationError({"file": "The bundle must contain only manifest.json and records.jsonl."})
    for info in infos:
        if info.is_dir():
            continue
        path = info.filename.replace("\\", "/")
        if path.startswith("/") or ".." in path.split("/") or info.file_size > MAX_EXPANDED_BYTES:
            raise ValidationError({"file": "The bundle contains an unsafe archive path or member."})
        expanded += info.file_size
        if expanded > MAX_EXPANDED_BYTES:
            raise ValidationError({"file": "The expanded bundle exceeds the 100 MiB limit."})
    try:
        manifest = json.loads(archive.read("manifest.json"))
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError({"file": "The bundle requires a valid manifest.json."}) from exc
    if manifest != {"format": "tekdocs-import", "version": IMPORT_SCHEMA_VERSION}:
        raise ValidationError({"file": "Only TekDocs import bundle version 1 is supported."})
    try:
        lines = archive.read("records.jsonl").decode("utf-8").splitlines()
    except (KeyError, UnicodeDecodeError) as exc:
        raise ValidationError({"file": "The bundle requires UTF-8 records.jsonl."}) from exc
    if len(lines) > MAX_ROWS:
        raise ValidationError({"file": "The import exceeds the 10,000-row limit."})
    records: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError({"file": f"records.jsonl line {number} is not valid JSON."}) from exc
        if not isinstance(record, dict):
            raise ValidationError({"file": f"records.jsonl line {number} must be an object."})
        record["_row_number"] = number
        records.append(record)
    return records


def _normalize_header(value: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return ALIASES.get(key, key)


def _text(value: Any, *, maximum: int = 500, required: bool = False) -> str:
    if value is None:
        value = ""
    if isinstance(value, dict | list):
        raise ValueError("field_type_invalid")
    cleaned = " ".join(str(value).split())
    if required and not cleaned:
        raise ValueError("required_field_missing")
    if len(cleaned.encode()) > maximum or any(ord(character) < 32 for character in cleaned):
        raise ValueError("field_length_invalid")
    if cleaned.startswith(FORMULA_PREFIXES):
        raise ValueError("spreadsheet_formula_rejected")
    return cleaned


def _multiline(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("field_type_invalid")
    if len(value.encode()) > MAX_FIELD_BYTES or "\x00" in value:
        raise ValueError("field_length_invalid")
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _tags(value: Any) -> list[str]:
    values = value if isinstance(value, list) else str(value or "").split(",")
    result = []
    for item in values:
        tag = _text(item, maximum=40)
        if tag and tag not in result:
            result.append(tag)
    if len(result) > 20:
        raise ValueError("tag_count_exceeded")
    return result


def _normalize_record(source: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    if any(SECRET_FIELD.search(str(key)) for key in source):
        raise ValueError("secret_field_rejected")
    record_type = _text(source.get("record_type"), maximum=40, required=True).lower()
    if record_type not in RECORD_TYPES:
        raise ValueError("record_type_unsupported")
    if record_type not in IMPLEMENTED_TYPES:
        raise ValueError("record_type_deferred")
    if set(source) - ({"record_type", "external_key"} | set(TEMPLATE_FIELDS[record_type])):
        raise ValueError("record_fields_unsupported")
    external_key = _text(source.get("external_key"), maximum=160, required=True)
    if not SAFE_KEY.fullmatch(external_key):
        raise ValueError("external_key_invalid")
    data: dict[str, Any]
    if record_type in {"organizations", "vendors"}:
        classification = _text(
            source.get("classification") or ("vendor" if record_type == "vendors" else "client"), maximum=32
        ).lower()
        if classification not in OrganizationKind.values:
            raise ValueError("classification_invalid")
        data = {
            "name": _text(source.get("name"), maximum=240, required=True),
            "legal_name": _text(source.get("legal_name"), maximum=240),
            "website": _text(source.get("website"), maximum=500),
            "classification": classification,
        }
    elif record_type == "people":
        kind = _text(source.get("kind") or "contact", maximum=32).lower()
        if kind not in {"employee", "contact"}:
            raise ValueError("person_kind_invalid")
        data = {
            "full_name": _text(source.get("full_name") or source.get("name"), maximum=240, required=True),
            "preferred_name": _text(source.get("preferred_name"), maximum=160),
            "kind": kind,
            "role": _text(source.get("role"), maximum=160),
            "responsibility": _text(source.get("responsibility"), maximum=240),
            "phone": _text(source.get("phone"), maximum=64),
            "email": _text(source.get("email"), maximum=254),
            "site_external_key": _text(source.get("site_external_key"), maximum=160),
            "location_external_key": _text(source.get("location_external_key"), maximum=160),
        }
    elif record_type == "sites":
        country = _text(source.get("country_code"), maximum=2).upper()
        if country and not re.fullmatch(r"[A-Z]{2}", country):
            raise ValueError("country_code_invalid")
        data = {
            key: _text(source.get(key), maximum=240 if key.startswith("address") else 120)
            for key in (
                "code",
                "address_line_1",
                "address_line_2",
                "city",
                "region",
                "postal_code",
                "timezone",
                "phone",
            )
        }
        data.update({"name": _text(source.get("name"), maximum=240, required=True), "country_code": country})
    elif record_type == "locations":
        data = {
            "site_external_key": _text(source.get("site_external_key"), maximum=160, required=True),
            "name": _text(source.get("name"), maximum=240, required=True),
            "kind": _text(source.get("kind") or "room", maximum=40),
            "code": _text(source.get("code"), maximum=80),
            "parent_external_key": _text(source.get("parent_external_key"), maximum=160),
        }
    elif record_type == "products":
        kind = _text(source.get("kind") or CatalogProductKind.HARDWARE, maximum=16).lower()
        if kind not in CatalogProductKind.values:
            raise ValueError("product_kind_invalid")
        data = {
            "name": _text(source.get("name"), maximum=240, required=True),
            "kind": kind,
            "description": _text(source.get("description"), maximum=1000),
        }
    elif record_type == "models":
        lifecycle = _text(source.get("lifecycle") or CatalogModelLifecycle.ACTIVE, maximum=20).lower()
        if lifecycle not in CatalogModelLifecycle.values:
            raise ValueError("model_lifecycle_invalid")
        data = {
            "product_external_key": _text(source.get("product_external_key"), maximum=160, required=True),
            "name": _text(source.get("name"), maximum=240, required=True),
            "model_number": _text(source.get("model_number"), maximum=160, required=True),
            "lifecycle": lifecycle,
        }
    elif record_type == "assets":
        model_entity_id = _text(source.get("model_entity_id"), maximum=36, required=True)
        try:
            model_entity_id = str(UUID(model_entity_id))
        except ValueError as exc:
            raise ValueError("model_entity_id_invalid") from exc
        data = {
            "model_entity_id": model_entity_id,
            "name": _text(source.get("name"), maximum=240, required=True),
            "serial_number": _text(source.get("serial_number"), maximum=160),
            "asset_tag": _text(source.get("asset_tag"), maximum=120),
        }
    elif record_type == "software_licenses":
        kind = _text(source.get("kind") or SoftwareLicenseKind.SUBSCRIPTION, maximum=20).lower()
        status = _text(source.get("status") or SoftwareLicenseStatus.ACTIVE, maximum=20).lower()
        seat_limit = _text(source.get("seat_limit") or "1", maximum=9)
        if kind not in SoftwareLicenseKind.values:
            raise ValueError("license_kind_invalid")
        if status not in SoftwareLicenseStatus.values:
            raise ValueError("license_status_invalid")
        if not seat_limit.isdigit() or not 1 <= int(seat_limit) <= 1_000_000:
            raise ValueError("seat_limit_invalid")
        data = {
            "asset_external_key": _text(source.get("asset_external_key"), maximum=160, required=True),
            "name": _text(source.get("name"), maximum=240, required=True),
            "kind": kind,
            "status": status,
            "seat_limit": int(seat_limit),
            "reference": _text(source.get("reference"), maximum=240),
        }
    elif record_type == "networks":
        cidr = _text(source.get("cidr"), maximum=49, required=True)
        try:
            cidr = ipaddress.ip_network(cidr, strict=True).with_prefixlen
        except ValueError as exc:
            raise ValueError("cidr_invalid") from exc
        vlan = _text(source.get("vlan_id"), maximum=4)
        if vlan and not (vlan.isdigit() and 1 <= int(vlan) <= 4094):
            raise ValueError("vlan_id_invalid")
        data = {
            "name": _text(source.get("name") or cidr, maximum=240),
            "cidr": cidr,
            "vlan_id": int(vlan) if vlan else None,
            "description": _text(source.get("description"), maximum=1000),
        }
    elif record_type == "documents":
        category = _text(source.get("category") or DocumentCategory.GENERAL, maximum=20).lower()
        if category not in DocumentCategory.values:
            raise ValueError("document_category_invalid")
        data = {
            "title": _text(source.get("title") or source.get("name"), maximum=240, required=True),
            "markdown": _multiline(source.get("markdown", "")),
            "category": category,
        }
    elif record_type == "document_metadata":
        data = {
            "document_external_key": _text(source.get("document_external_key"), maximum=160, required=True),
            "collection": _text(source.get("collection"), maximum=120),
            "tags": _tags(source.get("tags")),
        }
    else:
        provider = _text(source.get("provider") or "onepassword", maximum=32).lower()
        if provider != "onepassword":
            raise ValueError("credential_provider_unsupported")
        data = {
            "title": _text(source.get("title") or source.get("name"), maximum=240, required=True),
            "provider": provider,
            "reference_url": _text(source.get("reference_url"), maximum=1000, required=True),
        }
    return record_type, external_key, data


def template_csv(record_type: str) -> bytes:
    if record_type not in TEMPLATE_FIELDS:
        raise NotFound("That import template is unavailable.")
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerow(TEMPLATE_FIELDS[record_type])
    return output.getvalue().encode()


def batches_for_workspace(workspace: ResolvedWorkspace):  # type: ignore[no-untyped-def]
    return ImportBatch.scoped.for_scope(workspace.data_scope).filter(workspace=workspace.data_scope.workspace_id)


def _mapping(
    workspace: ResolvedWorkspace, source_system: str, record_type: str, external_key: str
) -> ImportExternalKey | None:
    return (
        ImportExternalKey.scoped.for_scope(workspace.data_scope)
        .filter(
            workspace=workspace.data_scope.workspace_id,
            source_system=source_system,
            record_type=record_type,
            external_key=external_key,
        )
        .select_related("local_entity")
        .first()
    )


@transaction.atomic
def create_preview(
    *, workspace: ResolvedWorkspace, actor_id: UUID, upload: Any, source_format: str, record_type: str = ""
) -> ImportBatch:
    deadline = time.monotonic() + MAX_PROCESSING_SECONDS
    if source_format not in SOURCE_FORMATS:
        raise ValidationError({"source_format": "Select a supported import format."})
    payload = _read_upload(upload)
    records = (
        _decode_bundle(payload) if source_format == "tekdocs_bundle" else _decode_csv(payload, record_type=record_type)
    )
    source_system = SOURCE_SYSTEM[source_format]
    normalized_rows: list[dict[str, Any]] = []
    keys: list[tuple[str, str]] = []
    for index, source in enumerate(records, start=1):
        if time.monotonic() > deadline:
            raise ValidationError({"file": "The import exceeded the 60-second preview limit."})
        number = int(source.pop("_row_number", index))
        try:
            kind, key, data = _normalize_record(source)
            normalized_rows.append(
                {
                    "row_number": number,
                    "record_type": kind,
                    "external_key": key,
                    "normalized_data": data,
                    "fingerprint": _digest(data),
                    "action": "",
                    "reason_code": "",
                    "local_entity": None,
                }
            )
            keys.append((kind, key))
        except (ValueError, TypeError) as exc:
            reason = str(exc) if str(exc) else "row_invalid"
            fallback = _text(source.get("record_type") or "unknown", maximum=40) or "unknown"
            key = _text(source.get("external_key") or f"row-{number}", maximum=160)
            normalized_rows.append(
                {
                    "row_number": number,
                    "record_type": fallback,
                    "external_key": key,
                    "normalized_data": {},
                    "fingerprint": _digest({}),
                    "action": ImportRowAction.REJECTED,
                    "reason_code": reason[:64],
                    "local_entity": None,
                }
            )
    duplicates = {item for item, count in Counter(keys).items() if count > 1}
    if workspace.organization is None:
        disallowed = {"products", "models", "assets", "software_licenses"}
    else:
        classifications = set(workspace.organization.classifications.values_list("kind", flat=True))
        disallowed = {"organizations", "vendors"}
        if not classifications.intersection({OrganizationKind.VENDOR, OrganizationKind.MANUFACTURER}):
            disallowed.update({"products", "models"})
        if OrganizationKind.CLIENT not in classifications:
            disallowed.update({"assets", "software_licenses"})
    for row in normalized_rows:
        if row["action"]:
            continue
        identity = (row["record_type"], row["external_key"])
        if identity in duplicates:
            row.update(action=ImportRowAction.CONFLICT, reason_code="duplicate_external_key")
            continue
        if row["record_type"] in disallowed:
            row.update(action=ImportRowAction.REJECTED, reason_code="record_type_wrong_workspace")
            continue
        mapping = _mapping(workspace, source_system, *identity)
        if mapping is None:
            if row["record_type"] == "people" and workspace.organization is not None:
                associations = (
                    PersonAssociation.scoped.for_scope(workspace.data_scope)
                    .filter(
                        archived_at__isnull=True,
                        person__entity__archived_at__isnull=True,
                        person__entity__display_name=_display_name(row["record_type"], row["normalized_data"]),
                    )
                    .select_related("person__entity")[:2]
                )
                matches = [association.person.entity for association in associations]
            else:
                possible = Entity.scoped.for_scope(workspace.data_scope).filter(
                    workspace=workspace.data_scope.workspace_id,
                    entity_type=_entity_type(row["record_type"]),
                    display_name=_display_name(row["record_type"], row["normalized_data"]),
                    archived_at__isnull=True,
                )[:2]
                matches = list(possible)
            if len(matches) == 1:
                row.update(
                    action=ImportRowAction.CONFLICT,
                    reason_code="possible_match_requires_confirmation",
                    local_entity=matches[0],
                )
            else:
                row["action"] = ImportRowAction.CREATE
        elif mapping.local_entity.archived_at is not None:
            row.update(
                action=ImportRowAction.CONFLICT, reason_code="mapped_record_archived", local_entity=mapping.local_entity
            )
        elif mapping.last_fingerprint == row["fingerprint"]:
            row.update(action=ImportRowAction.UNCHANGED, local_entity=mapping.local_entity)
        else:
            row.update(action=ImportRowAction.UPDATE, local_entity=mapping.local_entity)
    counts = Counter(str(row["action"]) for row in normalized_rows)
    batch = ImportBatch.objects.create(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        source_format=source_format,
        schema_version=IMPORT_SCHEMA_VERSION,
        source_filename=_safe_filename(getattr(upload, "name", "import")),
        source_digest=hashlib.sha256(payload).hexdigest(),
        result_counts={key: counts.get(key, 0) for key in ImportRowAction.values},
        created_by_id=actor_id,
        expires_at=timezone.now() + STAGING_LIFETIME,
    )
    ImportRow.objects.bulk_create(
        [
            ImportRow(
                tenant=batch.tenant, workspace=batch.workspace, organization=batch.organization, batch=batch, **row
            )
            for row in normalized_rows
        ]
    )
    AuditEvent.objects.create(
        tenant=batch.tenant,
        actor_id=actor_id,
        action="import.preview_created",
        entity_id=batch.id,
        metadata={"rows": len(normalized_rows), "source_format": source_format},
    )
    return batch


def _entity_type(record_type: str) -> str:
    return {
        "organizations": "organization",
        "vendors": "organization",
        "people": "person",
        "sites": "site",
        "locations": "location",
        "products": "catalog_product",
        "models": "catalog_model",
        "assets": "client_asset",
        "software_licenses": "software_license",
        "networks": "network_subnet",
        "documents": "document",
        "document_metadata": "document",
        "credential_references": "credential_reference",
    }.get(record_type, record_type.rstrip("s"))


def _display_name(record_type: str, data: dict[str, Any]) -> str:
    return str(data.get("name") or data.get("full_name") or data.get("title") or data.get("cidr") or "")


def _linked_entity(batch: ImportBatch, record_type: str, external_key: str) -> Entity | None:
    source_system = SOURCE_SYSTEM[batch.source_format]
    mapping = (
        ImportExternalKey.objects.filter(
            tenant=batch.tenant,
            workspace=batch.workspace,
            source_system=source_system,
            record_type=record_type,
            external_key=external_key,
        )
        .select_related("local_entity")
        .first()
    )
    return mapping.local_entity if mapping else None


def _apply_row(batch: ImportBatch, row: ImportRow, actor_id: UUID) -> Entity:
    data = dict(row.normalized_data)
    current = row.local_entity
    organization = batch.organization
    tenant = batch.tenant
    scope = DataScope.owner(tenant, organization)
    if row.record_type in {"organizations", "vendors"}:
        classifications = [data["classification"]]
        if current is None:
            return create_organization(
                tenant=tenant,
                actor_id=actor_id,
                name=data["name"],
                legal_name=data["legal_name"],
                website=data["website"],
                classifications=classifications,
            ).entity
        record = Organization.objects.select_related("entity").get(tenant=tenant, entity=current)
        return update_organization(
            organization=record,
            actor_id=actor_id,
            name=data["name"],
            legal_name=data["legal_name"],
            website=data["website"],
            classifications=classifications,
        ).entity
    if row.record_type == "sites":
        values = {
            key: data[key]
            for key in (
                "name",
                "code",
                "address_line_1",
                "address_line_2",
                "city",
                "region",
                "postal_code",
                "country_code",
                "timezone",
                "phone",
            )
        }
        if current is None:
            return create_site(tenant=tenant, organization=organization, actor_id=actor_id, **values).entity
        return update_site(
            site=Site.objects.select_related("entity").get(entity=current), actor_id=actor_id, **values
        ).entity
    if row.record_type == "locations":
        site_entity = _linked_entity(batch, "sites", data["site_external_key"])
        if site_entity is None:
            raise ValueError("site_dependency_missing")
        site = Site.objects.get(entity=site_entity, tenant=tenant, organization=organization)
        parent_entity = (
            _linked_entity(batch, "locations", data["parent_external_key"]) if data["parent_external_key"] else None
        )
        values = {
            "scope": scope,
            "site": site,
            "actor_id": actor_id,
            "name": data["name"],
            "kind": data["kind"],
            "code": data["code"],
            "parent_id": parent_entity.id if parent_entity else None,
        }
        if current is None:
            return create_location(**values).entity
        values.pop("site")
        return update_location(
            location=Location.objects.select_related("entity", "site").get(entity=current), **values
        ).entity
    if row.record_type == "people":
        site_entity = _linked_entity(batch, "sites", data["site_external_key"]) if data["site_external_key"] else None
        location_entity = (
            _linked_entity(batch, "locations", data["location_external_key"]) if data["location_external_key"] else None
        )
        people_site = Site.objects.get(entity=site_entity) if site_entity else None
        people_location = Location.objects.get(entity=location_entity) if location_entity else None
        values = {
            "actor_id": actor_id,
            "full_name": data["full_name"],
            "preferred_name": data["preferred_name"],
            "kind": data["kind"],
            "role": data["role"],
            "responsibility": data["responsibility"],
            "location": "",
            "office": "",
            "site": people_site,
            "structured_location": people_location,
            "phone": data["phone"],
            "email": data["email"],
        }
        if current is None:
            return create_person(tenant=tenant, organization=organization, **values).person.entity
        return update_person(
            association=PersonAssociation.objects.select_related("person", "person__entity").get(
                person__entity=current, organization=organization
            ),
            **values,
        ).person.entity
    if row.record_type == "products":
        if organization is None:
            raise ValueError("supplier_workspace_required")
        if current is None:
            return create_product(
                tenant=tenant,
                organization=organization,
                actor_id=actor_id,
                name=data["name"],
                kind=data["kind"],
                description=data["description"],
            ).entity
        product = CatalogProduct.objects.select_related("entity").get(entity=current, organization=organization)
        if product.kind != data["kind"]:
            raise ValueError("product_kind_change_unsupported")
        return update_product(
            product=product,
            actor_id=actor_id,
            name=data["name"],
            description=data["description"],
        ).entity
    if row.record_type == "models":
        if organization is None:
            raise ValueError("supplier_workspace_required")
        product_entity = _linked_entity(batch, "products", data["product_external_key"])
        if product_entity is None:
            raise ValueError("product_dependency_missing")
        product = CatalogProduct.objects.select_related("entity").get(
            entity=product_entity, organization=organization
        )
        definition = (
            CatalogSpecificationDefinition.objects.filter(
                tenant=tenant,
                organization=organization,
                name="Imported specifications",
                product_kind=product.kind,
                archived_at__isnull=True,
            )
            .prefetch_related("versions")
            .first()
        )
        if definition is None:
            definition = create_definition(
                tenant=tenant,
                organization=organization,
                actor_id=actor_id,
                name="Imported specifications",
                product_kind=product.kind,
                schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            )
        specification_version = definition.versions.order_by("-version").first()
        if specification_version is None:
            raise ValueError("specification_definition_invalid")
        if current is None:
            return create_model(
                product=product,
                actor_id=actor_id,
                name=data["name"],
                model_number=data["model_number"],
                specification_version=specification_version,
                lifecycle=data["lifecycle"],
                specifications={},
                notes="Imported through the TekDocs reconciliation framework.",
            ).entity
        model = CatalogModel.objects.select_related("entity", "product").get(entity=current, organization=organization)
        if model.product_id != product.id:
            raise ValueError("model_product_change_unsupported")
        revision = CatalogModelRevision.objects.filter(model=model).order_by("-revision").first()
        if revision is None:
            raise ValueError("model_revision_missing")
        revise_model(
            model=model,
            actor_id=actor_id,
            base_revision_id=revision.id,
            name=data["name"],
            model_number=data["model_number"],
            specification_version=specification_version,
            lifecycle=data["lifecycle"],
            specifications={},
            notes="Imported through the TekDocs reconciliation framework.",
        )
        return model.entity
    if row.record_type == "assets":
        model_entity_id = UUID(data["model_entity_id"])
        if current is None:
            asset = create_client_asset(
                tenant=tenant,
                organization=organization,
                actor_id=actor_id,
                model_entity_id=model_entity_id,
                name=data["name"],
            )
        else:
            asset = ClientAsset.objects.select_related("entity", "model", "product").get(
                entity=current, tenant=tenant, organization=organization
            )
            if asset.model.entity_id != model_entity_id:
                raise ValueError("asset_provenance_change_unsupported")
            asset.entity.display_name = data["name"]
            asset.entity.save(update_fields=("display_name", "updated_at"))
        if asset.product.kind == CatalogProductKind.HARDWARE:
            update_hardware_details(
                asset=asset,
                actor_id=actor_id,
                values={"serial_number": data["serial_number"], "asset_tag": data["asset_tag"]},
            )
        return asset.entity
    if row.record_type == "software_licenses":
        asset_entity = _linked_entity(batch, "assets", data["asset_external_key"])
        if asset_entity is None:
            raise ValueError("asset_dependency_missing")
        asset = ClientAsset.objects.select_related("entity", "product").get(
            entity=asset_entity, tenant=tenant, organization=organization
        )
        values = {
            "name": data["name"],
            "kind": data["kind"],
            "status": data["status"],
            "seat_limit": data["seat_limit"],
            "starts_on": None,
            "renews_on": None,
            "ends_on": None,
            "renewal_interval": SoftwareRenewalInterval.NONE,
            "auto_renew": False,
            "reference": data["reference"],
        }
        if current is None:
            return create_license(
                tenant=tenant, organization=organization, actor_id=actor_id, asset=asset, values=values
            ).entity
        license_record = SoftwareLicense.objects.select_related("entity").get(
            entity=current, tenant=tenant, organization=organization
        )
        return update_license(license_record=license_record, actor_id=actor_id, values=values).entity
    if row.record_type == "networks":
        vlan = None
        if data["vlan_id"]:
            vlan = NetworkVLAN.scoped.for_scope(scope).filter(vlan_id=data["vlan_id"]).first()
            if vlan is None:
                vlan = create_vlan(
                    tenant=tenant,
                    organization=organization,
                    actor_id=actor_id,
                    name=f"VLAN {data['vlan_id']}",
                    vlan_id=data["vlan_id"],
                    description="Created by import",
                )
        values = {
            "name": data["name"],
            "cidr": data["cidr"],
            "vrf_entity_id": None,
            "vlan_entity_id": vlan.entity_id if vlan else None,
            "description": data["description"],
        }
        if current is None:
            return create_subnet(tenant=tenant, organization=organization, actor_id=actor_id, **values).entity
        return update_subnet(
            record=NetworkSubnet.objects.select_related("entity").get(entity=current), actor_id=actor_id, values=values
        ).entity
    if row.record_type == "documents":
        if current is None:
            return create_document(
                tenant=tenant,
                organization=organization,
                actor_id=actor_id,
                title=data["title"],
                markdown=data["markdown"],
                category=data["category"],
            ).entity
        document = Document.objects.select_related("entity").get(entity=current)
        placement = document.placements.select_related("block__current_revision").get(parent__isnull=True, position=0)
        if placement.block.current_revision_id is None:
            raise ValueError("document_revision_missing")
        update_document(
            document=document,
            actor_id=actor_id,
            title=data["title"],
            markdown=data["markdown"],
            base_revision_id=placement.block.current_revision_id,
            category=data["category"],
            is_template=document.is_template,
            library_visible=document.library_visible,
        )
        return document.entity
    if row.record_type == "document_metadata":
        document_entity = _linked_entity(batch, "documents", data["document_external_key"])
        if document_entity is None:
            raise ValueError("document_dependency_missing")
        document = Document.objects.select_related("entity").get(
            entity=document_entity, tenant=tenant, organization=organization
        )
        document.collection = data["collection"]
        document.tags = data["tags"]
        document.full_clean()
        document.save(update_fields=("collection", "tags", "updated_at"))
        return document.entity
    if row.record_type == "credential_references":
        if current is None:
            return create_credential_reference(
                tenant=tenant,
                organization=organization,
                actor_id=actor_id,
                title=data["title"],
                provider=data["provider"],
                reference_url=data["reference_url"],
            ).entity
        reference = CredentialReference.objects.select_related("entity").get(entity=current)
        return update_credential_reference(
            reference=reference, actor_id=actor_id, title=data["title"], reference_url=data["reference_url"]
        ).entity
    raise ValueError("record_type_deferred")


@transaction.atomic
def apply_batch(
    *, workspace: ResolvedWorkspace, batch_id: UUID, actor_id: UUID, matches: dict[str, str] | None = None
) -> ImportBatch:
    deadline = time.monotonic() + MAX_PROCESSING_SECONDS
    try:
        batch: ImportBatch = batches_for_workspace(workspace).select_for_update().get(pk=batch_id)
    except ImportBatch.DoesNotExist as exc:
        raise NotFound("The import batch is unavailable.") from exc
    if batch.state not in {ImportBatchState.PREVIEW_READY, ImportBatchState.FAILED}:
        raise ValidationError({"batch": "Only a ready or failed import can be applied."})
    if batch.expires_at <= timezone.now():
        raise ValidationError({"batch": "This import preview expired. Upload it again."})
    selected_matches = matches or {}
    rows = list(batch.rows.select_related("local_entity").order_by("row_number"))
    row_ids = {str(row.id) for row in rows}
    if set(selected_matches) - row_ids:
        raise ValidationError({"matches": "A confirmed preview row is unavailable in this import."})
    for row in rows:
        requested = selected_matches.get(str(row.id))
        if requested and not (
            row.action == ImportRowAction.CONFLICT
            and row.reason_code == "possible_match_requires_confirmation"
        ):
            raise ValidationError({"matches": "Only a proposed exact match can be confirmed."})
        if (
            row.action == ImportRowAction.CONFLICT
            and row.reason_code == "possible_match_requires_confirmation"
            and requested
        ):
            try:
                requested_id = UUID(requested)
                if row.record_type == "people" and workspace.organization is not None:
                    association = PersonAssociation.scoped.for_scope(workspace.data_scope).select_related(
                        "person__entity"
                    ).get(
                        person__entity_id=requested_id,
                        person__entity__archived_at__isnull=True,
                        archived_at__isnull=True,
                    )
                    entity = association.person.entity
                else:
                    entity = Entity.scoped.for_scope(workspace.data_scope).get(
                        pk=requested_id,
                        workspace=batch.workspace,
                        archived_at__isnull=True,
                        entity_type=_entity_type(row.record_type),
                    )
            except (ValueError, Entity.DoesNotExist, PersonAssociation.DoesNotExist) as exc:
                raise ValidationError({"matches": "A confirmed match is unavailable in this Workspace."}) from exc
            row.local_entity = entity
            row.action = ImportRowAction.UPDATE
            row.reason_code = "operator_confirmed_match"
            row.save(update_fields=("local_entity", "action", "reason_code"))
    unresolved = [row for row in rows if row.action in {ImportRowAction.CONFLICT, ImportRowAction.REJECTED}]
    if unresolved:
        raise ValidationError({"batch": "Resolve or remove every conflict before applying this import."})
    batch.state = ImportBatchState.APPLYING
    batch.last_error_code = ""
    batch.save(update_fields=("state", "last_error_code"))
    source_system = SOURCE_SYSTEM[batch.source_format]
    counts: Counter[str] = Counter()
    for row in sorted(rows, key=lambda item: (RECORD_PRIORITY.get(item.record_type, 999), item.row_number)):
        if time.monotonic() > deadline:
            raise ValidationError({"batch": "The import exceeded the 60-second apply limit. Split the source."})
        if row.action == ImportRowAction.UNCHANGED:
            counts[row.action] += 1
            continue
        try:
            entity = _apply_row(batch, row, actor_id)
        except (ValueError, DjangoValidationError) as exc:
            raise ValidationError(
                {"batch": f"Apply stopped at row {row.row_number} because normalized data failed validation."}
            ) from exc
        ImportExternalKey.objects.update_or_create(
            workspace=batch.workspace,
            source_system=source_system,
            record_type=row.record_type,
            external_key=row.external_key,
            defaults={
                "tenant": batch.tenant,
                "organization": batch.organization,
                "local_entity": entity,
                "last_fingerprint": row.fingerprint,
            },
        )
        row.local_entity = entity
        row.save(update_fields=("local_entity",))
        counts[row.action] += 1
    batch.state = ImportBatchState.APPLIED
    batch.applied_at = timezone.now()
    batch.result_counts = {key: counts.get(key, 0) for key in ImportRowAction.values}
    batch.save(update_fields=("state", "applied_at", "result_counts"))
    batch.rows.update(normalized_data={})
    AuditEvent.objects.create(
        tenant=batch.tenant,
        actor_id=actor_id,
        action="import.applied",
        entity_id=batch.id,
        metadata={"rows": len(rows)},
    )
    return batch


@transaction.atomic
def cancel_batch(*, workspace: ResolvedWorkspace, batch_id: UUID, actor_id: UUID) -> ImportBatch:
    try:
        batch: ImportBatch = batches_for_workspace(workspace).select_for_update().get(pk=batch_id)
    except ImportBatch.DoesNotExist as exc:
        raise NotFound("The import batch is unavailable.") from exc
    if batch.state not in {ImportBatchState.PREVIEW_READY, ImportBatchState.FAILED}:
        raise ValidationError({"batch": "Only a pending import can be cancelled."})
    batch.state = ImportBatchState.CANCELLED
    batch.save(update_fields=("state",))
    batch.rows.update(normalized_data={})
    AuditEvent.objects.create(
        tenant=batch.tenant, actor_id=actor_id, action="import.cancelled", entity_id=batch.id, metadata={}
    )
    return batch


def result_report(batch: ImportBatch) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("row_number", "record_type", "external_key", "action", "reason_code", "local_entity_id"))
    for row in batch.rows.order_by("row_number"):
        values = (
            row.row_number,
            row.record_type,
            row.external_key,
            row.action,
            row.reason_code,
            str(row.local_entity_id or ""),
        )
        writer.writerow(
            tuple(
                f"'{value}" if isinstance(value, str) and value.startswith(FORMULA_PREFIXES) else value
                for value in values
            )
        )
    return output.getvalue().encode()


def purge_expired_import_staging(*, now: Any = None) -> int:
    now = now or timezone.now()
    return ImportRow.objects.filter(batch__expires_at__lte=now).exclude(normalized_data={}).update(normalized_data={})
