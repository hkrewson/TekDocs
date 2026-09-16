#!/bin/sh

#=======================# Live workspace rehearsal #=======================#
# Exercise the real browser and PostgreSQL, then verify retained records.
# Each run owns an isolated Compose project; cleanup preserves other stacks.

#=======================# VARIABLES #=======================#
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-live-workspace.XXXXXX")
environment_file="$work_directory/live-workspace.env"
project_name="tekdocs_live_workspace_$$"
playwright_image="tekdocs-live-workspace-e2e:local"

#======================# FUNCTIONS #=======================#

live_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" "$@"
}

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "Live workspace journey failed; recent backend logs follow." >&2
    live_compose logs --no-color --tail=200 migrate backend >&2 || true
    echo "Recent frontend access logs follow." >&2
    live_compose logs --no-color --tail=30 frontend >&2 || true
  fi
  live_compose down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  docker image rm -f "$playwright_image" >/dev/null 2>&1 || true
  rm -rf "$work_directory"
}
#=========================# MAIN #==========================#

trap cleanup EXIT HUP INT TERM

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
  echo "DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8080"
  echo "TEKDOCS_PUBLIC_URL=http://localhost:8080"
} >> "$environment_file"
bootstrap_token=$(sed -n 's/^TEKDOCS_BOOTSTRAP_TOKEN=//p' "$environment_file")
playwright_version=1.62.1
if ! grep -A 3 '"node_modules/@playwright/test"' "$repository_root/frontend/package-lock.json" | grep -q '"version": "1.62.1"'; then
  echo "Update the live Playwright image version to match package-lock.json." >&2
  exit 1
fi

echo "Starting isolated real-stack workspace browser journey"
live_compose build --quiet
live_compose up -d --wait
docker build --build-arg "PLAYWRIGHT_VERSION=$playwright_version" -f "$repository_root/frontend/Dockerfile.e2e" -t "$playwright_image" "$repository_root/frontend" >/dev/null
frontend_id=$(live_compose ps -q frontend)
docker run --rm \
  --network "container:$frontend_id" \
  -e PLAYWRIGHT_BASE_URL=http://localhost:8080 \
  -e TEKDOCS_E2E_BOOTSTRAP_TOKEN="$bootstrap_token" \
  "$playwright_image" npx playwright test --config=playwright.live.config.ts

live_compose run --rm -v "${project_name}_media_data:/app/media:ro" migrate python manage.py shell -c '
from datetime import timedelta
from decimal import Decimal
from django.test import Client
from django.urls import reverse
from apps.accounts.models import BuiltInRole, OrganizationAccessAssignment, TenantMembership, User
from apps.core.documents import resolve_document
from apps.core.models import AuditEvent, Block, CatalogModel, CatalogModelRevision, CatalogProduct, CatalogProductDocument, CatalogSpecificationDefinition, CatalogSpecificationDefinitionVersion, CertificateEndpoint, ClientAsset, ClientAssetDocumentProvenance, ClientAssetLifecycleEvent, ClientHardwareAsset, ClientSoftwareInstallation, CommercialContract, ComplianceEvidenceBundle, ComplianceFramework, ContractCost, CustomFieldDefinition, CustomFieldDefinitionVersion, Document, DocumentAttachment, DocumentPublication, DocumentPublicationArtifact, DocumentPublicationControlEvent, DocumentationListingReference, EntityLink, InboxNotification, Location, NetworkMACAddress, NetworkSubnet, NotificationPreference, Organization, OutboxDeliveryReceipt, OutboxEvent, PersonAssociation, RegisteredDomain, ReminderSchedule, Site, SoftwareLicense, SoftwareLicenseEvent, SoftwareLicenseInstallation, SoftwareLicenseSeat
from apps.core.models import Invoice, InvoiceArtifact, InvoiceLifecycleEvent, InvoiceLine, RecurringInvoiceSchedule, RecurringInvoiceTerms, RecurringInvoicePeriod
from apps.core.models import DNSZone, DNSRecord, NetworkCircuit, NetworkCircuitHandoff
from apps.core.compliance_bundles import verify_bundle
from apps.core.publications import read_publication_artifact, verify_publication
organization = Organization.objects.select_related("entity").get(entity__display_name="Live Acme Client")
assert organization.entity.organization_id is None
assert organization.tenant.name == "Live Workspace MSP"
assert organization.classifications.filter(kind="client").exists()
assert organization.classifications.filter(kind="vendor").exists()
assert organization.access_mode == "assigned_only"
technician = User.objects.get(display_name="Live Assigned Technician")
assignment = OrganizationAccessAssignment.objects.select_related("membership").get(
    organization=organization,
    membership__user=technician,
)
assert assignment.tenant == organization.tenant
assert assignment.membership.tenant == organization.tenant
staff_client = Client()
staff_client.force_login(technician)
workspace_response = staff_client.get(
    reverse("workspace-organization", kwargs={"entity_id": organization.entity_id}),
    HTTP_HOST="localhost",
)
assert workspace_response.status_code == 200
assert workspace_response.json()["name"] == "Live Acme Client"
association = PersonAssociation.objects.select_related("person__entity", "organization").get(
    person__entity__display_name="Live Morgan Ellis"
)
assert association.organization == organization
assert association.person.tenant == organization.tenant
assert association.role == "Office Manager"
site = Site.objects.select_related("entity", "organization").get(entity__display_name="Live Main Campus")
location = Location.objects.select_related("entity", "site", "parent__entity").get(entity__display_name="Office 214")
assert site.organization == organization
assert location.site == site
assert location.parent.entity.display_name == "Building A"
assert association.site == site
assert association.structured_location == location
assert association.location == "Live Main Campus"
assert association.office == "Office 214"
framework = ComplianceFramework.objects.get(entity__display_name="Live monitoring baseline")
assignment = framework.assignments.get()
assert framework.organization == organization
assert framework.current_revision.version_label == "2026.1"
assert assignment.applicability == "applicable"
assert assignment.implementation_status == "implemented"
assert assignment.reviews.get().decision == "Live monitoring control reviewed"
bundle = ComplianceEvidenceBundle.objects.get(organization=organization)
assert bundle.manifest["assignments"][0]["id"] == str(assignment.id)
assert verify_bundle(bundle)
registered_domain = RegisteredDomain.objects.get(ascii_name="live-acme.example")
certificate_endpoint = CertificateEndpoint.objects.get(domain=registered_domain)
assert registered_domain.organization == organization
assert registered_domain.expiration_date.isoformat() == "2027-08-13"
assert certificate_endpoint.organization == organization
assert certificate_endpoint.protocol == "https"
assert certificate_endpoint.port == 443
assert ReminderSchedule.objects.get(source_entity=registered_domain.entity).due_on.isoformat() == "2027-08-13"
definition = CustomFieldDefinition.objects.get(organization=organization, key="support_tier", entity_type="site")
version = CustomFieldDefinitionVersion.objects.get(definition=definition, version=1)
envelope = site.entity.custom_fields[str(definition.id)]
assert version.schema == {"type": "string", "enum": ["Standard", "Priority"]}
assert envelope == {
    "definition_version_id": str(version.id),
    "version": 1,
    "value": "Priority",
}
network_asset = ClientAsset.objects.get(entity__display_name="Live core switch")
network_record = NetworkSubnet.objects.get(entity__display_name="Live management LAN")
network_mac = NetworkMACAddress.objects.get(address="02:00:00:00:00:10")
assert network_record.organization == organization
assert network_record.location == location.parent
assert network_record.cidr == "192.0.2.0/24"
assert network_record.vlan_number == 20
assert network_record.use_full_range is True
assert network_record.assignable_start is None
assert network_record.assignable_end is None
circuit = NetworkCircuit.objects.get(entity__display_name="Live layout circuit")
assert circuit.organization == organization
assert circuit.tenant == organization.tenant
assert circuit.description == "Verified live circuit service"
assert circuit.service_identifier == "LIVE-CIRCUIT-01"
assert circuit.kind == "wan"
assert circuit.status == "suspended"
assert circuit.provider.entity.display_name == "Live Northwind Vendor"
assert circuit.contract_id is None
handoff = NetworkCircuitHandoff.objects.get(circuit=circuit, entity__display_name="Live circuit demarc")
assert handoff.organization == organization
assert handoff.tenant == organization.tenant
assert handoff.provider_reference == "LIVE-DEMARC-01"
assert handoff.interface.entity.display_name == "Live uplink"
assert handoff.device.entity.display_name == "Live network switch"
assert handoff.site.entity.display_name == "Live Main Campus"
assert handoff.location.entity.display_name == "Building A"
assert handoff.description == "Verified live demarc"
assert AuditEvent.objects.filter(entity_id=circuit.entity_id, action="network_circuit.handoff_created").count() == 1
assert AuditEvent.objects.filter(entity_id=circuit.entity_id, action="network_circuit.handoff_updated").count() == 2
assert AuditEvent.objects.filter(entity_id=circuit.entity_id, action="network_circuit.updated").count() == 3
dns_zone = DNSZone.objects.get(name="live-layout.example.invalid")
dns_record = DNSRecord.objects.get(zone=dns_zone, owner_name="host.live-layout.example.invalid")
assert dns_zone.organization == organization
assert dns_zone.tenant == organization.tenant
assert dns_record.organization == organization
assert dns_record.tenant == organization.tenant
assert dns_record.entity.organization_id == organization.id
assert dns_record.record_type == "TXT"
assert dns_record.value == "Live DNS value"
assert dns_record.ttl == 600
assert dns_record.ip_address_id is None
assert sorted(AuditEvent.objects.filter(entity_id=dns_record.entity_id).values_list("action", flat=True)) == [
    "dns_record.created", "dns_record.updated",
]
assert str(network_record.primary_dns) == "9.9.9.9"
assert str(network_record.secondary_dns) == "1.1.1.1"
assert network_mac.interface_id is None
assert network_mac.hardware_asset == network_asset
assert network_mac.description == "Ethernet"
vendor = Organization.objects.get(entity__display_name="Live Northwind Vendor")
link = EntityLink.objects.get(source=organization.entity, target=vendor.entity, link_type="supplied_by")
assert link.archived_at is None
assert link.metadata == {}
catalog_product = CatalogProduct.objects.get(entity__display_name="Live EdgeSwitch")
catalog_model = CatalogModel.objects.get(entity__display_name="Live EdgeSwitch 24")
catalog_definition = CatalogSpecificationDefinition.objects.get(name="Managed switch")
catalog_version = CatalogSpecificationDefinitionVersion.objects.get(definition=catalog_definition, version=1)
catalog_revisions = list(CatalogModelRevision.objects.filter(model=catalog_model).order_by("revision"))
assert catalog_product.organization == vendor
assert catalog_product.kind == "hardware"
assert catalog_model.organization == vendor
assert catalog_model.product == catalog_product
assert catalog_version.schema["additionalProperties"] is False
assert catalog_version.schema["required"] == ["port_count"]
assert len(catalog_revisions) == 2
assert catalog_revisions[0].parent_id is None
assert catalog_revisions[1].parent_id == catalog_revisions[0].id
assert catalog_revisions[1].specification_version == catalog_version
assert catalog_revisions[1].specifications == {"port_count": 24}
assert catalog_revisions[0].checksum != catalog_revisions[1].checksum
catalog_document = CatalogProductDocument.objects.select_related("publication", "model").get(
    product=catalog_product, archived_at__isnull=True
)
assert catalog_document.model == catalog_model
assert catalog_document.publication.audience == "client_visible"
asset = ClientAsset.objects.select_related("entity", "supplier", "product", "model", "model_revision").get(
    entity__display_name="Live core switch"
)
assert asset.organization == organization
assert asset.supplier == vendor
assert asset.product == catalog_product
assert asset.model == catalog_model
assert asset.model_revision == catalog_revisions[1]
assert asset.specifications == {"port_count": 24}
assert len(asset.provenance_checksum) == 64
asset_document = ClientAssetDocumentProvenance.objects.get(asset=asset)
assert asset_document.catalog_document == catalog_document
assert asset_document.publication == catalog_document.publication
assert asset_document.content_digest == catalog_document.publication.content_digest
msp_asset = ClientAsset.objects.select_related("entity", "supplier", "product", "model").get(
    entity__display_name="Live MSP core switch"
)
assert msp_asset.organization is None
assert msp_asset.entity.organization_id is None
assert msp_asset.tenant == organization.tenant
assert msp_asset.supplier == vendor
assert msp_asset.product == catalog_product
assert msp_asset.model == catalog_model
assert ClientAssetLifecycleEvent.objects.filter(
    asset=msp_asset,
    organization__isnull=True,
    event_type="created",
).count() == 1
hardware = ClientHardwareAsset.objects.get(asset=asset)
assert hardware.serial_number == "LIVE-SN-100"
assert hardware.asset_tag == "LIVE-SW-100"
assert hardware.lifecycle_state == "in_service"
assert hardware.assigned_person == association
assert hardware.assigned_site == site
assert hardware.assigned_location == location
assert sorted(ClientAssetLifecycleEvent.objects.filter(asset=asset).values_list("event_type", flat=True)) == [
    "assigned",
    "created",
    "state_changed",
]
software_asset = ClientAsset.objects.select_related("entity", "supplier", "product", "model").get(
    entity__display_name="Live endpoint protection"
)
assert software_asset.organization == organization
assert software_asset.supplier == vendor
assert software_asset.product.entity.display_name == "Live Secure Agent"
assert software_asset.model.entity.display_name == "Live Secure Agent Business"
software_installation = ClientSoftwareInstallation.objects.get(asset=software_asset)
assert software_installation.status == "installed"
assert software_installation.installed_version == "7.4.1"
assert software_installation.installed_on.isoformat() == "2026-08-10"
license_record = SoftwareLicense.objects.select_related("entity", "product", "model").get(
    entity__display_name="Live Secure Agent subscription"
)
assert license_record.organization == organization
assert license_record.product == software_asset.product
assert license_record.model == software_asset.model
assert license_record.seat_limit == 5
assert license_record.renewal_interval == "annual"
assert license_record.auto_renew is True
assert license_record.renews_on.isoformat() == "2027-09-10"
assert SoftwareLicenseInstallation.objects.filter(
    license=license_record, installation=software_installation, archived_at__isnull=True
).count() == 1
license_seat = SoftwareLicenseSeat.objects.get(license=license_record, revoked_at__isnull=True)
assert license_seat.seat_number == 1
assert license_seat.person == association
assert license_seat.installation == software_installation
assert sorted(SoftwareLicenseEvent.objects.filter(license=license_record).values_list("event_type", flat=True)) == [
    "created",
    "details_updated",
    "seat_assigned",
]
contract = CommercialContract.objects.select_related("entity", "provider__entity").get(
    entity__display_name="Live managed services agreement"
)
assert contract.organization == organization
assert contract.provider == vendor
assert contract.status == "active"
assert contract.renews_on.isoformat() == "2027-08-10"
assert contract.renewal_notice_days == 45
cost = ContractCost.objects.get(contract=contract, archived_at__isnull=True)
assert str(cost.amount) == "875.50"
assert cost.currency == "USD"
assert cost.reference == "LIVE-PRIVATE-RATE"
assert cost.billing_interval == "monthly"
schedule = RecurringInvoiceSchedule.objects.get(contract_cost=cost)
terms = RecurringInvoiceTerms.objects.get(schedule=schedule)
period = RecurringInvoicePeriod.objects.select_related("invoice", "line").get(schedule=schedule)
assert schedule.organization == organization
assert schedule.tenant == organization.tenant
assert schedule.enabled is False
stop_event = AuditEvent.objects.get(action="invoice.recurring_stopped", entity_id=contract.entity_id)
assert stop_event.metadata == {"schedule_id": str(schedule.pk), "reason": "Live service ended"}
assert stop_event.actor_id == User.objects.get(display_name="Live Workspace Owner").pk
assert schedule.interval == "monthly"
assert terms.version == 1
assert terms.description == "Live approved monthly support"
assert terms.quantity == Decimal("2.000")
assert terms.unit_amount == Decimal("75.0000")
assert terms.currency == "USD"
assert terms.tax_rate_id is None
assert terms.due_days == 30
assert period.terms == terms
assert period.starts_on == schedule.anchor
assert period.ends_before > period.starts_on
assert period.organization == organization
assert period.tenant == organization.tenant
invoice = period.invoice
line = period.line
assert Invoice.objects.filter(organization=organization).count() == 1
assert InvoiceLine.objects.filter(invoice=invoice).count() == 1
assert invoice.organization == organization
assert invoice.tenant == organization.tenant
assert invoice.state == "draft"
assert invoice.number == ""
assert invoice.issued_at is None
assert invoice.invoice_date == schedule.anchor
assert invoice.due_date == schedule.anchor + timedelta(days=30)
assert line.invoice == invoice
assert line.description == terms.description
assert line.quantity == terms.quantity
assert line.unit_amount == terms.unit_amount
assert line.currency == "USD"
assert not InvoiceArtifact.objects.filter(invoice=invoice).exists()
assert not InvoiceLifecycleEvent.objects.filter(invoice=invoice).exists()
print("Live recurring stop retained its audit reason, approved schedule, period claim, and unissued draft.")

from apps.core.models import NetworkRack
rack = NetworkRack.objects.select_related("site__entity", "location__entity").get(entity__display_name="Live layout rack")
assert rack.organization == organization
assert rack.status == "planned" and rack.unit_count == 42
assert rack.site.entity.display_name == "Live Main Campus"
assert rack.location.entity.display_name == "Building A"
assert AuditEvent.objects.filter(entity_id=rack.entity_id, action="network_rack.updated").exists()
print("Live rack creation and update retained its exact site, location and audit history.")
from apps.core.models import NetworkDevice
device = NetworkDevice.objects.select_related("hardware_asset__entity").get(entity__display_name="Live network switch")
assert device.organization == organization and device.rack == rack
assert device.site_id == rack.site_id and device.location_id == rack.location_id
assert device.rack_unit == 5 and device.rack_units == 2 and device.status == "offline"
assert device.hardware_asset.entity.display_name == "Live core switch"
assert AuditEvent.objects.filter(entity_id=device.entity_id, action="network_device.updated").count() == 2
print("Live device retained hardware identity, ordinary edits and rack-derived placement.")
from apps.core.models import NetworkInterface
interface = NetworkInterface.objects.get(entity__display_name="Live uplink")
assert interface.organization == organization and interface.device_id == device.pk
assert interface.status == "disabled" and interface.kind == "physical"
assert interface.description == "Uplink to the core rack"
assert AuditEvent.objects.filter(entity_id=interface.entity_id, action="network_interface.updated").count() == 1
print("Live interface retained its device binding, description, status and update audit.")
from apps.core.models import NetworkIPAddress
interface_ip = NetworkIPAddress.objects.get(address="192.0.2.11", organization=organization)
assert interface_ip.interface_id == interface.pk and interface_ip.hardware_asset_id is None
assert interface_ip.description == "Live interface IP address" and interface_ip.status == "reserved"
interface_mac = NetworkMACAddress.objects.get(address="02:00:00:00:00:71", organization=organization)
assert interface_mac.interface_id is None and interface_mac.hardware_asset_id is None
assert interface_mac.description == "Live interface MAC address"
assert AuditEvent.objects.filter(entity_id=interface_ip.entity_id, action="network_ip_address.created").count() == 1
assert AuditEvent.objects.filter(entity_id=interface_ip.entity_id, action="network_ip_address.updated").count() == 1
assert AuditEvent.objects.filter(entity_id=interface_mac.entity_id, action="network_mac_address.created").count() == 1
assert AuditEvent.objects.filter(entity_id=interface_mac.entity_id, action="network_mac_address.updated").count() == 2
print("Live endpoint creation retains interface bindings, ordinary edits and removed MAC history.")

client_document = Document.objects.get(entity__display_name="Live Acme onboarding")
assert client_document.organization == organization
client_block = client_document.placements.get(parent__isnull=True, position=0).block
client_revisions = list(client_block.revisions.order_by("revision_number").values_list("markdown", flat=True))
assert client_revisions == [
    "# Acme onboarding\n\nClient-owned canonical Markdown.",
    "# Acme onboarding\n\nRevision two is retained.",
    "# Acme onboarding",
]
semantic_placement = client_document.placements.get(parent__isnull=True, position=1)
assert semantic_placement.block.current_revision.markdown == "Revision two is retained."
conversion_event = AuditEvent.objects.get(
    action="document.semantic_sections_created",
    entity_id=client_document.entity_id,
)
assert conversion_event.metadata["section_count"] == 2
assert "markdown" not in conversion_event.metadata
assert "tekdocs://entity/" not in resolve_document(client_document).markdown
file_document = Document.objects.get(entity__display_name="Live vendor source file")
assert file_document.organization == organization
resolved_file_notes = resolve_document(file_document).markdown
assert resolved_file_notes == "## Local notes\n\nClient-specific context.\n", repr(resolved_file_notes)
primary_versions = list(DocumentAttachment.objects.filter(document=file_document, purpose="primary_file").order_by("version_number"))
assert [record.version_number for record in primary_versions] == [1, 2]
assert primary_versions[1].replaces_id == primary_versions[0].id
for record, expected in zip(primary_versions, (b"retained source version one\n", b"retained source version two\n"), strict=True):
    with record.file.storage.open(record.file.name, "rb") as stored:
        assert stored.read() == expected
assert AuditEvent.objects.filter(action="document.primary_file.created", entity_id__in=[record.entity_id for record in primary_versions]).count() == 2
template = Document.objects.get(entity__display_name="Live incident template")
template_copy = Document.objects.get(entity__display_name="New from Live incident template")
assert template.organization == organization
assert template.category == "procedure"
assert template.is_template is True
assert template_copy.organization == organization
assert template_copy.category == "procedure"
assert template_copy.is_template is False
template_attachment = DocumentAttachment.objects.get(document=template, archived_at__isnull=True)
copied_attachment = DocumentAttachment.objects.get(document=template_copy, archived_at__isnull=True)
assert template_attachment.entity_id != copied_attachment.entity_id
assert template_attachment.checksum == copied_attachment.checksum
assert template_attachment.original_filename == copied_attachment.original_filename == "incident-checklist.txt"
assert not template_attachment.file.name.endswith("incident-checklist.txt")
assert str(template_attachment.entity_id) in resolve_document(template).markdown
assert str(copied_attachment.entity_id) in resolve_document(template_copy).markdown
assert str(template_attachment.entity_id) not in resolve_document(template_copy).markdown
imported_document = Document.objects.get(entity__display_name="live-import")
assert imported_document.organization == organization
assert imported_document.category == "general"
assert imported_document.is_template is False
assert imported_document.placements.filter(parent__isnull=True).count() == 2
assert resolve_document(imported_document).markdown == "# Imported runbook\n\nCanonical UTF-8 Markdown.\n"
shared_document = Document.objects.get(entity__display_name="Live shared response")
assert shared_document.organization is None
shared_block = shared_document.placements.get(parent__isnull=True, position=0).block
assert shared_block.current_revision.markdown == "MSP-owned block revision three."
assert list(shared_block.revisions.order_by("revision_number").values_list("markdown", flat=True)) == [
    "One MSP-owned block.",
    "MSP-owned block revision two.",
    "MSP-owned block revision three.",
]
assert DocumentationListingReference.objects.filter(
    document=shared_document, organization=organization, archived_at__isnull=True
).count() == 1
reuse = client_document.placements.get(block__current_revision__markdown="MSP-owned block revision two.")
assert reuse.block != shared_block
assert reuse.block.organization == organization
assert reuse.resolution_mode == "live"
assert reuse.block.current_revision.markdown == "MSP-owned block revision two."
resolved = resolve_document(client_document).markdown
assert "MSP-owned block revision two." in resolved
assert "revision three" not in resolved
assert Block.objects.filter(placements__document=shared_document).count() == 1
publication = DocumentPublication.objects.get(document=client_document)
assert publication.reason == "Live publication regression"
assert publication.audience == "client_visible"
assert publication.retention == "permanent"
assert publication.lifecycle_state == "withdrawn"
assert verify_publication(publication)["valid"] is True
assert list(
    DocumentPublicationControlEvent.objects.filter(publication=publication)
    .order_by("occurred_at", "id")
    .values_list("action", flat=True)
) == ["submitted", "approved", "withdrawn"]
portal_membership = TenantMembership.objects.select_related("user", "organization").get(
    user__display_name="Live Client Reader"
)
assert portal_membership.role == BuiltInRole.CLIENT_USER
assert portal_membership.organization == organization
assert InboxNotification.objects.filter(
    recipient=portal_membership.user,
    surface="client_portal",
    organization=organization,
).count() >= 2
preference = NotificationPreference.objects.get(user=portal_membership.user, surface="client_portal")
assert preference.delivery_mode == "daily"
assert preference.quiet_start.isoformat(timespec="minutes") == "22:00"
assert preference.quiet_end.isoformat(timespec="minutes") == "07:00"
assert OutboxEvent.objects.filter(organization=organization, state="delivered").count() >= 3
assert OutboxDeliveryReceipt.objects.filter(event__organization=organization).count() >= 3
pdf_artifact = DocumentPublicationArtifact.objects.get(publication=publication, kind="pdf")
assert read_publication_artifact(pdf_artifact).startswith(b"%PDF-")
assert publication.manifest["artifacts"][0]["checksum"] == pdf_artifact.checksum
print("Live workspace database fixture verified")
'
echo "Real browser-to-Django-to-PostgreSQL workspace journey passed"
