from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from apps.accounts.policy import PermissionKey


class CapabilityStatus(StrEnum):
    SUPPORTED = "supported"
    EXPERIMENTAL = "experimental"
    EXCLUDED = "excluded"


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    label: str
    path: str
    status: CapabilityStatus
    permission: PermissionKey


CAPABILITY_REGISTRY: dict[str, CapabilityDefinition] = {
    "overview": CapabilityDefinition(
        "Overview", "/overview", CapabilityStatus.SUPPORTED, PermissionKey.WORKSPACES_VIEW
    ),
    "organizations": CapabilityDefinition(
        "Organizations", "/organizations", CapabilityStatus.SUPPORTED, PermissionKey.ORGANIZATIONS_VIEW
    ),
    "people": CapabilityDefinition("People", "/people", CapabilityStatus.SUPPORTED, PermissionKey.PEOPLE_VIEW),
    "sites": CapabilityDefinition("Sites", "/sites", CapabilityStatus.SUPPORTED, PermissionKey.SITES_VIEW),
    "custom_fields": CapabilityDefinition(
        "Custom fields", "/custom-fields", CapabilityStatus.SUPPORTED, PermissionKey.CUSTOM_FIELDS_VIEW
    ),
    "taxonomies": CapabilityDefinition(
        "Taxonomies", "/taxonomies", CapabilityStatus.SUPPORTED, PermissionKey.CUSTOM_FIELDS_VIEW
    ),
    "documentation": CapabilityDefinition(
        "Documentation", "/documentation", CapabilityStatus.SUPPORTED, PermissionKey.DOCUMENTS_VIEW
    ),
    "files": CapabilityDefinition("Files", "/files", CapabilityStatus.SUPPORTED, PermissionKey.DOCUMENTS_VIEW),
    "assets": CapabilityDefinition("Assets", "/assets", CapabilityStatus.SUPPORTED, PermissionKey.ASSETS_VIEW),
    "licenses": CapabilityDefinition("Licenses", "/licenses", CapabilityStatus.SUPPORTED, PermissionKey.ASSETS_VIEW),
    "networks": CapabilityDefinition("Networks", "/networks", CapabilityStatus.SUPPORTED, PermissionKey.NETWORKS_VIEW),
    "domains": CapabilityDefinition("Domains", "/domains", CapabilityStatus.SUPPORTED, PermissionKey.NETWORKS_VIEW),
    "certificates": CapabilityDefinition(
        "Certificates", "/certificates", CapabilityStatus.SUPPORTED, PermissionKey.NETWORKS_VIEW
    ),
    "credentials": CapabilityDefinition(
        "Credentials", "/credentials", CapabilityStatus.SUPPORTED, PermissionKey.CREDENTIAL_REFERENCES_VIEW
    ),
    "services": CapabilityDefinition(
        "Services", "/services", CapabilityStatus.SUPPORTED, PermissionKey.WORKSPACES_VIEW
    ),
    "vendors": CapabilityDefinition("Vendors", "/vendors", CapabilityStatus.SUPPORTED, PermissionKey.ASSETS_VIEW),
    "products": CapabilityDefinition("Products", "/products", CapabilityStatus.SUPPORTED, PermissionKey.ASSETS_VIEW),
    "compliance": CapabilityDefinition(
        "Compliance", "/compliance", CapabilityStatus.SUPPORTED, PermissionKey.COMPLIANCE_VIEW
    ),
    "deadlines": CapabilityDefinition(
        "Reminders", "/deadlines", CapabilityStatus.SUPPORTED, PermissionKey.DEADLINES_VIEW
    ),
    "activity": CapabilityDefinition("Activity", "/activity", CapabilityStatus.SUPPORTED, PermissionKey.ACTIVITY_VIEW),
    "recycle_bin": CapabilityDefinition(
        "Recycle bin", "/recycle-bin", CapabilityStatus.SUPPORTED, PermissionKey.RECYCLE_BIN_VIEW
    ),
    "integrations": CapabilityDefinition(
        "Integrations", "/integrations", CapabilityStatus.SUPPORTED, PermissionKey.INTEGRATIONS_VIEW
    ),
    "invoices": CapabilityDefinition("Invoices", "/invoices", CapabilityStatus.SUPPORTED, PermissionKey.INVOICES_VIEW),
}

CAPABILITY_PERMISSIONS = {key: definition.permission for key, definition in CAPABILITY_REGISTRY.items()}
SUPPORTED_CAPABILITIES = tuple(CAPABILITY_REGISTRY)
