#!/usr/bin/env python3
"""Validate the plain-language catalog and route review inventory."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "frontend" / "src" / "i18n" / "en-US.json"
CAPABILITIES = ROOT / "frontend" / "src" / "product" / "capabilities.ts"
APP = ROOT / "frontend" / "src" / "App.tsx"
INVENTORY = ROOT / "docs" / "UI_COPY_INVENTORY.json"

VALID_STATUSES = {"pending", "reviewed"}
REQUIRED_AUXILIARY_ROUTES = {
    "*",
    "/access-control",
    "/auth/*",
    "/notification-delivery",
    "/portal",
    "/search",
    "/settings",
    "/staff",
    "/system-status",
    "/workspaces/organizations/:organizationId/overview",
    "/workspaces/organizations/:organizationId/search",
}
PROMOTIONAL_PHRASES = {
    "best-in-class",
    "cutting-edge",
    "effortless",
    "intelligent",
    "powerful",
    "seamless",
    "world-class",
}
INTERNAL_TERMS = {
    "artifact",
    "canonical",
    "payload",
    "projection",
    "provider identity",
    "schema",
    "surface",
}
TECHNICAL_KEY_PREFIXES = ("systemStatus.", "integrations.log")
REPLACED_SHELL_LITERALS = {
    "Available capabilities",
    "Search TekDocs",
    "Staff &amp; invitations",
}
REVIEWED_INFRASTRUCTURE_FILES = {
    ROOT / "frontend" / "src" / "inventory" / "Assets.tsx": {
        "Provenance checksum",
        "Retained specifications",
        "STATIC product documentation",
        "inspect retained provenance",
        "New asset from supplier model",
    },
    ROOT / "frontend" / "src" / "inventory" / "Licenses.tsx": {
        "inspect its entitlement",
        "Revoke seat",
    },
    ROOT / "frontend" / "src" / "credential-references" / "CredentialReferences.tsx": {
        "Credential references",
        "security boundary",
        "hands off",
    },
    ROOT / "frontend" / "src" / "domains" / "Domains.tsx": {
        "Monitoring details",
        "Collection history",
        "monitoring evidence",
    },
    ROOT / "frontend" / "src" / "domains" / "Certificates.tsx": {
        "certificate evidence",
        "monitoring evidence",
    },
    ROOT / "frontend" / "src" / "commercial" / "Contracts.tsx": {
        "commercial records",
        "operational fields",
    },
}
REVIEWED_SUPPLIER_FILES = {
    ROOT / "frontend" / "src" / "inventory" / "Vendors.tsx": {
        "retained asset provenance",
        "derived supplier list",
    },
    ROOT / "frontend" / "src" / "catalog" / "ProductCatalogs.tsx": {
        "Reusable product and model definitions retained",
        "No vendor or manufacturer catalogs are available",
    },
    ROOT / "frontend" / "src" / "catalog" / "Products.tsx": {
        "stable supplier-owned family",
        "Reusable validation contracts",
        "Specifications are validated and retained",
        "STATIC publication",
        "No retained publications",
        "Create revision",
        "Revision notes",
        "Sell price",
    },
}
REVIEWED_INVOICE_FILES = {
    ROOT / "frontend" / "src" / "accounting" / "Invoices.tsx": {
        "window.confirm",
        "Provider event ID",
        "Accounting handoff",
        "Ed25519 signing key",
        " · inclusive",
    },
    ROOT / "frontend" / "src" / "accounting" / "InvoiceSettings.tsx": {
        "['none', 'No date']",
        "['never', 'Never']",
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def object_value(value: Any, name: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{name} must be an object")
    return value


def string_value(value: Any, name: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{name} must be a non-empty string")
    return value.strip()


def string_list(value: Any, name: str) -> list[str]:
    require(isinstance(value, list) and bool(value), f"{name} must be a non-empty list")
    return [string_value(item, f"{name}[{index}]") for index, item in enumerate(value)]


def capability_routes() -> set[str]:
    source = CAPABILITIES.read_text(encoding="utf-8")
    body = source.split("export const capabilityRegistry = {", 1)[1].split("} as const", 1)[0]
    return set(re.findall(r"path: '([^']+)'", body))


def validate_inventory() -> tuple[int, int, int]:
    inventory = object_value(json.loads(INVENTORY.read_text(encoding="utf-8")), "inventory")
    require(inventory.get("schema_version") == 1, "UI copy inventory schema_version must be 1")
    require(inventory.get("issue") == 59, "UI copy inventory must identify issue 59")
    raw_entries = inventory.get("entries")
    require(isinstance(raw_entries, list) and bool(raw_entries), "UI copy inventory entries must be a non-empty list")

    identifiers: set[str] = set()
    covered_routes: set[str] = set()
    reviewed = 0
    for index, raw_entry in enumerate(raw_entries):
        entry = object_value(raw_entry, f"entries[{index}]")
        identifier = string_value(entry.get("id"), f"entries[{index}].id")
        require(identifier not in identifiers, f"duplicate UI copy inventory id: {identifier}")
        identifiers.add(identifier)
        string_value(entry.get("workflow"), f"{identifier}.workflow")
        routes = string_list(entry.get("routes"), f"{identifier}.routes")
        states = string_list(entry.get("states"), f"{identifier}.states")
        require(len(routes) == len(set(routes)), f"{identifier}.routes contains duplicates")
        require(len(states) == len(set(states)), f"{identifier}.states contains duplicates")
        covered_routes.update(routes)
        status = string_value(entry.get("status"), f"{identifier}.status")
        require(status in VALID_STATUSES, f"{identifier}.status must be pending or reviewed")
        decisions = entry.get("decisions")
        require(isinstance(decisions, list), f"{identifier}.decisions must be a list")
        if status == "reviewed":
            reviewed += 1
            require(bool(decisions), f"reviewed inventory entry {identifier} must record copy decisions")
            string_list(entry.get("evidence"), f"{identifier}.evidence")
        else:
            string_value(entry.get("next_review"), f"{identifier}.next_review")
        for decision_index, raw_decision in enumerate(decisions):
            decision = object_value(raw_decision, f"{identifier}.decisions[{decision_index}]")
            before = string_value(decision.get("before"), f"{identifier}.decisions[{decision_index}].before")
            after = string_value(decision.get("after"), f"{identifier}.decisions[{decision_index}].after")
            require(before != after, f"{identifier} decision must change the copy")
            string_value(decision.get("reason"), f"{identifier}.decisions[{decision_index}].reason")

    required_routes = capability_routes() | REQUIRED_AUXILIARY_ROUTES
    missing = sorted(required_routes - covered_routes)
    require(not missing, f"UI copy inventory is missing routes: {', '.join(missing)}")
    return len(raw_entries), reviewed, len(required_routes)


def validate_catalog() -> int:
    catalog = object_value(json.loads(CATALOG.read_text(encoding="utf-8")), "English catalog")
    for key, raw_value in catalog.items():
        value = string_value(raw_value, f"catalog.{key}")
        lowered = value.casefold()
        for phrase in PROMOTIONAL_PHRASES:
            require(phrase not in lowered, f"catalog.{key} contains banned promotional phrase: {phrase}")
        if not key.startswith(TECHNICAL_KEY_PREFIXES):
            for term in INTERNAL_TERMS:
                require(
                    re.search(rf"\b{re.escape(term)}s?\b", lowered) is None,
                    f"catalog.{key} exposes internal term outside a technical view: {term}",
                )
    return len(catalog)


def validate_shell_migration() -> None:
    source = APP.read_text(encoding="utf-8")
    remaining = sorted(literal for literal in REPLACED_SHELL_LITERALS if literal in source)
    require(not remaining, f"reviewed shell copy returned as raw JSX: {', '.join(remaining)}")
    for message_id in (
        "navigation.open",
        "navigation.close",
        "navigation.pageUnavailable",
        "shell.accountMenu",
        "shell.search",
    ):
        require(f"translate('{message_id}'" in source, f"App shell must use catalog message {message_id}")


def validate_infrastructure_migration() -> None:
    for source_path, replaced_literals in REVIEWED_INFRASTRUCTURE_FILES.items():
        source = source_path.read_text(encoding="utf-8")
        remaining = sorted(literal for literal in replaced_literals if literal in source)
        require(
            not remaining,
            f"reviewed infrastructure copy returned in {source_path}: {', '.join(remaining)}",
        )


def validate_supplier_migration() -> None:
    for source_path, replaced_literals in REVIEWED_SUPPLIER_FILES.items():
        source = source_path.read_text(encoding="utf-8")
        remaining = sorted(literal for literal in replaced_literals if literal in source)
        require(
            not remaining,
            f"reviewed supplier copy returned in {source_path}: {', '.join(remaining)}",
        )


def validate_invoice_migration() -> None:
    for source_path, replaced_literals in REVIEWED_INVOICE_FILES.items():
        source = source_path.read_text(encoding="utf-8")
        remaining = sorted(literal for literal in replaced_literals if literal in source)
        require(
            not remaining,
            f"reviewed invoice copy or confirmation returned in {source_path}: {', '.join(remaining)}",
        )


def main() -> int:
    entries, reviewed, route_count = validate_inventory()
    message_count = validate_catalog()
    validate_shell_migration()
    validate_infrastructure_migration()
    validate_supplier_migration()
    validate_invoice_migration()
    print(
        f"UI language contract passed: {route_count} routes inventoried in {entries} workflow groups, "
        f"{reviewed} reviewed {'group' if reviewed == 1 else 'groups'}, and {message_count} catalog messages checked."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"UI language contract failed: {exc}") from exc
