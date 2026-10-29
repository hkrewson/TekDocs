"""Preserve the reversible shape of promoted legacy content at Git acceptance."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from uuid import UUID

from .content_profile import ContentProfileError, parse_content
from .document_migration_attachments import DocumentMigrationAttachmentError, portable_document_attachments
from .models import Block, Document, DocumentAuthority, DocumentAuthorityMode, WorkspaceRepository
from .repository_service import RepositoryInputError, RepositoryServiceError


class ReversibleShapeError(ValueError):
    pass


def reversible_markdown_projection(
    expected: Mapping[str, bytes], actual: Mapping[str, bytes],
) -> dict[UUID, str]:
    """Compare snapshots without acquiring locks or reading mutable projections."""
    if not set(expected).issubset(actual):
        raise ReversibleShapeError("rollback_file_set_changed")
    markdown: dict[UUID, str] = {}
    for path, source in expected.items():
        before, after = parse_content(source), parse_content(actual[path])
        if after.content_id != before.content_id or after.kind != before.kind:
            raise ReversibleShapeError("rollback_content_identity_changed")
        if before.kind == "document":
            if after.frontmatter != before.frontmatter or after.markdown != before.markdown:
                raise ReversibleShapeError("rollback_root_metadata_changed")
        elif after.frontmatter != before.frontmatter:
            raise ReversibleShapeError("rollback_fragment_structure_changed")
        elif after.markdown != before.markdown:
            markdown[after.content_id] = after.markdown
    return markdown


def guard_reversible_migration_write(
    *, repository: WorkspaceRepository, changes: Mapping[str, bytes | None],
    read_source: Callable[[str], bytes],
) -> None:
    """Run under the writer's Git lock and repository row lock, before write_commit.

    Promotion starts from verified legacy parity. Preserving each accepted shape
    permits repeated body edits without consulting stale indexed content or taking
    another Git lock. Native Git identities have no legacy owner and are excluded.
    This cannot repair a snapshot that had already diverged before this guard.
    """
    scope = {
        "tenant_id": repository.tenant_id,
        "organization_id": repository.workspace.organization_id,
    }
    promoted = DocumentAuthority.objects.filter(
        **scope, workspace_id=repository.workspace_id, authority=DocumentAuthorityMode.REPOSITORY,
    ).values("content_id")
    documents = Document.objects.filter(
        **scope, entity__workspace_id=repository.workspace_id, id__in=promoted,
    )
    identities = {document_id: f"docs/{document_id}.md" for document_id in documents.values_list("id", flat=True)}
    owned_blocks = {
        block.id: block
        for block in Block.objects.filter(**scope, source_document__in=documents).select_related(
            "source_document__entity"
        )
    }
    identities.update({block_id: f"fragments/{block_id}.md" for block_id in owned_blocks})
    if not identities:
        return
    protected_paths = set(identities.values())
    denial = (
        "This migrated document is kept reversible. Edit only its owned fragment text; "
        "restore legacy authority before changing its metadata, paths or structure."
    )
    try:
        expected: dict[str, bytes] = {}
        actual: dict[str, bytes] = {}
        for path, source in changes.items():
            if path in protected_paths:
                expected[path] = read_source(path)
                if source is not None:
                    actual[path] = source
            elif source is not None and path.casefold().endswith(".md"):
                # A new path must not duplicate or relocate a protected identity.
                try:
                    content_id = parse_content(source).content_id
                except ContentProfileError:
                    continue  # Unrelated invalid source remains the indexer's concern.
                if content_id in identities:
                    raise ReversibleShapeError("rollback_content_identity_changed")
        markdown = reversible_markdown_projection(expected, actual)
        for block_id, body in markdown.items():
            owner = owned_blocks[block_id].source_document
            if owner is None:
                raise ReversibleShapeError("rollback_content_identity_changed")
            portable_document_attachments(owner, body)
    except DocumentMigrationAttachmentError as exc:
        raise RepositoryInputError(
            "This migrated document is kept reversible. File links must refer to its own verified files."
        ) from exc
    except (ContentProfileError, ReversibleShapeError, RepositoryServiceError) as exc:
        raise RepositoryInputError(denial) from exc
