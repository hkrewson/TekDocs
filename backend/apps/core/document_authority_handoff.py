"""Explicit, parity-gated authority transitions for imported documents."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from django.db import connection, transaction

from .document_migration_coexistence import document_coexistence_status
from .document_migration_export import build_simple_document_export
from .models import AuditEvent, Document, DocumentAuthority, DocumentAuthorityMode, Workspace, WorkspaceRepository
from .workspaces import ResolvedWorkspace


class DocumentAuthorityHandoffError(ValueError):
    def __init__(self, *codes: str) -> None:
        self.codes = tuple(sorted(set(codes)))
        super().__init__(", ".join(self.codes))


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
        if status["content_copy_state"] != "in_sync" or status["read_projection_state"] != "matched":
            raise DocumentAuthorityHandoffError("rollback_projection_not_matched")
        if authority.authority != DocumentAuthorityMode.REPOSITORY:
            raise DocumentAuthorityHandoffError("unexpected_current_authority")
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
