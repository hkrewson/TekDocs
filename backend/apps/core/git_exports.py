from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounts.models import User

from .documents import resolve_document
from .models import AuditEvent, CredentialReference, Document, DocumentPublication, GitExportBundle
from .workspaces import ResolvedWorkspace

MAX_EXPORT_DOCUMENTS = 250
MAX_EXPORT_BYTES = 20 * 1024 * 1024
ENTITY_LINK = re.compile(r"tekdocs://entity/([0-9a-fA-F-]{36})")
ATTACHMENT_LINK = re.compile(r"tekdocs://attachment/[0-9a-fA-F-]{36}")
ONEPASSWORD_LINK = re.compile(r"https://(?:[A-Za-z0-9-]+\.)?1password\.com/[^\s)>]+", re.IGNORECASE)


def _json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def _safe_markdown(markdown: str, *, tenant_id: UUID) -> str:
    credential_entity_ids = set(
        CredentialReference.objects.filter(tenant_id=tenant_id).values_list("entity_id", flat=True)
    )

    def entity_replacement(match: re.Match[str]) -> str:
        try:
            entity_id = UUID(match.group(1))
        except ValueError:
            return "tekdocs://entity/invalid"
        return "tekdocs://entity/redacted" if entity_id in credential_entity_ids else match.group(0)

    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    normalized = ENTITY_LINK.sub(entity_replacement, normalized)
    normalized = ATTACHMENT_LINK.sub("tekdocs://attachment/omitted", normalized)
    normalized = ONEPASSWORD_LINK.sub("tekdocs://credential/omitted", normalized)
    return normalized.rstrip("\n") + "\n"


def _manifest_has_credential_reference(manifest: object) -> bool:
    if not isinstance(manifest, dict):
        return True
    entities = manifest.get("entities", [])
    if not isinstance(entities, list):
        return True
    return any(
        not isinstance(projection, dict) or projection.get("entity_type") == "credential_reference"
        for projection in entities
    )


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, files[path])
    return target.getvalue()


@transaction.atomic
def create_git_export(
    *, workspace: ResolvedWorkspace, actor: User, document_entity_ids: list[UUID], publication_entity_ids: list[UUID]
) -> GitExportBundle:
    if not document_entity_ids and not publication_entity_ids:
        raise ValidationError({"selection": "Select at least one document or STATIC publication."})
    if len(document_entity_ids) + len(publication_entity_ids) > MAX_EXPORT_DOCUMENTS:
        raise ValidationError({"selection": "A Git export may contain at most 250 selected records."})
    documents = list(
        Document.scoped.for_scope(workspace.data_scope)
        .filter(entity_id__in=document_entity_ids, archived_at__isnull=True)
        .select_related("entity")
        .prefetch_related("placements__block__current_revision", "placements__pinned_revision")
        .order_by("entity__display_name", "entity_id")
    )
    publications = list(
        DocumentPublication.scoped.for_scope(workspace.data_scope)
        .filter(entity_id__in=publication_entity_ids)
        .select_related("entity", "document__entity")
        .order_by("title", "entity_id")
    )
    if len(documents) != len(set(document_entity_ids)) or len(publications) != len(set(publication_entity_ids)):
        raise NotFound("One or more selected export records are unavailable in this Workspace.")
    if any(_manifest_has_credential_reference(publication.manifest) for publication in publications):
        raise ValidationError(
            {"publication_ids": "A selected STATIC publication contains credential-reference metadata."}
        )

    files: dict[str, bytes] = {}
    selected_documents: list[dict[str, str]] = []
    for document in documents:
        filename = f"documents/{slugify(document.entity.display_name) or 'document'}--{document.entity_id}.md"
        markdown = _safe_markdown(resolve_document(document).markdown, tenant_id=workspace.member.tenant.id)
        files[filename] = markdown.encode()
        selected_documents.append({"entity_id": str(document.entity_id), "path": filename})
    selected_publications: list[dict[str, str]] = []
    for publication in publications:
        directory = PurePosixPath("publications") / str(publication.entity_id)
        markdown_path = str(directory / "publication.md")
        manifest_path = str(directory / "manifest.json")
        files[markdown_path] = _safe_markdown(
            publication.canonical_markdown, tenant_id=workspace.member.tenant.id
        ).encode()
        files[manifest_path] = _json(publication.manifest)
        selected_publications.append(
            {"entity_id": str(publication.entity_id), "markdown_path": markdown_path, "manifest_path": manifest_path}
        )
    selection = {
        "format": "tekdocs-sanitized-git-export/v1",
        "workspace_id": str(workspace.data_scope.workspace_id),
        "documents": selected_documents,
        "publications": selected_publications,
        "exclusions": [
            "credential_references",
            "attachment_content",
            "live_attachment_links",
            "secrets",
            "audit",
            "provider_payloads",
            "editor_html",
        ],
    }
    files["tekdocs-export.json"] = _json(selection)
    files["README.md"] = (
        b"# TekDocs sanitized export\n\n"
        b"This deterministic working tree contains selected Markdown and STATIC manifests. "
        b"It excludes credential references, attachment bytes, secrets, audit data, and integration payloads.\n"
    )
    content = _zip_bytes(files)
    if len(content) > MAX_EXPORT_BYTES:
        raise ValidationError({"selection": "The sanitized Git export exceeds 20 MiB."})
    bundle = GitExportBundle(
        id=uuid4(),
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        selection_manifest=selection,
        content_digest=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
        created_by=actor,
    )
    bundle.artifact.save("export.zip", ContentFile(content), save=False)
    bundle.full_clean()
    bundle.save()  # type: ignore[no-untyped-call]
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor=actor,
        action="git_export.created",
        entity_id=bundle.id,
        metadata={"documents": len(documents), "publications": len(publications)},
    )
    return bundle
