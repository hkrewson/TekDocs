#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
baseline_ref=${TEKDOCS_DOCUMENTATION_UPGRADE_FROM_REF:-9b9fcc4}
expected_baseline_version=${TEKDOCS_DOCUMENTATION_UPGRADE_FROM_VERSION:-0.2.8}
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-documentation-upgrade.XXXXXX")
baseline_directory="$work_directory/baseline"
environment_file="$work_directory/upgrade.env"
project_name="tekdocs_docs_upgrade_$$"

baseline_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$baseline_directory/compose.yml" -f "$baseline_directory/compose.test.yml" "$@"
}

current_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" "$@"
}

cleanup() {
  current_compose down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  rm -rf "$work_directory"
}
trap cleanup EXIT HUP INT TERM

git -C "$repository_root" cat-file -e "$baseline_ref^{commit}"
mkdir -p "$baseline_directory"
git -C "$repository_root" archive "$baseline_ref" | tar -x -C "$baseline_directory"
"$baseline_directory/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
} >> "$environment_file"

baseline_version=$(tr -d '[:space:]' < "$baseline_directory/VERSION")
current_version=$(tr -d '[:space:]' < "$repository_root/VERSION")
if [ "$baseline_version" != "$expected_baseline_version" ]; then
  echo "Documentation upgrade expected baseline $expected_baseline_version, found $baseline_version" >&2
  exit 1
fi
if [ "$current_version" = "$baseline_version" ]; then
  echo "Documentation upgrade requires a version newer than $baseline_version" >&2
  exit 1
fi

echo "Creating retained documentation in TekDocs $baseline_version"
baseline_compose up -d --build --wait backend
baseline_compose exec -T backend python manage.py shell -c '
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.bootstrap import bootstrap_owner
from apps.core.document_attachments import create_document_attachment
from apps.core.documents import create_document, update_document
from apps.core.models import PublicationAudience, PublicationRetention
from apps.core.publications import publish_document
from apps.core.rls import OrganizationRLSMode, rls_scope
from apps.core.scoping import DataScope
from apps.core.workspaces import resolve_msp_workspace

result = bootstrap_owner(tenant_name="Documentation Upgrade MSP", owner_email="documentation-upgrade@example.invalid", owner_display_name="Upgrade Owner", password="Upgrade-only-Aa7-password")
scope_context = rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY)
scope_context.__enter__()
document = create_document(tenant=result.tenant, organization=None, actor_id=result.owner.id, title="Preserved documentation alpha", markdown="# Preserved alpha\n\nRevision one.\n")
current_id = document.placements.get(parent__isnull=True, position=0).block.current_revision_id
update_document(document=document, actor_id=result.owner.id, title="Preserved documentation alpha", markdown="# Preserved alpha\n\nRevision two.\n", base_revision_id=current_id)
create_document_attachment(document=document, actor_id=result.owner.id, upload=SimpleUploadedFile("upgrade.txt", b"preserve this file\n", content_type="text/plain"))
publish_document(workspace=resolve_msp_workspace(result.owner), document=document, actor_id=result.owner.id, reason="Pre-upgrade publication", audience=PublicationAudience.MSP_INTERNAL, retention=PublicationRetention.PERMANENT, retention_review_on=None)
scope_context.__exit__(None, None, None)
print("Documentation fixture created")
'
baseline_compose down --remove-orphans

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
echo "Applying TekDocs $current_version to the retained $baseline_version database and media"
current_compose up -d --build --wait backend
current_compose exec -T backend python manage.py shell -c '
from apps.core.models import BlockRevision, Document, DocumentAttachment, DocumentPublication, DocumentPublicationArtifact, InstallationState
from apps.core.publications import verify_publication
from apps.core.rls import OrganizationRLSMode, rls_scope
from apps.core.scoping import DataScope

tenant = InstallationState.objects.select_related("tenant").get(pk=1).tenant
scope_context = rls_scope(DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.MSP_ONLY)
scope_context.__enter__()
document = Document.objects.select_related("entity").get(entity__display_name="Preserved documentation alpha")
assert list(BlockRevision.objects.filter(block__placements__document=document).order_by("revision_number").values_list("revision_number", flat=True)) == [1, 2]
attachment = DocumentAttachment.objects.get(document=document, original_filename="upgrade.txt")
with attachment.file.storage.open(attachment.file.name, "rb") as stored:
    assert stored.read() == b"preserve this file\n"
publication = DocumentPublication.objects.get(document=document)
assert verify_publication(publication)["valid"] is True
artifact = DocumentPublicationArtifact.objects.get(publication=publication, kind="pdf")
with artifact.file.storage.open(artifact.file.name, "rb") as stored:
    assert stored.read(5) == b"%PDF-"
scope_context.__exit__(None, None, None)
print("Documentation identities, history, attachment, manifest, and PDF survived upgrade")
'
current_compose exec -T backend python manage.py check
current_compose exec -T backend python manage.py makemigrations --check --dry-run

echo "Documentation upgrade rehearsal passed: $baseline_version -> $current_version"
