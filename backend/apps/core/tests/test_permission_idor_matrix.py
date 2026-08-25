import secrets
import uuid

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.accounts.policy import PERMISSION_BY_KEY
from apps.core.models import InstallationState
from apps.core.permission_inventory import AUTHENTICATED_ROUTE_PERMISSIONS, PUBLIC_API_ROUTE_NAMES


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Matrix MSP",
        owner_email="matrix-owner@example.com",
        owner_display_name="Matrix Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


def _api_route_names():
    pending = [("", get_resolver().url_patterns)]
    names: set[str] = set()
    while pending:
        prefix, patterns = pending.pop()
        for pattern in patterns:
            route_pattern = prefix + str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                pending.append((route_pattern, pattern.url_patterns))
            elif isinstance(pattern, URLPattern) and route_pattern.startswith("api/v1/") and pattern.name:
                names.add(pattern.name)
    return names


def _api_route_methods():
    pending = [("", get_resolver().url_patterns)]
    methods: dict[str, set[str]] = {}
    supported = {"GET", "POST", "PATCH", "PUT", "DELETE"}
    while pending:
        prefix, patterns = pending.pop()
        for pattern in patterns:
            route_pattern = prefix + str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                pending.append((route_pattern, pattern.url_patterns))
            elif isinstance(pattern, URLPattern) and route_pattern.startswith("api/v1/") and pattern.name:
                view_class = getattr(pattern.callback, "view_class", None)
                if view_class is not None:
                    methods[pattern.name] = {method for method in supported if hasattr(view_class, method.lower())}
    return methods


def _kwargs_for(route_name: str) -> dict[str, object]:
    value = uuid.UUID("00000000-0000-4000-8000-000000000001")
    route_kwargs: dict[str, tuple[str, ...]] = {
        "access-collection-detail": ("collection_id",),
        "custom-role-detail": ("role_id",),
        "scoped-role-assignment-detail": ("assignment_id",),
        "access-control-member-role": ("user_id",),
        "access-control-organization-detail": ("organization_entity_id",),
        "access-control-organization-staff": ("organization_entity_id",),
        "access-control-organization-staff-detail": ("organization_entity_id", "user_id"),
        "api-token-rotate": ("token_id",),
        "api-token-revoke": ("token_id",),
        "invitation-revoke": ("invitation_id",),
        "invitation-resend": ("invitation_id",),
        "client-invitation-list-create": ("organization_entity_id",),
        "client-portal-document-detail": ("publication_entity_id",),
        "client-portal-document-artifact-download": ("publication_entity_id", "artifact_entity_id"),
        "client-portal-notification-read": ("notification_id",),
        "notification-read": ("notification_id",),
        "organization-detail": ("entity_id",),
        "msp-entity-relationship-list-create": ("entity_id",),
        "msp-entity-relationship-detail": ("entity_id", "link_id"),
        "msp-relationship-graph-view-detail": ("view_id",),
        "msp-relationship-graph-snapshots": ("view_id",),
        "msp-relationship-graph-snapshot-export": ("snapshot_id", "export_format"),
        "msp-domain-review": ("domain_entity_id",),
        "msp-domain-monitoring": ("domain_entity_id",),
        "msp-certificate-endpoint-list-create": ("domain_entity_id",),
        "msp-certificate-monitoring": ("domain_entity_id", "endpoint_entity_id"),
        "msp-hostname-list-create": ("domain_entity_id",),
        "msp-domain-observation-create": ("hostname_entity_id",),
        "msp-person-detail": ("person_entity_id",),
        "msp-credential-reference-detail": ("credential_reference_entity_id",),
        "msp-credential-reference-open": ("credential_reference_entity_id",),
        "msp-site-detail": ("site_entity_id",),
        "msp-document-detail": ("document_entity_id",),
        "msp-document-restructure": ("document_entity_id",),
        "msp-document-export": ("document_entity_id",),
        "msp-document-remote-source": ("document_entity_id",),
        "msp-document-key-binding-list-create": ("document_entity_id",),
        "msp-document-key-binding-detail": ("document_entity_id", "binding_id"),
        "msp-document-keys": ("document_entity_id",),
        "msp-document-remote-observations": ("document_entity_id",),
        "msp-document-remote-observation-apply": ("document_entity_id", "observation_id"),
        "msp-document-attachment-list-create": ("document_entity_id",),
        "msp-document-primary-file": ("document_entity_id",),
        "msp-document-attachment-detail": ("document_entity_id", "attachment_entity_id"),
        "msp-document-attachment-download": ("document_entity_id", "attachment_entity_id"),
        "msp-document-publication-list-create": ("document_entity_id",),
        "msp-document-publication-detail": ("document_entity_id", "publication_entity_id"),
        "msp-document-publication-approve": ("document_entity_id", "publication_entity_id"),
        "msp-document-publication-withdraw": ("document_entity_id", "publication_entity_id"),
        "msp-document-publication-markdown": ("document_entity_id", "publication_entity_id"),
        "msp-document-publication-export": ("document_entity_id", "publication_entity_id"),
        "msp-document-publication-manifest": ("document_entity_id", "publication_entity_id"),
        "msp-document-publication-artifact-download": (
            "document_entity_id",
            "publication_entity_id",
            "artifact_entity_id",
        ),
        "msp-document-revision-list": ("document_entity_id",),
        "msp-document-revision-detail": ("document_entity_id", "revision_id"),
        "msp-document-placement-list-create": ("document_entity_id",),
        "msp-document-placement-detail": ("document_entity_id", "placement_id"),
        "msp-document-placement-reuse": ("document_entity_id", "placement_id"),
        "msp-document-placement-detach": ("document_entity_id", "placement_id"),
        "msp-document-reference-list-create": ("document_entity_id",),
        "msp-document-reference-detail": ("document_entity_id", "reference_id"),
        "msp-location-list-create": ("site_entity_id",),
        "msp-location-detail": ("site_entity_id", "location_entity_id"),
        "msp-custom-field-definition-detail": ("definition_id",),
        "msp-entity-custom-field-list": ("entity_id",),
        "msp-entity-custom-field-detail": ("entity_id", "definition_id"),
        "msp-asset-detail": ("asset_entity_id",),
        "msp-asset-mac-addresses": ("asset_entity_id",),
        "msp-asset-mac-address-detail": ("asset_entity_id", "mac_address_entity_id"),
        "msp-network-detail": ("network_entity_id",),
        "msp-network-rack-detail": ("rack_entity_id",),
        "msp-network-device-detail": ("device_entity_id",),
        "msp-hardware-detail": ("asset_entity_id",),
        "msp-hardware-assignment-choices": ("asset_entity_id",),
        "msp-hardware-assignment": ("asset_entity_id",),
        "msp-hardware-disposal": ("asset_entity_id",),
        "msp-hardware-lifecycle": ("asset_entity_id",),
        "msp-software-detail": ("asset_entity_id",),
        "msp-software-license-detail": ("license_entity_id",),
        "msp-software-license-installation": ("license_entity_id",),
        "msp-software-license-seat": ("license_entity_id",),
        "msp-software-license-seat-detail": ("license_entity_id", "seat_id"),
        "msp-commercial-contract-detail": ("contract_entity_id",),
        "msp-commercial-contract-cost-list-create": ("contract_entity_id",),
        "msp-commercial-contract-cost-detail": ("contract_entity_id", "cost_id"),
        "msp-network-vrf-detail": ("vrf_entity_id",),
        "msp-network-vlan-detail": ("vlan_entity_id",),
        "msp-network-subnet-detail": ("subnet_entity_id",),
        "msp-network-interface-detail": ("interface_entity_id",),
        "msp-network-ip-address-detail": ("ip_address_entity_id",),
        "msp-network-mac-address-detail": ("mac_address_entity_id",),
        "msp-network-wireless-detail": ("wireless_entity_id",),
        "msp-network-dns-zone-detail": ("zone_entity_id",),
        "msp-network-dns-record-detail": ("record_entity_id",),
        "msp-network-circuit-detail": ("circuit_entity_id",),
        "msp-network-circuit-handoffs": ("circuit_entity_id",),
        "msp-network-circuit-handoff-detail": ("circuit_entity_id", "handoff_entity_id"),
        "msp-netbox-reference-detail": ("reference_id",),
        "msp-integration-connection-detail": ("connection_id",),
        "msp-integration-connection-rotate": ("connection_id",),
        "msp-integration-conflict-resolve": ("conflict_id",),
        "msp-git-export-download": ("bundle_id",),
        "msp-compliance-framework-detail": ("framework_entity_id",),
        "msp-compliance-catalog-revision-list-create": ("framework_entity_id",),
        "msp-compliance-catalog-revision-detail": ("framework_entity_id", "revision_number"),
        "msp-compliance-assignment-list": ("framework_entity_id",),
        "msp-compliance-assignment-review": ("framework_entity_id", "control_entity_id"),
        "msp-compliance-evidence-review": ("evidence_entity_id",),
        "msp-data-flow-detail": ("data_flow_entity_id",),
        "msp-data-flow-revisions": ("data_flow_entity_id",),
        "msp-data-flow-snapshot-export": ("snapshot_id", "export_format"),
        "organization-data-flow-snapshots": ("organization_entity_id",),
        "organization-data-flow-snapshot-export": ("organization_entity_id", "snapshot_id", "export_format"),
        "organization-data-flows": ("organization_entity_id",),
        "organization-data-flow-choices": ("organization_entity_id",),
        "organization-data-flow-detail": ("organization_entity_id", "data_flow_entity_id"),
        "organization-data-flow-revisions": ("organization_entity_id", "data_flow_entity_id"),
        "msp-compliance-risk-review": ("risk_entity_id",),
        "msp-compliance-assignment-evidence-link": ("assignment_id",),
        "msp-asset-document-detail": ("asset_entity_id", "publication_entity_id"),
        "msp-asset-document-artifact-download": ("asset_entity_id", "publication_entity_id", "artifact_entity_id"),
        "workspace-organization": ("entity_id",),
        "organization-people-list-create": ("organization_entity_id",),
        "organization-credential-reference-list-create": ("organization_entity_id",),
        "organization-credential-reference-detail": (
            "organization_entity_id",
            "credential_reference_entity_id",
        ),
        "organization-credential-reference-open": (
            "organization_entity_id",
            "credential_reference_entity_id",
        ),
        "organization-integration-connection-detail": ("organization_entity_id", "connection_id"),
        "organization-integration-connection-rotate": ("organization_entity_id", "connection_id"),
        "organization-integration-provider-list": ("organization_entity_id",),
        "organization-integration-connection-list-create": ("organization_entity_id",),
        "organization-integration-job-list-create": ("organization_entity_id",),
        "organization-integration-log-list": ("organization_entity_id",),
        "organization-integration-conflict-list": ("organization_entity_id",),
        "organization-integration-conflict-resolve": ("organization_entity_id", "conflict_id"),
        "organization-git-export-list-create": ("organization_entity_id",),
        "organization-git-export-download": ("organization_entity_id", "bundle_id"),
        "organization-compliance-framework-list-create": ("organization_entity_id",),
        "organization-compliance-framework-detail": ("organization_entity_id", "framework_entity_id"),
        "organization-compliance-catalog-revision-list-create": (
            "organization_entity_id",
            "framework_entity_id",
        ),
        "organization-compliance-catalog-revision-detail": (
            "organization_entity_id",
            "framework_entity_id",
            "revision_number",
        ),
        "organization-compliance-assignment-list": ("organization_entity_id", "framework_entity_id"),
        "organization-compliance-assignment-review": (
            "organization_entity_id",
            "framework_entity_id",
            "control_entity_id",
        ),
        "organization-compliance-evidence-list-create": ("organization_entity_id",),
        "organization-compliance-evidence-review": ("organization_entity_id", "evidence_entity_id"),
        "organization-compliance-assignment-evidence-link": ("organization_entity_id", "assignment_id"),
        "organization-compliance-risk-list-create": ("organization_entity_id",),
        "organization-compliance-risk-review": ("organization_entity_id", "risk_entity_id"),
        "organization-compliance-bundle-list-create": ("organization_entity_id",),
        "organization-reminder-list-create": ("organization_entity_id",),
        "organization-reminder-calendar": ("organization_entity_id",),
        "organization-domain-list-create": ("organization_entity_id",),
        "organization-domain-review": ("organization_entity_id", "domain_entity_id"),
        "organization-domain-monitoring": ("organization_entity_id", "domain_entity_id"),
        "organization-certificate-endpoint-list-create": ("organization_entity_id", "domain_entity_id"),
        "organization-certificate-monitoring": (
            "organization_entity_id",
            "domain_entity_id",
            "endpoint_entity_id",
        ),
        "organization-hostname-list-create": ("organization_entity_id", "domain_entity_id"),
        "organization-domain-observation-create": ("organization_entity_id", "hostname_entity_id"),
        "organization-catalog-product-list-create": ("organization_entity_id",),
        "organization-catalog-product-detail": ("organization_entity_id", "product_entity_id"),
        "organization-catalog-publication-choices": ("organization_entity_id",),
        "organization-catalog-product-document-list-create": (
            "organization_entity_id",
            "product_entity_id",
        ),
        "organization-catalog-product-document-detail": (
            "organization_entity_id",
            "product_entity_id",
            "association_id",
        ),
        "organization-catalog-model-list-create": ("organization_entity_id", "product_entity_id"),
        "organization-catalog-model-detail": (
            "organization_entity_id",
            "product_entity_id",
            "model_entity_id",
        ),
        "organization-catalog-specification-definition-list-create": ("organization_entity_id",),
        "organization-catalog-specification-definition-version-create": (
            "organization_entity_id",
            "definition_id",
        ),
        "organization-client-asset-list-create": ("organization_entity_id",),
        "organization-client-asset-bulk": ("organization_entity_id",),
        "organization-asset-csv-template": ("organization_entity_id",),
        "organization-asset-csv-export": ("organization_entity_id",),
        "organization-asset-csv-preview": ("organization_entity_id",),
        "organization-asset-csv-apply": ("organization_entity_id",),
        "organization-client-asset-model-choices": ("organization_entity_id",),
        "organization-client-asset-detail": ("organization_entity_id", "asset_entity_id"),
        "organization-asset-mac-addresses": ("organization_entity_id", "asset_entity_id"),
        "organization-asset-mac-address-detail": (
            "organization_entity_id",
            "asset_entity_id",
            "mac_address_entity_id",
        ),
        "organization-networks": ("organization_entity_id",),
        "organization-network-detail": ("organization_entity_id", "network_entity_id"),
        "organization-network-choices": ("organization_entity_id",),
        "organization-network-search": ("organization_entity_id",),
        "organization-network-export": ("organization_entity_id",),
        "organization-netbox-reference-list-create": ("organization_entity_id",),
        "organization-netbox-reference-detail": ("organization_entity_id", "reference_id"),
        "organization-netbox-reference-choices": ("organization_entity_id",),
        "organization-netbox-reconcile-preview": ("organization_entity_id",),
        "organization-network-racks": ("organization_entity_id",),
        "organization-network-rack-detail": ("organization_entity_id", "rack_entity_id"),
        "organization-network-devices": ("organization_entity_id",),
        "organization-network-device-detail": ("organization_entity_id", "device_entity_id"),
        "organization-network-vrfs": ("organization_entity_id",),
        "organization-network-vrf-detail": ("organization_entity_id", "vrf_entity_id"),
        "organization-network-vlans": ("organization_entity_id",),
        "organization-network-vlan-detail": ("organization_entity_id", "vlan_entity_id"),
        "organization-network-subnets": ("organization_entity_id",),
        "organization-network-subnet-detail": ("organization_entity_id", "subnet_entity_id"),
        "organization-network-interfaces": ("organization_entity_id",),
        "organization-network-interface-detail": ("organization_entity_id", "interface_entity_id"),
        "organization-network-ip-addresses": ("organization_entity_id",),
        "organization-network-ip-address-detail": ("organization_entity_id", "ip_address_entity_id"),
        "organization-network-mac-addresses": ("organization_entity_id",),
        "organization-network-mac-address-detail": ("organization_entity_id", "mac_address_entity_id"),
        "organization-network-wireless": ("organization_entity_id",),
        "organization-network-wireless-detail": ("organization_entity_id", "wireless_entity_id"),
        "organization-network-dns-zones": ("organization_entity_id",),
        "organization-network-dns-zone-detail": ("organization_entity_id", "zone_entity_id"),
        "organization-network-dns-records": ("organization_entity_id",),
        "organization-network-dns-record-detail": ("organization_entity_id", "record_entity_id"),
        "organization-network-circuits": ("organization_entity_id",),
        "organization-network-circuit-choices": ("organization_entity_id",),
        "organization-network-circuit-detail": ("organization_entity_id", "circuit_entity_id"),
        "organization-network-circuit-handoffs": ("organization_entity_id", "circuit_entity_id"),
        "organization-network-circuit-handoff-detail": (
            "organization_entity_id",
            "circuit_entity_id",
            "handoff_entity_id",
        ),
        "organization-webhook-endpoint-list-create": ("organization_entity_id",),
        "organization-webhook-endpoint-detail": ("organization_entity_id", "endpoint_id"),
        "organization-webhook-endpoint-rotate": ("organization_entity_id", "endpoint_id"),
        "organization-webhook-delivery-list": ("organization_entity_id",),
        "organization-webhook-delivery-retry": ("organization_entity_id", "delivery_id"),
        "inbound-webhook": ("endpoint_id",),
        "organization-client-hardware-detail": ("organization_entity_id", "asset_entity_id"),
        "organization-client-hardware-assignment-choices": (
            "organization_entity_id",
            "asset_entity_id",
        ),
        "organization-client-hardware-assignment": ("organization_entity_id", "asset_entity_id"),
        "organization-client-hardware-disposal": ("organization_entity_id", "asset_entity_id"),
        "organization-client-hardware-lifecycle": ("organization_entity_id", "asset_entity_id"),
        "organization-client-software-detail": ("organization_entity_id", "asset_entity_id"),
        "organization-software-license-list-create": ("organization_entity_id",),
        "organization-software-license-choices": ("organization_entity_id",),
        "organization-software-license-detail": ("organization_entity_id", "license_entity_id"),
        "organization-software-license-installation": ("organization_entity_id", "license_entity_id"),
        "organization-software-license-seat": ("organization_entity_id", "license_entity_id"),
        "organization-software-license-seat-detail": (
            "organization_entity_id",
            "license_entity_id",
            "seat_id",
        ),
        "organization-commercial-contract-list-create": ("organization_entity_id",),
        "organization-commercial-contract-provider-choices": ("organization_entity_id",),
        "organization-commercial-contract-detail": ("organization_entity_id", "contract_entity_id"),
        "organization-commercial-contract-cost-list-create": (
            "organization_entity_id",
            "contract_entity_id",
        ),
        "organization-commercial-contract-cost-detail": (
            "organization_entity_id",
            "contract_entity_id",
            "cost_id",
        ),
        "organization-client-asset-document-detail": (
            "organization_entity_id",
            "asset_entity_id",
            "publication_entity_id",
        ),
        "organization-client-asset-document-artifact-download": (
            "organization_entity_id",
            "asset_entity_id",
            "publication_entity_id",
            "artifact_entity_id",
        ),
        "organization-client-vendor-list": ("organization_entity_id",),
        "organization-person-detail": ("organization_entity_id", "person_entity_id"),
        "organization-site-list-create": ("organization_entity_id",),
        "organization-document-list-create": ("organization_entity_id",),
        "organization-document-detail": ("organization_entity_id", "document_entity_id"),
        "organization-document-restructure": ("organization_entity_id", "document_entity_id"),
        "organization-document-export": ("organization_entity_id", "document_entity_id"),
        "organization-document-attachment-list-create": ("organization_entity_id", "document_entity_id"),
        "organization-document-primary-file": ("organization_entity_id", "document_entity_id"),
        "organization-document-attachment-detail": (
            "organization_entity_id",
            "document_entity_id",
            "attachment_entity_id",
        ),
        "organization-document-attachment-download": (
            "organization_entity_id",
            "document_entity_id",
            "attachment_entity_id",
        ),
        "organization-document-publication-list-create": ("organization_entity_id", "document_entity_id"),
        "organization-document-publication-detail": (
            "organization_entity_id",
            "document_entity_id",
            "publication_entity_id",
        ),
        "organization-document-publication-approve": (
            "organization_entity_id",
            "document_entity_id",
            "publication_entity_id",
        ),
        "organization-document-publication-withdraw": (
            "organization_entity_id",
            "document_entity_id",
            "publication_entity_id",
        ),
        "organization-document-publication-export": (
            "organization_entity_id",
            "document_entity_id",
            "publication_entity_id",
        ),
        "organization-document-publication-markdown": (
            "organization_entity_id",
            "document_entity_id",
            "publication_entity_id",
        ),
        "organization-document-publication-manifest": (
            "organization_entity_id",
            "document_entity_id",
            "publication_entity_id",
        ),
        "organization-document-publication-artifact-download": (
            "organization_entity_id",
            "document_entity_id",
            "publication_entity_id",
            "artifact_entity_id",
        ),
        "organization-document-template-instantiate": ("organization_entity_id",),
        "organization-document-template-library": ("organization_entity_id",),
        "organization-document-template-rollout-preview": ("organization_entity_id",),
        "organization-document-template-rollout-apply": ("organization_entity_id",),
        "organization-document-import": ("organization_entity_id",),
        "organization-document-file-backed-create": ("organization_entity_id",),
        "organization-document-block-library": ("organization_entity_id",),
        "organization-document-remote-source": ("organization_entity_id", "document_entity_id"),
        "organization-document-key-binding-list-create": ("organization_entity_id", "document_entity_id"),
        "organization-document-key-binding-detail": (
            "organization_entity_id",
            "document_entity_id",
            "binding_id",
        ),
        "organization-document-keys": ("organization_entity_id", "document_entity_id"),
        "organization-key-bindings": ("organization_entity_id",),
        "organization-document-remote-observations": ("organization_entity_id", "document_entity_id"),
        "organization-document-remote-observation-apply": (
            "organization_entity_id",
            "document_entity_id",
            "observation_id",
        ),
        "organization-document-revision-list": ("organization_entity_id", "document_entity_id"),
        "organization-document-revision-detail": (
            "organization_entity_id",
            "document_entity_id",
            "revision_id",
        ),
        "organization-document-placement-list-create": ("organization_entity_id", "document_entity_id"),
        "organization-document-placement-detail": (
            "organization_entity_id",
            "document_entity_id",
            "placement_id",
        ),
        "organization-document-placement-reuse": (
            "organization_entity_id",
            "document_entity_id",
            "placement_id",
        ),
        "organization-document-placement-detach": (
            "organization_entity_id",
            "document_entity_id",
            "placement_id",
        ),
        "organization-document-mention-search": ("organization_entity_id",),
        "organization-site-detail": ("organization_entity_id", "site_entity_id"),
        "organization-location-list-create": ("organization_entity_id", "site_entity_id"),
        "organization-location-detail": (
            "organization_entity_id",
            "site_entity_id",
            "location_entity_id",
        ),
        "organization-custom-field-definition-list-create": ("organization_entity_id",),
        "organization-custom-field-definition-detail": ("organization_entity_id", "definition_id"),
        "organization-entity-custom-field-list": ("organization_entity_id", "entity_id"),
        "organization-entity-custom-field-detail": (
            "organization_entity_id",
            "entity_id",
            "definition_id",
        ),
        "organization-entity-search": ("organization_entity_id",),
        "organization-entity-relationship-list-create": ("organization_entity_id", "entity_id"),
        "organization-entity-relationship-detail": ("organization_entity_id", "entity_id", "link_id"),
        "organization-relationship-graph": ("organization_entity_id",),
        "organization-relationship-graph-views": ("organization_entity_id",),
        "organization-relationship-graph-view-detail": ("organization_entity_id", "view_id"),
        "organization-relationship-graph-snapshots": ("organization_entity_id", "view_id"),
        "organization-relationship-graph-snapshot-export": (
            "organization_entity_id",
            "snapshot_id",
            "export_format",
        ),
        "organization-recycle-bin": ("organization_entity_id",),
        "notification-delivery-retry": ("delivery_id",),
    }
    if route_name in {"msp-recycle-bin-restore", "organization-recycle-bin-restore"}:
        kwargs = {"record_type": "site", "record_id": value}
        if route_name.startswith("organization-"):
            kwargs["organization_entity_id"] = value
        return kwargs
    return {
        name: ("json" if name == "export_format" else 1 if name == "revision_number" else value)
        for name in route_kwargs.get(route_name, ())
    }


def _request(client: Client, method: str, route_name: str):
    url = reverse(route_name, kwargs=_kwargs_for(route_name))
    return client.generic(method, url, data="{}", content_type="application/json")


MUTATION_ROUTE_METHODS = tuple(
    (contract, method)
    for contract in AUTHENTICATED_ROUTE_PERMISSIONS
    if contract.mutation_permissions
    for method in contract.methods
    if method != "GET"
)


def test_route_permission_inventory_covers_every_api_route_and_has_stable_unique_contracts():
    contracts = {contract.route_name: contract for contract in AUTHENTICATED_ROUTE_PERMISSIONS}

    assert len(contracts) == len(AUTHENTICATED_ROUTE_PERMISSIONS)
    assert set(contracts) | PUBLIC_API_ROUTE_NAMES == _api_route_names()
    route_methods = _api_route_methods()
    for contract in contracts.values():
        assert contract.methods
        assert set(contract.methods) == route_methods[contract.route_name]
        assert len(contract.mutation_permissions) <= len(contract.methods)
        for permission in contract.mutation_permissions:
            assert PERMISSION_BY_KEY[permission].requires_mfa


@pytest.mark.django_db
@pytest.mark.parametrize("contract", AUTHENTICATED_ROUTE_PERMISSIONS, ids=lambda item: item.route_name)
def test_every_authenticated_route_denies_anonymous_and_non_member(contract, installation):  # type: ignore[no-untyped-def]
    anonymous = Client()
    outsider = User.objects.create_user(
        email=f"{uuid.uuid4()}@example.com",
        display_name="Outsider",
    )
    outsider_client = Client()
    outsider_client.force_login(outsider)
    method = contract.methods[0]

    assert _request(anonymous, method, contract.route_name).status_code == 403
    assert _request(outsider_client, method, contract.route_name).status_code in {403, 404}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("contract", "method"),
    MUTATION_ROUTE_METHODS,
    ids=lambda item: item.route_name if hasattr(item, "route_name") else item,
)
def test_every_cataloged_mutation_method_denies_read_only_members(contract, method, installation):  # type: ignore[no-untyped-def]
    reader = User.objects.create_user(
        email=f"{uuid.uuid4()}@example.com",
        display_name="Reader",
    )
    TenantMembership.objects.create(tenant=installation.tenant, user=reader, role=BuiltInRole.READ_ONLY)
    client = Client()
    client.force_login(reader)
    assert _request(client, method, contract.route_name).status_code in {403, 404}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "contract",
    tuple(contract for contract in AUTHENTICATED_ROUTE_PERMISSIONS if any(_kwargs_for(contract.route_name).values())),
    ids=lambda item: item.route_name,
)
def test_identifier_routes_reject_malformed_uuid_paths_without_entering_a_view(contract, installation):  # type: ignore[no-untyped-def]
    client = Client()
    client.force_login(installation.owner)
    url = reverse(contract.route_name, kwargs=_kwargs_for(contract.route_name))
    malformed = url.replace("00000000-0000-4000-8000-000000000001", "not-a-uuid")

    assert client.get(malformed).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    "contract",
    tuple(
        contract for contract in AUTHENTICATED_ROUTE_PERMISSIONS if any(method != "GET" for method in contract.methods)
    ),
    ids=lambda item: item.route_name,
)
def test_every_unsafe_route_rejects_a_session_without_csrf(contract, installation):  # type: ignore[no-untyped-def]
    client = Client(enforce_csrf_checks=True)
    client.force_login(installation.owner)
    method = next(method for method in contract.methods if method != "GET")

    assert _request(client, method, contract.route_name).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("contract", "method"),
    MUTATION_ROUTE_METHODS,
    ids=lambda item: item.route_name if hasattr(item, "route_name") else item,
)
def test_every_cataloged_privileged_mutation_method_requires_mfa(contract, method, installation):  # type: ignore[no-untyped-def]
    installation.owner.authenticator_set.all().delete()
    client = Client()
    client.force_login(installation.owner)
    assert _request(client, method, contract.route_name).status_code in {403, 404}


@pytest.mark.django_db(transaction=True)
def test_runtime_role_enforces_complete_route_authorization_matrix(
    installation,
    django_runtime_role,  # type: ignore[no-untyped-def]
):
    anonymous = Client()
    outsider = User.objects.create_user(
        email=f"{uuid.uuid4()}@example.com",
        display_name="Runtime outsider",
    )
    outsider_client = Client()
    outsider_client.force_login(outsider)
    reader = User.objects.create_user(
        email=f"{uuid.uuid4()}@example.com",
        display_name="Runtime reader",
    )
    TenantMembership.objects.create(tenant=installation.tenant, user=reader, role=BuiltInRole.READ_ONLY)
    reader_client = Client()
    reader_client.force_login(reader)
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(installation.owner)
    privileged_client = Client()
    privileged_client.force_login(installation.owner)
    installation.owner.authenticator_set.all().delete()

    with django_runtime_role():
        for contract in AUTHENTICATED_ROUTE_PERMISSIONS:
            method = contract.methods[0]
            assert _request(anonymous, method, contract.route_name).status_code == 403, contract.route_name
            assert _request(outsider_client, method, contract.route_name).status_code in {
                403,
                404,
            }, contract.route_name
        for contract, method in MUTATION_ROUTE_METHODS:
            assert _request(reader_client, method, contract.route_name).status_code in {
                403,
                404,
            }, contract.route_name
            assert _request(privileged_client, method, contract.route_name).status_code in {
                403,
                404,
            }, contract.route_name
        for contract in AUTHENTICATED_ROUTE_PERMISSIONS:
            unsafe_methods = tuple(method for method in contract.methods if method != "GET")
            if unsafe_methods:
                response = _request(csrf_client, unsafe_methods[0], contract.route_name)
                assert response.status_code == 403, contract.route_name
