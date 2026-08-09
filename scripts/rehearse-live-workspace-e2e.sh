#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
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
    echo "Live workspace journey failed; recent service logs follow." >&2
    live_compose logs --no-color --tail=120 backend frontend >&2 || true
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
live_compose up -d --build --wait
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
from apps.accounts.models import OrganizationAccessAssignment, User
from apps.core.documents import resolve_document
from apps.core.models import Block, CustomFieldDefinition, CustomFieldDefinitionVersion, Document, DocumentAttachment, DocumentPublication, DocumentPublicationArtifact, DocumentationListingReference, EntityLink, Location, Organization, PersonAssociation, Site
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
definition = CustomFieldDefinition.objects.get(organization=organization, key="support_tier", entity_type="site")
version = CustomFieldDefinitionVersion.objects.get(definition=definition, version=1)
envelope = site.entity.custom_fields[str(definition.id)]
assert version.schema == {"type": "string", "enum": ["Standard", "Priority"]}
assert envelope == {
    "definition_version_id": str(version.id),
    "version": 1,
    "value": "Priority",
}
vendor = Organization.objects.get(entity__display_name="Live Northwind Vendor")
link = EntityLink.objects.get(source=organization.entity, target=vendor.entity, link_type="supplied_by")
assert link.archived_at is None
assert link.metadata == {}
client_document = Document.objects.get(entity__display_name="Live Acme onboarding")
assert client_document.organization == organization
client_block = client_document.placements.get(parent__isnull=True, position=0).block
assert client_block.current_revision.markdown.endswith(
    "[Live Main Campus](tekdocs://entity/" + str(organization.sites.get(entity__display_name="Live Main Campus").entity_id) + ")"
)
assert list(client_block.revisions.order_by("revision_number").values_list("markdown", flat=True)) == [
    "# Acme onboarding\n\nClient-owned canonical Markdown.",
    "# Acme onboarding\n\nRevision two is retained.",
    client_block.current_revision.markdown,
]
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
assert publication.lifecycle_state == "current"
assert verify_publication(publication)["valid"] is True
pdf_artifact = DocumentPublicationArtifact.objects.get(publication=publication, kind="pdf")
assert read_publication_artifact(pdf_artifact).startswith(b"%PDF-")
assert publication.manifest["artifacts"][0]["checksum"] == pdf_artifact.checksum
print("Live workspace database fixture verified")
'
echo "Real browser-to-Django-to-PostgreSQL workspace journey passed"
