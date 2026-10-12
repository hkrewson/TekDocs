"""Explicit, parity-gated authority transitions for imported documents."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from django.db import connection, transaction

from .content_profile import ContentProfileError, parse_content
from .document_migration_coexistence import document_coexistence_status
from .document_migration_export import build_simple_document_export
from .documents import _append_block_revision
from .models import (
    AuditEvent,
    Block,
    Document,
    DocumentAuthority,
    DocumentAuthorityMode,
    Workspace,
    WorkspaceRepository,
)
from .repository_service import RepositoryServiceError, read_accepted_repository_markdown_files
from .workspaces import ResolvedWorkspace


class DocumentAuthorityHandoffError(ValueError):
    def __init__(self, *codes: str) -> None:
        self.codes = tuple(sorted(set(codes)))
        super().__init__(", ".join(self.codes))


def prepare_rollback_markdown_projection(*, workspace: Workspace, document: Document) -> dict[UUID, str]:
    """Return safely projectable Git-authored fragment Markdown, or fail closed.

    Rollback supports body edits only. Stable identities, root metadata, fragment
    metadata, and the placement/include graph must still match the legacy export.
    """

    repository = WorkspaceRepository.objects.filter(workspace=workspace).first()
    if (
        repository is None
        or repository.accepted_commit_id is None
        or repository.accepted_commit_id != repository.indexed_commit_id
    ):
        raise DocumentAuthorityHandoffError("rollback_repository_not_ready")
    try:
        exported = build_simple_document_export(document, allow_repository_divergence=True)
        accepted, files = read_accepted_repository_markdown_files(repository_id=repository.id)
        if accepted.id != repository.accepted_commit_id:
            raise DocumentAuthorityHandoffError("rollback_repository_not_ready")
        current = dict(files)
        expected_paths = {path for path, _source in exported.files}
        parsed_current = {
            path: parse_content(current[path])
            for path in expected_paths
            if path in current
        }
        parsed_expected = {path: parse_content(source) for path, source in exported.files}
    except (ContentProfileError, RepositoryServiceError, ValueError) as exc:
        raise DocumentAuthorityHandoffError("rollback_source_unavailable") from exc
    if set(parsed_current) != expected_paths:
        raise DocumentAuthorityHandoffError("rollback_file_set_changed")
    markdown_by_block: dict[UUID, str] = {}
    for path, expected in parsed_expected.items():
        actual = parsed_current[path]
        if actual.content_id != expected.content_id or actual.kind != expected.kind:
            raise DocumentAuthorityHandoffError("rollback_content_identity_changed")
        if path.startswith("docs/"):
            if actual.frontmatter != expected.frontmatter or actual.markdown != expected.markdown:
                raise DocumentAuthorityHandoffError("rollback_root_metadata_changed")
            continue
        if actual.frontmatter != expected.frontmatter:
            raise DocumentAuthorityHandoffError("rollback_fragment_structure_changed")
        if actual.markdown != expected.markdown:
            markdown_by_block[actual.content_id] = actual.markdown
    owned_ids = set(markdown_by_block)
    if not owned_ids:
        return {}
    blocks = {
        block.id: block
        for block in Block.objects.select_related("current_revision").filter(
            id__in=owned_ids, source_document=document
        )
    }
    if set(blocks) != owned_ids or any(block.current_revision_id is None for block in blocks.values()):
        raise DocumentAuthorityHandoffError("rollback_legacy_block_unavailable")
    return markdown_by_block


@transaction.atomic
def transition_document_authority(
    *,
    workspace: Workspace,
    document_id: UUID,
    actor_id: UUID,
    target: str,
    reader_workspace: ResolvedWorkspace,
) -> str:
    if target not in {DocumentAuthorityMode.LEGACY, DocumentAuthorityMode.REPOSITORY}:
        raise DocumentAuthorityHandoffError("unsupported_authority_target")
    locked_workspace = Workspace.objects.select_for_update().get(pk=workspace.pk)
    repository = WorkspaceRepository.objects.select_for_update().filter(workspace=locked_workspace).first()
    if repository is None:
        raise DocumentAuthorityHandoffError("repository_missing")
    document = (
        Document.objects.select_for_update()
        .select_related("entity")
        .filter(
            id=document_id,
            tenant_id=locked_workspace.tenant_id,
            organization_id=cast(UUID, locked_workspace.organization_id),
            entity__workspace_id=locked_workspace.id,
        )
        .first()
    )
    if document is None:
        raise DocumentAuthorityHandoffError("document_unavailable")
    status = document_coexistence_status(
        workspace=locked_workspace, document=document, reader_workspace=reader_workspace
    )
    blockers = cast(list[str], status["handoff_blockers"])
    rollback_markdown: dict[UUID, str] | None = None
    if target == DocumentAuthorityMode.LEGACY and status["authority_state"] == DocumentAuthorityMode.REPOSITORY:
        rollback_markdown = prepare_rollback_markdown_projection(workspace=locked_workspace, document=document)
        blockers = [
            blocker
            for blocker in blockers
            if blocker not in {"content_copy_not_in_sync", "repository_read_projection_not_matched"}
        ]
    if blockers:
        raise DocumentAuthorityHandoffError(*blockers)
    authority = DocumentAuthority.objects.select_for_update().filter(
        workspace=locked_workspace, content_id=document.id
    ).first()
    if authority is None:
        raise DocumentAuthorityHandoffError("document_authority_state_unavailable")
    if authority.authority == target:
        return "already_at_target"
    if target == DocumentAuthorityMode.REPOSITORY and authority.authority != DocumentAuthorityMode.LEGACY:
        raise DocumentAuthorityHandoffError("unexpected_current_authority")

    exported = build_simple_document_export(document, verify_attachments=True)
    owned_fragment_ids = tuple(
        content_id for content_id in exported.copied_content_ids if content_id != document.id
    )
    fragment_states = list(
        DocumentAuthority.objects.select_for_update().filter(
            workspace=locked_workspace, content_id__in=owned_fragment_ids
        )
    )
    by_id = {state.content_id: state for state in fragment_states}
    if set(by_id) != set(owned_fragment_ids):
        raise DocumentAuthorityHandoffError("fragment_authority_state_unavailable")

    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL tekdocs.document_authority_transition = 'on'")
    if target == DocumentAuthorityMode.REPOSITORY:
        if authority.authority != DocumentAuthorityMode.LEGACY:
            raise DocumentAuthorityHandoffError("unexpected_current_authority")
        authority.authority = DocumentAuthorityMode.REPOSITORY
        authority.save(update_fields=("authority", "updated_at"))
        for fragment_id in owned_fragment_ids:
            fragment = by_id[fragment_id]
            if fragment.authority != DocumentAuthorityMode.LEGACY:
                raise DocumentAuthorityHandoffError("unexpected_fragment_authority")
            other_legacy_consumers = Document.objects.filter(
                placements__block_id=fragment_id,
                tenant_id=locked_workspace.tenant_id,
                organization_id=cast(UUID, locked_workspace.organization_id),
            ).exclude(id=document.id).exclude(
                id__in=DocumentAuthority.objects.filter(
                    workspace=locked_workspace, authority=DocumentAuthorityMode.REPOSITORY
                ).values("content_id")
            )
            if other_legacy_consumers.exists():
                raise DocumentAuthorityHandoffError("fragment_has_legacy_consumers")
            fragment.authority = DocumentAuthorityMode.REPOSITORY
            fragment.save(update_fields=("authority", "updated_at"))
    else:
        if rollback_markdown is None and (
            status["content_copy_state"] != "in_sync" or status["read_projection_state"] != "matched"
        ):
            raise DocumentAuthorityHandoffError("rollback_projection_not_matched")
        if authority.authority != DocumentAuthorityMode.REPOSITORY:
            raise DocumentAuthorityHandoffError("unexpected_current_authority")
        if rollback_markdown:
            blocks = {
                block.id: block
                for block in Block.objects.select_for_update(of=("self",))
                .select_related("current_revision")
                .filter(id__in=rollback_markdown)
            }
            for block_id, markdown in rollback_markdown.items():
                block = blocks.get(block_id)
                if block is None or block.current_revision is None:
                    raise DocumentAuthorityHandoffError("rollback_projection_not_matched")
                _append_block_revision(
                    block=block,
                    actor_id=actor_id,
                    markdown=markdown,
                    base_revision_id=cast(UUID, block.current_revision_id),
                )
            projected_status = document_coexistence_status(
                workspace=locked_workspace, document=document, reader_workspace=reader_workspace
            )
            if (
                projected_status["content_copy_state"] != "in_sync"
                or projected_status["read_projection_state"] != "matched"
            ):
                raise DocumentAuthorityHandoffError("rollback_projection_not_matched")
        for fragment_id in owned_fragment_ids:
            fragment = by_id[fragment_id]
            if fragment.authority == DocumentAuthorityMode.REPOSITORY:
                fragment.authority = DocumentAuthorityMode.LEGACY
                fragment.save(update_fields=("authority", "updated_at"))
        authority.authority = DocumentAuthorityMode.LEGACY
        authority.save(update_fields=("authority", "updated_at"))

    AuditEvent.objects.create(
        tenant=locked_workspace.tenant,
        actor_id=actor_id,
        action="document.authority_transitioned",
        entity_id=document.entity_id,
        metadata={"from": status["authority_state"], "to": target},
    )
    return "transitioned"
