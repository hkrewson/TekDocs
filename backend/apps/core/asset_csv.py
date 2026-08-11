from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid5

from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from .inventory import InventoryError, assets_for_scope, create_client_asset, update_hardware_details
from .models import (
    AuditEvent,
    CatalogModel,
    ClientAsset,
    ClientHardwareAsset,
    Entity,
    HardwareAcquisitionMethod,
    HardwareLifecycleState,
    SoftwareInstallationStatus,
)
from .publications import canonical_json
from .scoping import DataScope
from .software_inventory import SoftwareInventoryError, update_installation

SCHEMA_VERSION = "tekdocs.assets.v1"
MAX_FILE_BYTES = 1024 * 1024
MAX_ROWS = 500
MAX_CELL_LENGTH = 500
PREVIEW_MAX_AGE_SECONDS = 15 * 60
PREVIEW_SIGNING_SALT = "tekdocs.asset-csv-preview.v1"

FIELDS = (
    "schema_version",
    "import_key",
    "asset_id",
    "name",
    "kind",
    "model_id",
    "serial_number",
    "asset_tag",
    "lifecycle_state",
    "acquired_on",
    "acquisition_method",
    "acquisition_reference",
    "warranty_provider",
    "warranty_starts_on",
    "warranty_ends_on",
    "warranty_reference",
    "software_status",
    "installed_version",
    "installed_on",
    "last_verified_on",
)

HARDWARE_FIELDS = {
    "serial_number",
    "asset_tag",
    "lifecycle_state",
    "acquired_on",
    "acquisition_method",
    "acquisition_reference",
    "warranty_provider",
    "warranty_starts_on",
    "warranty_ends_on",
    "warranty_reference",
}
SOFTWARE_FIELDS = {"software_status", "installed_version", "installed_on", "last_verified_on"}


class AssetCsvError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ParsedAssetRow:
    number: int
    import_key: str
    asset_id: UUID
    supplied_asset_id: bool
    name: str
    kind: str
    model_id: UUID
    hardware: dict[str, object]
    software: dict[str, object]


def _spreadsheet_safe(value: object) -> str:
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def _decode_spreadsheet_safe(value: str) -> str:
    if value.startswith("'") and (
        value[1:].lstrip().startswith(("=", "+", "-", "@")) or value[1:].startswith(("\t", "\r", "\n"))
    ):
        return value[1:]
    return value


def template_csv() -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\r\n")
    writer.writeheader()
    return output.getvalue().encode("utf-8")


def export_assets_csv(scope: DataScope) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\r\n")
    writer.writeheader()
    for asset in assets_for_scope(scope).order_by("entity__display_name", "entity_id"):
        hardware = getattr(asset, "hardware", None)
        software = getattr(asset, "software_installation", None)
        row: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "import_key": "",
            "asset_id": asset.entity_id,
            "name": asset.entity.display_name,
            "kind": asset.product.kind,
            "model_id": asset.model.entity_id,
        }
        if hardware is not None:
            for field in HARDWARE_FIELDS:
                row[field] = getattr(hardware, field)
        if software is not None:
            row.update(
                {
                    "software_status": software.status,
                    "installed_version": software.installed_version,
                    "installed_on": software.installed_on,
                    "last_verified_on": software.last_verified_on,
                }
            )
        writer.writerow({field: _spreadsheet_safe(row.get(field, "")) for field in FIELDS})
    return output.getvalue().encode("utf-8")


def _read_csv(content: bytes) -> tuple[list[dict[str, str]], str]:
    if not content:
        raise AssetCsvError("Choose a non-empty CSV file.")
    if len(content) > MAX_FILE_BYTES:
        raise AssetCsvError("Asset CSV files may not exceed 1 MiB.")
    if b"\x00" in content:
        raise AssetCsvError("CSV files may not contain null bytes.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AssetCsvError("Asset CSV files must use UTF-8 encoding.") from exc
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = reader.fieldnames or []
        if headers != list(FIELDS):
            raise AssetCsvError("Use the exact TekDocs asset CSV header and column order.")
        rows = list(reader)
    except csv.Error as exc:
        raise AssetCsvError("The CSV structure is malformed.") from exc
    if len(rows) > MAX_ROWS:
        raise AssetCsvError(f"Asset CSV files may contain at most {MAX_ROWS} data rows.")
    if not rows:
        raise AssetCsvError("The asset CSV does not contain any data rows.")
    normalized: list[dict[str, str]] = []
    for row in rows:
        if None in row:
            raise AssetCsvError("CSV rows may not contain extra columns.")
        values = {field: _decode_spreadsheet_safe(value or "") for field, value in row.items()}
        if any(len(value) > MAX_CELL_LENGTH for value in values.values()):
            raise AssetCsvError(f"CSV cells may not exceed {MAX_CELL_LENGTH} characters.")
        normalized.append(values)
    return normalized, hashlib.sha256(content).hexdigest()


def _uuid(value: str, *, field: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a UUID.") from exc


def _date(value: str, *, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD.") from exc


def _identifier(value: str) -> str:
    return " ".join(value.strip().split()).upper()


def _parse_row(row: dict[str, str], number: int, scope: DataScope) -> ParsedAssetRow:
    if row["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}.")
    import_key = row["import_key"].strip()
    supplied_id = bool(row["asset_id"].strip())
    if supplied_id:
        asset_id = _uuid(row["asset_id"].strip(), field="asset_id")
    else:
        if not import_key or len(import_key) > 240:
            raise ValueError("New rows require an import_key of 1 to 240 characters.")
        asset_id = uuid5(scope.workspace_id, import_key)
    name = row["name"].strip()
    if not name or len(name) > 240:
        raise ValueError("name must contain 1 to 240 characters.")
    kind = row["kind"].strip()
    if kind not in {"hardware", "software"}:
        raise ValueError("kind must be hardware or software.")
    model_id = _uuid(row["model_id"].strip(), field="model_id")
    if kind == "hardware" and any(row[field].strip() for field in SOFTWARE_FIELDS):
        raise ValueError("Hardware rows may not contain software fields.")
    if kind == "software" and any(row[field].strip() for field in HARDWARE_FIELDS):
        raise ValueError("Software rows may not contain hardware fields.")
    hardware: dict[str, object] = {}
    software: dict[str, object] = {}
    if kind == "hardware":
        state = row["lifecycle_state"].strip() or HardwareLifecycleState.IN_STOCK
        if state not in set(HardwareLifecycleState.values) - {HardwareLifecycleState.DISPOSED}:
            raise ValueError("lifecycle_state is not supported for CSV import.")
        method = row["acquisition_method"].strip()
        if method and method not in HardwareAcquisitionMethod.values:
            raise ValueError("acquisition_method is not supported.")
        hardware = {
            "serial_number": _identifier(row["serial_number"]),
            "asset_tag": _identifier(row["asset_tag"]),
            "lifecycle_state": state,
            "acquired_on": _date(row["acquired_on"].strip(), field="acquired_on"),
            "acquisition_method": method,
            "acquisition_reference": row["acquisition_reference"].strip(),
            "warranty_provider": row["warranty_provider"].strip(),
            "warranty_starts_on": _date(row["warranty_starts_on"].strip(), field="warranty_starts_on"),
            "warranty_ends_on": _date(row["warranty_ends_on"].strip(), field="warranty_ends_on"),
            "warranty_reference": row["warranty_reference"].strip(),
        }
        limits = {
            "serial_number": 160,
            "asset_tag": 120,
            "acquisition_reference": 240,
            "warranty_provider": 160,
            "warranty_reference": 240,
        }
        for field, limit in limits.items():
            if len(str(hardware[field])) > limit:
                raise ValueError(f"{field} may not exceed {limit} characters.")
        if (
            hardware["warranty_starts_on"]
            and hardware["warranty_ends_on"]
            and hardware["warranty_ends_on"] < hardware["warranty_starts_on"]  # type: ignore[operator]
        ):
            raise ValueError("warranty_ends_on cannot precede warranty_starts_on.")
    else:
        status = row["software_status"].strip() or SoftwareInstallationStatus.PLANNED
        if status not in SoftwareInstallationStatus.values:
            raise ValueError("software_status is not supported.")
        software = {
            "status": status,
            "installed_version": row["installed_version"].strip(),
            "installed_on": _date(row["installed_on"].strip(), field="installed_on"),
            "last_verified_on": _date(row["last_verified_on"].strip(), field="last_verified_on"),
        }
        if len(str(software["installed_version"])) > 160:
            raise ValueError("installed_version may not exceed 160 characters.")
        if status == SoftwareInstallationStatus.INSTALLED and software["installed_on"] is None:
            raise ValueError("installed software requires installed_on.")
    return ParsedAssetRow(number, import_key, asset_id, supplied_id, name, kind, model_id, hardware, software)


def _current_values(asset: ClientAsset, row: ParsedAssetRow) -> tuple[dict[str, object], dict[str, object]]:
    if row.kind == "hardware":
        profile = asset.hardware
        current = {field: getattr(profile, field) for field in row.hardware}
        return current, row.hardware
    installation = asset.software_installation
    current = {field: getattr(installation, field) for field in row.software}
    return current, row.software


def preview_assets_csv(*, scope: DataScope, content: bytes) -> dict[str, Any]:
    raw_rows, source_digest = _read_csv(content)
    rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    seen: set[UUID] = set()
    seen_serials: set[str] = set()
    seen_tags: set[str] = set()
    for number, raw in enumerate(raw_rows, start=2):
        try:
            row = _parse_row(raw, number, scope)
            if row.asset_id in seen:
                raise ValueError("The file targets the same asset more than once.")
            seen.add(row.asset_id)
            asset = assets_for_scope(scope).filter(entity_id=row.asset_id).first()
            if row.supplied_asset_id and asset is None:
                raise ValueError("asset_id is unavailable in this workspace.")
            if asset is not None and asset.model.entity_id != row.model_id:
                raise ValueError("CSV import cannot change retained model provenance.")
            if asset is not None:
                model_kind = asset.product.kind
            else:
                model = CatalogModel.objects.select_related("product", "organization").get(
                    tenant_id=scope.tenant_id,
                    entity_id=row.model_id,
                    archived_at__isnull=True,
                    entity__archived_at__isnull=True,
                    product__archived_at__isnull=True,
                )
                classifications = set(model.organization.classifications.values_list("kind", flat=True))
                if not classifications.intersection({"vendor", "manufacturer"}):
                    raise ValueError("The selected model no longer belongs to an active supplier.")
                model_kind = model.product.kind
            if model_kind != row.kind:
                raise ValueError("kind does not match the selected supplier model.")
            if row.kind == "hardware":
                for field, seen_values in (("serial_number", seen_serials), ("asset_tag", seen_tags)):
                    value = str(row.hardware[field])
                    if not value:
                        continue
                    if value in seen_values:
                        raise ValueError(f"{field} is duplicated within this file.")
                    seen_values.add(value)
                    conflict = (
                        ClientHardwareAsset.scoped.for_scope(scope)
                        .filter(**{field: value})
                        .exclude(asset__entity_id=row.asset_id)
                        .exists()
                    )
                    if conflict:
                        raise ValueError(f"{field} is already used by another asset in this workspace.")
            if asset is None:
                action = "create"
                changes = ["asset"]
            else:
                current, requested = _current_values(asset, row)
                changes = (["name"] if asset.entity.display_name != row.name else []) + [
                    field for field, value in requested.items() if current[field] != value
                ]
                action = "update" if changes else "skip"
                if (
                    row.kind == "software"
                    and asset.software_installation.status == SoftwareInstallationStatus.UNINSTALLED
                    and changes
                ):
                    raise ValueError("Uninstalled software cannot be changed by CSV import.")
            rows.append(
                {
                    "row": number,
                    "asset_id": str(row.asset_id),
                    "name": row.name,
                    "kind": row.kind,
                    "action": action,
                    "changes": changes,
                }
            )
        except (ValueError, CatalogModel.DoesNotExist, ObjectDoesNotExist) as exc:
            message = "The supplier model is unavailable." if isinstance(exc, CatalogModel.DoesNotExist) else str(exc)
            errors.append({"row": number, "message": message})
    action_digest = hashlib.sha256(canonical_json(rows)).hexdigest()
    token = None
    if not errors:
        token = signing.dumps(
            {"workspace_id": str(scope.workspace_id), "source_digest": source_digest, "action_digest": action_digest},
            salt=PREVIEW_SIGNING_SALT,
            compress=True,
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "rows": rows,
        "errors": errors,
        "summary": {
            "total": len(raw_rows),
            "create": sum(item["action"] == "create" for item in rows),
            "update": sum(item["action"] == "update" for item in rows),
            "skip": sum(item["action"] == "skip" for item in rows),
            "errors": len(errors),
        },
        "preview_token": token,
    }


@transaction.atomic
def apply_assets_csv(
    *, scope: DataScope, content: bytes, preview_token: str, actor_id: UUID, tenant: Any, organization: Any
) -> dict[str, int]:
    try:
        signed = signing.loads(preview_token, salt=PREVIEW_SIGNING_SALT, max_age=PREVIEW_MAX_AGE_SECONDS)
    except signing.BadSignature as exc:
        raise AssetCsvError("The CSV preview expired or is invalid. Preview the file again.") from exc
    preview = preview_assets_csv(scope=scope, content=content)
    if preview["errors"] or preview["preview_token"] is None:
        raise AssetCsvError("The CSV no longer passes validation. Preview it again.")
    unsigned = signing.loads(preview["preview_token"], salt=PREVIEW_SIGNING_SALT)
    if signed != unsigned or signed["workspace_id"] != str(scope.workspace_id):
        raise AssetCsvError("The file or workspace changed after preview. Preview the file again.")
    raw_rows, _digest = _read_csv(content)
    counts = {"created": 0, "updated": 0, "skipped": 0}
    for number, raw in enumerate(raw_rows, start=2):
        row = _parse_row(raw, number, scope)
        asset = assets_for_scope(scope).select_for_update(of=("self",)).filter(entity_id=row.asset_id).first()
        if asset is None:
            asset = create_client_asset(
                tenant=tenant,
                organization=organization,
                actor_id=actor_id,
                model_entity_id=row.model_id,
                name=row.name,
                entity_id=row.asset_id,
            )
            if row.kind == "hardware" and any(
                value not in ("", None, HardwareLifecycleState.IN_STOCK) for value in row.hardware.values()
            ):
                update_hardware_details(asset=asset, actor_id=actor_id, values=dict(row.hardware))
            elif row.kind == "software" and any(
                value not in ("", None, SoftwareInstallationStatus.PLANNED) for value in row.software.values()
            ):
                update_installation(asset=asset, actor_id=actor_id, values=dict(row.software))
            counts["created"] += 1
            continue
        current, requested = _current_values(asset, row)
        name_changed = asset.entity.display_name != row.name
        detail_changes = {field: value for field, value in requested.items() if current[field] != value}
        if not name_changed and not detail_changes:
            counts["skipped"] += 1
            continue
        if name_changed:
            Entity.objects.filter(pk=asset.entity_id).update(display_name=row.name)
            AuditEvent.objects.create(
                tenant_id=scope.tenant_id,
                actor_id=actor_id,
                action="asset.renamed",
                entity_id=asset.entity_id,
                metadata={},
            )
        try:
            if row.kind == "hardware" and detail_changes:
                update_hardware_details(asset=asset, actor_id=actor_id, values=detail_changes)
            elif detail_changes:
                update_installation(asset=asset, actor_id=actor_id, values=detail_changes)
        except (InventoryError, SoftwareInventoryError) as exc:
            raise AssetCsvError(f"Row {number}: {exc}") from exc
        counts["updated"] += 1
    return counts
