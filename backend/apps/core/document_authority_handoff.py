"""Explicit, parity-gated authority transitions for imported documents."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from django.db import connection, transaction
from django.db.models import Q

from .content_profile import ContentProfileError
from .document_migration_coexistence import document_coexistence_status
from .document_migration_export import build_simple_document_export
from .document_migration_keys import content_key_authority_edges
from .document_reversible_writes import ReversibleShapeError, reversible_markdown_projection
from .documents import _append_block_revision
from .models import (
    AuditEvent,
    Block,
    Document,
    DocumentAuthority,
    DocumentAuthorityMode,
    DocumentPlacement,
    Workspace,
    WorkspaceRepository,
)
from .repository_service import (
    RepositoryServiceError,
    pin_accepted_repository_for_publication,
    read_accepted_repository_markdown_files,
)
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
        markdown_by_block = reversible_markdown_projection(dict(exported.files), dict(files))
    except ReversibleShapeError as exc:
        raise DocumentAuthorityHandoffError(str(exc)) from exc
    except (ContentProfileError, RepositoryServiceError, ValueError) as exc:
        raise DocumentAuthorityHandoffError("rollback_source_unavailable") from exc
    owned_ids = set(markdown_by_block)
    if not owned_ids:
        return {}
    blocks = {
        block.id: block
        for block in Block.objects.select_related("current_revision").filter(id__in=owned_ids, source_document=document)
    }
    if set(blocks) != owned_ids or any(block.current_revision_id is None for block in blocks.values()):
        raise DocumentAuthorityHandoffError("rollback_legacy_block_unavailable")
    return markdown_by_block


def transition_document_authority(
    *,
    workspace: Workspace,
    document_id: UUID,
    actor_id: UUID,
    target: str,
    reader_workspace: ResolvedWorkspace,
) -> str:
    repository = WorkspaceRepository.objects.filter(workspace=workspace, tenant_id=workspace.tenant_id).first()
    if repository is None:
        raise DocumentAuthorityHandoffError("repository_missing")
    try:
        # Same order as writers: Git lock, repository row, then owner rows.
        # Nested snapshot reads take compatible shared locks while this pin lives.
        with pin_accepted_repository_for_publication(repository.id):
            return _transition_document_authority_locked(
                workspace=workspace,
                document_id=document_id,
                actor_id=actor_id,
                target=target,
                reader_workspace=reader_workspace,
            )
    except RepositoryServiceError as exc:
        raise DocumentAuthorityHandoffError("rollback_repository_not_ready") from exc


@transaction.atomic
def _transition_document_authority_locked(
    *,
    workspace: Workspace,
    document_id: UUID,
    actor_id: UUID,
    target: str,
    reader_workspace: ResolvedWorkspace,
    _group_staged: bool = False,
    _group_members: tuple[UUID, ...] = (),
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
    key_edges = content_key_authority_edges(locked_workspace, (document.id,))
    members = set(_group_members) if _group_members else {document.id}
    neighbors = {identity for edge in key_edges for identity in edge} - members
    same_target = set(DocumentAuthority.objects.filter(
        workspace=locked_workspace, content_id__in=neighbors, authority=target,
    ).values_list("content_id", flat=True))
    if neighbors != same_target:
        raise DocumentAuthorityHandoffError("live_dependency_group_incomplete")
    from .document_migration_publications import publication_migration_actor_allowed
    from .models import DocumentPublication

    if DocumentPublication.objects.filter(document=document).exists() and (
        not publication_migration_actor_allowed(workspace=locked_workspace, actor_id=actor_id)
        or reader_workspace.member.user.id != actor_id
        or reader_workspace.member.tenant.id != locked_workspace.tenant_id
        or (reader_workspace.organization.id if reader_workspace.organization else None)
        != locked_workspace.organization_id
    ):
        raise DocumentAuthorityHandoffError("publication_migration_not_authorized")
    status = document_coexistence_status(
        workspace=locked_workspace, document=document, reader_workspace=reader_workspace
    )
    if target == DocumentAuthorityMode.LEGACY:
        members = set(_group_members) if _group_members else {document.id}
        edges = DocumentPlacement.objects.filter(
            tenant_id=locked_workspace.tenant_id, organization=locked_workspace.organization,
            document__entity__workspace=locked_workspace, resolution_mode="live",
        ).filter(Q(document=document) | Q(block__source_document=document))
        neighbors = {identity for edge in edges.values_list("document_id", "block__source_document_id")
                     for identity in edge} - members
        outside_repository = DocumentAuthority.objects.filter(
            workspace=locked_workspace, content_id__in=neighbors, authority=DocumentAuthorityMode.REPOSITORY,
        ).exists()
        if outside_repository:
            raise DocumentAuthorityHandoffError("live_dependency_group_incomplete")
    if target == DocumentAuthorityMode.REPOSITORY:
        live_owners = set(document.placements.filter(resolution_mode="live").exclude(
            block__source_document_id=document.id,
        ).values_list("block__source_document_id", flat=True))
        retired_owners = set(DocumentAuthority.objects.filter(
            workspace=locked_workspace, content_id__in=live_owners, authority=DocumentAuthorityMode.REPOSITORY,
        ).values_list("content_id", flat=True))
        # A foreign owner is allowed only through the exact validated template
        # enrollment. Its public root authority is SELECT-only under client RLS.
        from .document_template_migration import template_enrollment_evidence

        evidence = template_enrollment_evidence(document)
        if evidence is not None and evidence.source_document_id in live_owners:
            source = Document.objects.get(tenant_id=document.tenant_id, pk=evidence.source_document_id)
            if DocumentAuthority.objects.filter(
                tenant_id=document.tenant_id, workspace_id=source.entity.workspace_id,
                content_id=source.id, authority=DocumentAuthorityMode.REPOSITORY,
            ).exists():
                retired_owners.add(source.id)
        if live_owners != retired_owners:
            raise DocumentAuthorityHandoffError("live_dependency_group_incomplete")
    blockers = cast(list[str], status["handoff_blockers"])
    rollback_markdown: dict[UUID, str] | None = None
    if target == DocumentAuthorityMode.LEGACY and status["authority_state"] == DocumentAuthorityMode.REPOSITORY:
        rollback_markdown = prepare_rollback_markdown_projection(workspace=locked_workspace, document=document)
        blockers = [
            blocker
            for blocker in blockers
            # Snapshot capacity gates promotion/publication, not lossless return
            # to retained legacy custody after files were added under Git.
            if blocker not in {
                "content_copy_not_in_sync", "repository_read_projection_not_matched", "managed_file_retention_limit",
                "template_history_git_custody_unavailable"
            }
        ]
    if blockers:
        raise DocumentAuthorityHandoffError(*blockers)
    authority = (
        DocumentAuthority.objects.select_for_update().filter(workspace=locked_workspace, content_id=document.id).first()
    )
    if authority is None:
        raise DocumentAuthorityHandoffError("document_authority_state_unavailable")
    if authority.authority == target and not _group_staged:
        return "already_at_target"
    if (target == DocumentAuthorityMode.REPOSITORY and authority.authority != DocumentAuthorityMode.LEGACY
        and not _group_staged):
        raise DocumentAuthorityHandoffError("unexpected_current_authority")

    exported = build_simple_document_export(document, verify_attachments=True)
    owned_fragment_ids = tuple(content_id for content_id in exported.copied_content_ids if content_id != document.id)
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
        if authority.authority != DocumentAuthorityMode.LEGACY and not _group_staged:
            raise DocumentAuthorityHandoffError("unexpected_current_authority")
        authority.authority = DocumentAuthorityMode.REPOSITORY
        authority.save(update_fields=("authority", "updated_at"))
        for fragment_id in owned_fragment_ids:
            fragment = by_id[fragment_id]
            if fragment.authority != DocumentAuthorityMode.LEGACY:
                raise DocumentAuthorityHandoffError("unexpected_fragment_authority")
            other_legacy_consumers = (
                Document.objects.filter(
                    placements__block_id=fragment_id,
                    placements__resolution_mode="live",
                    tenant_id=locked_workspace.tenant_id,
                    organization_id=cast(UUID, locked_workspace.organization_id),
                )
                .exclude(id=document.id)
                .exclude(
                    id__in=DocumentAuthority.objects.filter(
                        workspace=locked_workspace, authority=DocumentAuthorityMode.REPOSITORY
                    ).values("content_id")
                )
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

    from .document_migration_publications import assess_retained_publications

    history_before = cast(dict[str, object], status["publication_history"])["evidence_sha256"]
    if assess_retained_publications(workspace=locked_workspace, document=document)["evidence_sha256"] != history_before:
        raise DocumentAuthorityHandoffError("publication_history_changed")
    AuditEvent.objects.create(
        tenant=locked_workspace.tenant,
        actor_id=actor_id,
        action="document.authority_transitioned",
        entity_id=document.entity_id,
        metadata={
            "from": "legacy" if _group_staged else status["authority_state"],
            "to": target, "publication_history_sha256": history_before,
        },
    )
    return "transitioned"
