#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-documentation-backup.XXXXXX")
environment_file="$work_directory/recovery.env"
backup_directory="$work_directory/backup"
source_project="tekdocs_docs_backup_$$"
restore_project="tekdocs_docs_restore_$$"
mkdir -p "$backup_directory"

compose_for() {
  project_name=$1
  shift
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" "$@"
}

cleanup() {
  compose_for "$source_project" down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  compose_for "$restore_project" down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  rm -rf "$work_directory"
}
trap cleanup EXIT HUP INT TERM

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
} >> "$environment_file"

echo "Creating an isolated documentation fixture"
compose_for "$source_project" up -d --build --wait backend
compose_for "$source_project" exec -T backend python manage.py shell -c '
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.bootstrap import bootstrap_owner
from apps.core.document_attachments import create_document_attachment, replace_primary_document_file
from apps.core.documents import create_document, resolve_document, restructure_document, update_document
from apps.core.models import DocumentAttachmentPurpose, DocumentPublicationArtifact, DocumentPublicationControlEvent, PublicationAudience, PublicationRetention
from apps.core.publications import publish_document
from apps.core.rls import OrganizationRLSMode, rls_scope
from apps.core.scoping import DataScope
from apps.core.workspaces import resolve_msp_workspace

result = bootstrap_owner(tenant_name="Recovery Evidence MSP", owner_email="recovery@example.invalid", owner_display_name="Recovery Owner", password="Recovery-only-Aa7-password")
scope_context = rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY)
scope_context.__enter__()
document = create_document(tenant=result.tenant, organization=None, actor_id=result.owner.id, title="Recovery evidence runbook", markdown="# Recovery evidence\n\nRevision one.\n")
revision = update_document(document=document, actor_id=result.owner.id, title="Recovery evidence runbook", markdown="# Recovery evidence\n\nRevision two is canonical.\n", base_revision_id=document.placements.get(parent__isnull=True, position=0).block.current_revision_id)
restructured = restructure_document(document=document, actor_id=result.owner.id, base_revision_id=revision.id)
document.refresh_from_db()
attachment = create_document_attachment(document=document, actor_id=result.owner.id, upload=SimpleUploadedFile("recovery-evidence.txt", b"retained attachment bytes\n", content_type="text/plain"))
primary_v1 = create_document_attachment(document=document, actor_id=result.owner.id, upload=SimpleUploadedFile("source-v1.pdf", b"%PDF-1.4\nretained primary v1\n%%EOF", content_type="application/pdf"), purpose=DocumentAttachmentPurpose.PRIMARY_FILE, version_number=1)
primary_v2 = replace_primary_document_file(document=document, actor_id=result.owner.id, upload=SimpleUploadedFile("source-v2.pdf", b"%PDF-1.4\nretained primary v2\n%%EOF", content_type="application/pdf"))
publication = publish_document(workspace=resolve_msp_workspace(result.owner), document=document, actor_id=result.owner.id, reason="Backup rehearsal fixture", audience=PublicationAudience.MSP_INTERNAL, retention=PublicationRetention.PERMANENT, retention_review_on=None)
assert revision.revision_number == 2
assert restructured.section_count == 2
assert document.placements.count() == 2
assert resolve_document(document).markdown == "# Recovery evidence\n\nRevision two is canonical.\n"
assert attachment.file.storage.exists(attachment.file.name)
assert primary_v2.replaces_id == primary_v1.id
assert DocumentPublicationArtifact.objects.filter(publication=publication, kind="pdf").count() == 1
assert list(DocumentPublicationControlEvent.objects.filter(publication=publication).order_by("occurred_at").values_list("action", flat=True)) == ["submitted", "approved"]
scope_context.__exit__(None, None, None)
print("Documentation recovery fixture created")
'

echo "Capturing PostgreSQL and media as separate backup artifacts"
compose_for "$source_project" exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_directory/postgres.dump"
docker run --rm -v "${source_project}_media_data:/source:ro" -v "$backup_directory:/backup" postgres:17-alpine@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193 tar -czf /backup/media.tar.gz -C /source .
test -s "$backup_directory/postgres.dump"
test -s "$backup_directory/media.tar.gz"
compose_for "$source_project" down --volumes --remove-orphans

echo "Restoring into clean database and media volumes with separately retained deployment keys"
compose_for "$restore_project" up -d --wait db
compose_for "$restore_project" run --rm migrate
compose_for "$restore_project" exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < "$backup_directory/postgres.dump"
docker volume create "${restore_project}_media_data" >/dev/null
docker run --rm -v "${restore_project}_media_data:/restore" -v "$backup_directory:/backup:ro" postgres:17-alpine@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193 tar -xzf /backup/media.tar.gz -C /restore
compose_for "$restore_project" up -d --build --wait backend
compose_for "$restore_project" exec -T backend python manage.py shell -c '
from apps.core.documents import primary_placement, resolve_document
from apps.core.models import BlockRevision, Document, DocumentAttachment, DocumentAttachmentPurpose, DocumentPublication, DocumentPublicationArtifact, DocumentPublicationControlEvent, InstallationState
from apps.core.publications import verify_publication
from apps.core.rls import OrganizationRLSMode, rls_scope
from apps.core.scoping import DataScope

tenant = InstallationState.objects.select_related("tenant").get(pk=1).tenant
scope_context = rls_scope(DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.MSP_ONLY)
scope_context.__enter__()
document = Document.objects.select_related("entity").get(entity__display_name="Recovery evidence runbook")
assert document.placements.count() == 2
assert resolve_document(document).markdown == "# Recovery evidence\n\nRevision two is canonical.\n"
primary = primary_placement(document)
assert list(BlockRevision.objects.filter(block=primary.block).order_by("revision_number").values_list("markdown", flat=True)) == ["# Recovery evidence\n\nRevision one.\n", "# Recovery evidence\n\nRevision two is canonical.\n", "# Recovery evidence"]
attachment = DocumentAttachment.objects.get(document=document, original_filename="recovery-evidence.txt")
with attachment.file.storage.open(attachment.file.name, "rb") as stored:
    assert stored.read() == b"retained attachment bytes\n"
primary_versions = list(DocumentAttachment.objects.filter(document=document, purpose=DocumentAttachmentPurpose.PRIMARY_FILE).order_by("version_number"))
assert [record.version_number for record in primary_versions] == [1, 2]
assert primary_versions[1].replaces_id == primary_versions[0].id
for record, expected in zip(primary_versions, (b"%PDF-1.4\nretained primary v1\n%%EOF", b"%PDF-1.4\nretained primary v2\n%%EOF"), strict=True):
    with record.file.storage.open(record.file.name, "rb") as stored:
        assert stored.read() == expected
publication = DocumentPublication.objects.get(document=document)
assert verify_publication(publication)["valid"] is True
assert list(DocumentPublicationControlEvent.objects.filter(publication=publication).order_by("occurred_at").values_list("action", flat=True)) == ["submitted", "approved"]
artifact = DocumentPublicationArtifact.objects.get(publication=publication, kind="pdf")
with artifact.file.storage.open(artifact.file.name, "rb") as stored:
    assert stored.read(5) == b"%PDF-"
scope_context.__exit__(None, None, None)
print("Database, revision history, attachment, primary-file history, signed manifest, and PDF restored")
'
compose_for "$restore_project" exec -T backend python manage.py check

echo "Documentation backup/restore rehearsal passed"
