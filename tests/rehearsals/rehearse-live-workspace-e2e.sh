#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-live-workspace.XXXXXX")
environment_file="$work_directory/live-workspace.env"
project_name="tekdocs_live_workspace_$$"
playwright_image="tekdocs-live-workspace-e2e:local"

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
from django.test import Client
from django.urls import reverse
from apps.accounts.models import BuiltInRole, OrganizationAccessAssignment, TenantMembership, User
from apps.core.documents import resolve_document
from apps.core.models import Block, CatalogModel, CatalogModelRevision, CatalogProduct, CatalogProductDocument, CatalogSpecificationDefinition, CatalogSpecificationDefinitionVersion, CertificateEndpoint, ClientAsset, ClientAssetDocumentProvenance, ClientAssetLifecycleEvent, ClientHardwareAsset, ClientSoftwareInstallation, CommercialContract, ComplianceEvidenceBundle, ComplianceFramework, ContractCost, CustomFieldDefinition, CustomFieldDefinitionVersion, Document, DocumentAttachment, DocumentPublication, DocumentPublicationArtifact, DocumentPublicationControlEvent, DocumentationListingReference, EntityLink, InboxNotification, Location, NetworkMACAddress, NetworkSubnet, NotificationPreference, Organization, OutboxDeliveryReceipt, OutboxEvent, PersonAssociation, RegisteredDomain, ReminderSchedule, Site, SoftwareLicense, SoftwareLicenseEvent, SoftwareLicenseInstallation, SoftwareLicenseSeat
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
assert list(ClientAssetLifecycleEvent.objects.filter(asset=asset).values_list("event_type", flat=True)) == [
    "assigned",
    "state_changed",
    "created",
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
assert list(SoftwareLicenseEvent.objects.filter(license=license_record).values_list("event_type", flat=True)) == [
    "details_updated",
    "seat_assigned",
    "created",
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
client_document = Document.objects.get(entity__display_name="Live Acme onboarding")
assert client_document.organization == organization
client_block = client_document.placements.get(parent__isnull=True, position=0).block
client_revisions = list(client_block.revisions.order_by("revision_number").values_list("markdown", flat=True))
assert len(client_revisions) == 4
assert client_revisions[0] == "# Acme onboarding\n\nClient-owned canonical Markdown."
assert client_revisions[1] == "# Acme onboarding\n\nRevision two is retained."
assert "tekdocs://entity/" in client_revisions[2]
assert "tekdocs://entity/" not in client_revisions[3]
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
assert str(template_attachment.entity_id) in template.placements.get(parent__isnull=True, position=0).block.current_revision.markdown
assert str(copied_attachment.entity_id) in template_copy.placements.get(parent__isnull=True, position=0).block.current_revision.markdown
assert str(template_attachment.entity_id) not in template_copy.placements.get(parent__isnull=True, position=0).block.current_revision.markdown
imported_document = Document.objects.get(entity__display_name="live-import")
assert imported_document.organization == organization
assert imported_document.category == "general"
assert imported_document.is_template is False
assert imported_document.placements.get(parent__isnull=True, position=0).block.current_revision.markdown == "# Imported runbook\n\nCanonical UTF-8 Markdown.\n"
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
reuse = client_document.placements.exclude(parent__isnull=True, position=0).get()
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
