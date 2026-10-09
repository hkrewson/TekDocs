from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import PurePosixPath
from uuid import UUID, uuid4

import yaml
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounts.models import User

from .content_profile import ContentProfileError, parse_content
from .documents import resolve_document
from .models import AuditEvent, CredentialReference, Document, DocumentPublication, GitExportBundle, WorkspaceRepository
from .repository_service import (
    MAX_PINNED_SNAPSHOT_BYTES,
    RepositoryServiceError,
    read_accepted_repository_markdown_files,
)
from .repository_storage import RepositoryStorageError
from .workspaces import ResolvedWorkspace

MAX_EXPORT_DOCUMENTS = 250
MAX_EXPORT_BYTES = 20 * 1024 * 1024
ENTITY_LINK = re.compile(r"tekdocs://entity/([0-9a-fA-F-]{36})", re.IGNORECASE)
ATTACHMENT_LINK = re.compile(r"tekdocs://attachment/[0-9a-fA-F-]{36}", re.IGNORECASE)
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


def _safe_repository_source(source: bytes, *, tenant_id: UUID) -> tuple[bytes, str, str]:
    parsed = parse_content(source)
    frontmatter = dict(parsed.frontmatter)
    frontmatter.pop("key_bindings", None)
    credential_ids = set(CredentialReference.objects.filter(tenant_id=tenant_id).values_list("entity_id", flat=True))
    if "entity_links" in frontmatter:
        frontmatter["entity_links"] = [
            link for link in frontmatter["entity_links"] if UUID(str(link["id"])) not in credential_ids
        ]
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    sanitized = _safe_markdown(f"---\n{yaml_text}---\n{parsed.markdown}", tenant_id=tenant_id)
    sanitized = sanitized.replace("tekdocs://entity/redacted", "tekdocs://credential/omitted")
    for entity_id in credential_ids:
        sanitized = re.sub(str(entity_id), "redacted-credential-reference", sanitized, flags=re.IGNORECASE)
    result = sanitized.encode("utf-8")
    parse_content(result)
    return result, str(parsed.content_id), parsed.kind


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


def _manifest_has_frozen_key_values(manifest: object) -> bool:
    if not isinstance(manifest, dict):
        return True
    resolutions = manifest.get("key_resolutions", [])
    return not isinstance(resolutions, list) or bool(resolutions)


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
    *,
    workspace: ResolvedWorkspace,
    actor: User,
    document_entity_ids: list[UUID],
    publication_entity_ids: list[UUID],
    include_repository: bool = False,
) -> GitExportBundle:
    if not document_entity_ids and not publication_entity_ids and not include_repository:
        raise ValidationError({"selection": "Select a document, STATIC publication, or repository snapshot."})
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
    if any(_manifest_has_frozen_key_values(publication.manifest) for publication in publications):
        raise ValidationError(
            {"publication_ids": "A selected STATIC publication contains frozen field values that cannot be sanitized."}
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
    repository_selection: dict[str, object] | None = None
    repository_file_count = 0
    if include_repository:
        repository = (
            WorkspaceRepository.scoped.for_tenant(workspace.member.tenant)
            .filter(workspace_id=workspace.data_scope.workspace_id)
            .first()
        )
        if repository is None or repository.accepted_commit_id is None:
            raise ValidationError({"include_repository": "This Workspace has no accepted repository content."})
        if repository.indexed_commit_id != repository.accepted_commit_id:
            raise ValidationError({"include_repository": "The accepted repository content is not fully indexed."})
        try:
            accepted, sources = read_accepted_repository_markdown_files(
                repository_id=repository.id,
                max_files=MAX_EXPORT_DOCUMENTS - len(documents) - len(publications),
                max_bytes=MAX_PINNED_SNAPSHOT_BYTES,
            )
        except (RepositoryServiceError, RepositoryStorageError) as exc:
            raise ValidationError(
                {"include_repository": "The accepted repository snapshot is unavailable or over limit."}
            ) from exc
        repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
        if repository.accepted_commit_id != accepted.id or repository.indexed_commit_id != accepted.id or not sources:
            raise ValidationError(
                {"include_repository": "The accepted repository snapshot is unavailable or not indexed."}
            )
        credential_ids = set(
            CredentialReference.objects.filter(tenant_id=workspace.member.tenant.id).values_list("entity_id", flat=True)
        )
        selected_files = []
        for path, source in sources:
            if any(str(entity_id) in path.casefold() for entity_id in credential_ids):
                raise ValidationError(
                    {"include_repository": "A repository path contains credential-reference metadata."}
                )
            try:
                sanitized, content_id, kind = _safe_repository_source(source, tenant_id=workspace.member.tenant.id)
            except (ContentProfileError, ValueError, TypeError) as exc:
                raise ValidationError({"include_repository": "Repository content cannot be safely exported."}) from exc
            export_path = str(PurePosixPath("repository") / path)
            files[export_path] = sanitized
            selected_files.append(
                {
                    "path": export_path,
                    "content_id": content_id,
                    "kind": kind,
                    "sha256": hashlib.sha256(sanitized).hexdigest(),
                }
            )
        repository_selection = {
            "accepted_commit": accepted.object_id,
            "object_format": accepted.object_format,
            "snapshot_only": True,
            "files": selected_files,
        }
        repository_file_count = len(selected_files)
    selection: dict[str, object] = {
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
    if repository_selection is not None:
        selection["repository"] = repository_selection
    files["tekdocs-export.json"] = _json(selection)
    files["README.md"] = (
        b"# TekDocs sanitized export\n\n"
        b"This deterministic, sanitized snapshot contains selected Markdown and STATIC manifests. "
        b"Repository files, when selected, come from the exact accepted commit. "
        b"It excludes known credential references, key bindings, attachment bytes and live links, "
        b"audit data, and integration payloads. Review authored text for other secrets before sharing. "
        b"It has no Git history and is not a complete backup or restore artifact.\n"
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
        metadata={
            "documents": len(documents),
            "publications": len(publications),
            "repository_files": repository_file_count,
        },
    )
    return bundle
