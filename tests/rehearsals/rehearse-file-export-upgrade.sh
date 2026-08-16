#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
baseline_ref=${TEKDOCS_FILE_EXPORT_UPGRADE_FROM_REF:-edfd1b5}
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-file-export-upgrade.XXXXXX")
baseline_directory="$work_directory/baseline"
environment_file="$work_directory/upgrade.env"
project_name="tekdocs_file_export_upgrade_$$"
fixture_password=$(openssl rand -base64 36 | tr -d '\n')

baseline_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$baseline_directory/compose.yml" -f "$baseline_directory/compose.test.yml" "$@"
}

current_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" "$@"
}

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    current_compose logs --no-color --tail=200 migrate backend >&2 || true
  fi
  current_compose down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  rm -rf "$work_directory"
  exit "$status"
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
if [ "$baseline_version" != "0.8.21" ]; then
  echo "File/export upgrade expected baseline 0.8.21, found $baseline_version" >&2
  exit 1
fi
if [ "$current_version" != "0.8.25" ]; then
  echo "File/export upgrade expected current version 0.8.25, found $current_version" >&2
  exit 1
fi

echo "Creating versioned source files and retained publication in TekDocs $baseline_version"
baseline_compose up -d --build --wait backend
baseline_compose exec -T -e TEKDOCS_FIXTURE_PASSWORD="$fixture_password" backend python manage.py shell -c '
import os
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.bootstrap import bootstrap_owner
from apps.core.document_attachments import create_document_attachment, replace_primary_document_file
from apps.core.documents import create_document, update_document
from apps.core.models import DocumentAttachmentPurpose, PublicationAudience, PublicationRetention
from apps.core.publications import publish_document
from apps.core.rls import OrganizationRLSMode, rls_scope
from apps.core.scoping import DataScope
from apps.core.workspaces import resolve_msp_workspace

result = bootstrap_owner(tenant_name="File Export Upgrade MSP", owner_email="upgrade@example.invalid", owner_display_name="Upgrade Owner", password=os.environ["TEKDOCS_FIXTURE_PASSWORD"])
scope = rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY)
scope.__enter__()
document = create_document(tenant=result.tenant, organization=None, actor_id=result.owner.id, title="Retained source package", markdown="# Retained source\n\nRevision one.")
revision = update_document(document=document, actor_id=result.owner.id, title="Retained source package", markdown="# Retained source\n\nRevision two.", base_revision_id=document.placements.get().block.current_revision_id)
primary_v1 = create_document_attachment(document=document, actor_id=result.owner.id, upload=SimpleUploadedFile("source-v1.pdf", b"%PDF-1.4\nsource v1\n%%EOF"), purpose=DocumentAttachmentPurpose.PRIMARY_FILE, version_number=1)
primary_v2 = replace_primary_document_file(document=document, actor_id=result.owner.id, upload=SimpleUploadedFile("source-v2.pdf", b"%PDF-1.4\nsource v2\n%%EOF"))
attachment = create_document_attachment(document=document, actor_id=result.owner.id, upload=SimpleUploadedFile("evidence.txt", b"retained evidence\n"))
publication = publish_document(workspace=resolve_msp_workspace(result.owner), document=document, actor_id=result.owner.id, reason="Upgrade boundary", audience=PublicationAudience.MSP_INTERNAL, retention=PublicationRetention.PERMANENT, retention_review_on=None)
assert revision.revision_number == 2
assert primary_v2.replaces_id == primary_v1.id
assert attachment.checksum
assert publication.content_digest
scope.__exit__(None, None, None)
print("File/export upgrade fixture created")
'
baseline_compose down --remove-orphans

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
echo "Applying TekDocs $current_version to retained file and publication state"
current_compose up -d --build --wait backend
current_compose exec -T backend python manage.py shell -c '
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
from io import BytesIO
from django.conf import settings
from apps.core.document_exports import export_bundle, resolve_export_snapshot
from apps.core.documents import resolve_document
from apps.core.models import BlockRevision, Document, DocumentAttachment, DocumentAttachmentPurpose, DocumentPublication, DocumentPublicationArtifact, InstallationState
from apps.core.publications import verify_publication
from apps.core.rls import OrganizationRLSMode, rls_scope
from apps.core.scoping import DataScope
from apps.core.workspaces import resolve_msp_workspace

tenant = InstallationState.objects.select_related("tenant", "owner").get(pk=1).tenant
owner = InstallationState.objects.select_related("owner").get(pk=1).owner
scope = rls_scope(DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.MSP_ONLY)
scope.__enter__()
document = Document.objects.select_related("entity").get(entity__display_name="Retained source package")
assert resolve_document(document).markdown == "# Retained source\n\nRevision two.\n"
revisions = BlockRevision.objects.filter(tenant=tenant)
assert revisions.filter(revision_number=2).exists(), list(revisions.values_list("revision_number", "markdown"))
for revision in revisions:
    assert revision.checksum == sha256(revision.markdown.encode("utf-8")).hexdigest()
records = list(DocumentAttachment.objects.filter(document=document).order_by("purpose", "version_number", "original_filename"))
expected = {"source-v1.pdf": b"%PDF-1.4\nsource v1\n%%EOF", "source-v2.pdf": b"%PDF-1.4\nsource v2\n%%EOF", "evidence.txt": b"retained evidence\n"}
for record in records:
    with record.file.storage.open(record.file.name, "rb") as stored:
        content = stored.read()
    assert content == expected[record.original_filename]
    assert record.size == len(content)
    assert record.checksum == sha256(content).hexdigest()
primary = [record for record in records if record.purpose == DocumentAttachmentPurpose.PRIMARY_FILE]
assert [record.version_number for record in primary] == [1, 2]
assert primary[1].replaces_id == primary[0].id
publication = DocumentPublication.objects.get(document=document)
assert verify_publication(publication)["valid"] is True
artifact = DocumentPublicationArtifact.objects.get(publication=publication, kind="pdf")
with artifact.file.storage.open(artifact.file.name, "rb") as stored:
    assert stored.read(5) == b"%PDF-"
before = sorted(path.relative_to(settings.MEDIA_ROOT).as_posix() for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file())
snapshot = resolve_export_snapshot(workspace=resolve_msp_workspace(owner), document=document, attachment_ids=tuple(record.entity_id for record in records))
bundle = export_bundle(snapshot)
with ZipFile(BytesIO(bundle)) as archive:
    assert archive.testzip() is None
    assert len([name for name in archive.namelist() if name.startswith("attachments/")]) == 3
after = sorted(path.relative_to(settings.MEDIA_ROOT).as_posix() for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file())
assert after == before
scope.__exit__(None, None, None)
print("Source files, checksums, revisions, retained publication, and regenerable export survived upgrade")
'
current_compose exec -T backend python manage.py check
current_compose exec -T backend python manage.py makemigrations --check --dry-run

echo "File/export upgrade rehearsal passed: $baseline_version -> $current_version"
