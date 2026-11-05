"""Atomic source/consumer coordinator with separately authorized membership."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from .models import Document, Workspace


class LibraryMemberResolver(Protocol):
    def __call__(
        self, *, source_workspace: Workspace, source_document_id: UUID,
        destination_document_ids: tuple[UUID, ...], actor_id: UUID,
    ) -> list[tuple[Workspace, UUID]]: ...


@dataclass(frozen=True, slots=True)
class LibraryHandoffPlan:
    source_document_id: UUID
    destination_document_ids: tuple[UUID, ...]
    target: str
    plan_sha256: str


def _prepare_library_handoff(
    *,
    source_workspace: Workspace,
    source_document_id: UUID,
    destination_document_ids: tuple[UUID, ...],
    actor_id: UUID,
    target: str,
    member_resolver: LibraryMemberResolver,
) -> tuple[LibraryHandoffPlan, list[tuple[Workspace, UUID]]]:
    from django.db import connection, transaction

    from apps.accounts.models import User

    from .document_migration_coexistence import document_coexistence_status
    from .document_migration_export import build_simple_document_export
    from .document_template_migration import TemplateMigrationError
    from .models import Block, DocumentAuthority, WorkspaceRepository
    from .publications import canonical_json
    from .template_library_scope import editable_template_workspace_scope
    from .workspaces import resolve_msp_workspace, resolve_organization_workspace

    if target not in {"repository", "legacy"}:
        raise TemplateMigrationError("unsupported_template_authority_target")
    members = member_resolver(
        source_workspace=source_workspace,
        source_document_id=source_document_id,
        destination_document_ids=destination_document_ids,
        actor_id=actor_id,
    )
    actor = User.objects.get(pk=actor_id, is_active=True)
    proofs = []
    with transaction.atomic():
        for workspace, document_id in members:
            with editable_template_workspace_scope(workspace, actor_id):
                document = (
                    Document.objects.select_for_update(of=("self",))
                    .select_related("entity")
                    .get(
                        tenant_id=workspace.tenant_id,
                        organization=workspace.organization,
                        entity__workspace=workspace,
                        pk=document_id,
                    )
                )
                list(
                    Block.objects.select_for_update()
                    .filter(
                        tenant_id=workspace.tenant_id,
                        source_document=document,
                    )
                    .order_by("id")
                )
                authority = DocumentAuthority.objects.select_for_update().get(
                    workspace=workspace,
                    tenant_id=workspace.tenant_id,
                    content_id=document.id,
                )
                repository = (
                    WorkspaceRepository.objects.select_for_update(of=("self",))
                    .select_related("accepted_commit")
                    .get(
                        tenant_id=workspace.tenant_id,
                        workspace=workspace,
                    )
                )
                if repository.accepted_commit is None or repository.accepted_commit_id != repository.indexed_commit_id:
                    raise TemplateMigrationError("repository_not_current")
                reader = (
                    resolve_organization_workspace(actor, entity_id=workspace.organization.entity_id)
                    if workspace.organization
                    else resolve_msp_workspace(actor)
                )
                status = document_coexistence_status(workspace=workspace, document=document, reader_workspace=reader)
                blockers = list(cast(list[str], status["handoff_blockers"]))
                rollback = target == "legacy" and authority.authority == "repository"
                if rollback:
                    from .document_authority_handoff import prepare_rollback_markdown_projection

                    prepare_rollback_markdown_projection(workspace=workspace, document=document)
                    blockers = [
                        code
                        for code in blockers
                        if code
                        not in {
                            "content_copy_not_in_sync",
                            "repository_read_projection_not_matched",
                            "managed_file_retention_limit",
                            "template_history_git_custody_unavailable",
                        }
                    ]
                if blockers:
                    raise TemplateMigrationError(", ".join(blockers))
                exported = build_simple_document_export(
                    document,
                    verify_attachments=True,
                    allow_repository_divergence=rollback,
                )
                proofs.append(
                    {
                        "document": str(document.id),
                        "workspace": str(workspace.id),
                        "authority": authority.authority,
                        "commit": repository.accepted_commit.object_id,
                        "files": [(path, hashlib.sha256(source).hexdigest()) for path, source in exported.files],
                        "enrollment": exported.template_enrollment_sha256,
                        "source": exported.template_source_sha256,
                        "history": status["publication_history"],
                        "review": [
                            document.review_state,
                            document.review_content_sha256,
                            str(document.last_reviewed_at),
                        ],
                    }
                )
    # Owner locks above serialize new placement/binding writers. The boolean-only
    # SQL check includes inaccessible consumers without exposing their identities.
    with editable_template_workspace_scope(source_workspace, actor_id), connection.cursor() as cursor:
        cursor.execute("SELECT tekdocs_library_cohort_closed(%s, %s::uuid[])", [
            source_workspace.tenant_id, [identity for _workspace, identity in members],
        ])
        if not cursor.fetchone()[0]:
            raise TemplateMigrationError("library_live_dependency_group_incomplete")
        cursor.execute("SELECT tekdocs_library_pinned_cohort_closed(%s, %s::uuid[], %s)", [
            source_workspace.tenant_id, [identity for _workspace, identity in members], target,
        ])
        if not cursor.fetchone()[0]:
            raise TemplateMigrationError("library_pinned_dependency_group_incomplete")
    return LibraryHandoffPlan(
        source_document_id,
        tuple(sorted(destination_document_ids)),
        target,
        hashlib.sha256(canonical_json({"actor": str(actor_id), "target": target, "members": proofs})).hexdigest(),
    ), members


def prepare_library_handoff(
    *,
    source_workspace: Workspace,
    source_document_id: UUID,
    destination_document_ids: tuple[UUID, ...],
    actor_id: UUID,
    target: str,
    member_resolver: LibraryMemberResolver,
) -> LibraryHandoffPlan:
    from .repository_service import coordinated_repository_transaction

    with coordinated_repository_transaction():
        plan, _members = _prepare_library_handoff(
            source_workspace=source_workspace,
            source_document_id=source_document_id,
            destination_document_ids=destination_document_ids,
            actor_id=actor_id,
            target=target,
            member_resolver=member_resolver,
        )
        return plan


def transition_library_authority(
    *,
    source_workspace: Workspace,
    source_document_id: UUID,
    destination_document_ids: tuple[UUID, ...],
    actor_id: UUID,
    target: str,
    member_resolver: LibraryMemberResolver,
    plan_sha256: str,
) -> str:
    from django.db import connection

    from apps.accounts.models import User

    from .document_authority_handoff import _transition_document_authority_locked
    from .document_template_migration import TemplateMigrationError
    from .models import DocumentAuthority
    from .repository_service import coordinated_repository_transaction
    from .template_library_scope import editable_template_workspace_scope
    from .workspaces import resolve_msp_workspace, resolve_organization_workspace

    with coordinated_repository_transaction():
        plan, members = _prepare_library_handoff(
            source_workspace=source_workspace,
            source_document_id=source_document_id,
            destination_document_ids=destination_document_ids,
            actor_id=actor_id,
            target=target,
            member_resolver=member_resolver,
        )
        if plan.plan_sha256 != plan_sha256:
            raise TemplateMigrationError("preview_changed")
        actor = User.objects.get(pk=actor_id, is_active=True)
        changed = False
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL tekdocs.document_authority_transition = 'on'")
        for workspace, document_id in members:
            with editable_template_workspace_scope(workspace, actor_id):
                state = DocumentAuthority.objects.get(
                    tenant_id=workspace.tenant_id,
                    workspace=workspace,
                    content_id=document_id,
                )
                if state.authority != target:
                    changed = True
                    if target == "repository":
                        state.authority = target
                        state.save(update_fields=("authority", "updated_at"))
        if not changed:
            return "already_at_target"
        if target == "legacy":
            from .document_authority_handoff import prepare_rollback_markdown_projection
            from .documents import _append_block_revision
            from .models import Block

            # Every owned body is restored before verifying any dependent client.
            for workspace, document_id in members:
                with editable_template_workspace_scope(workspace, actor_id):
                    document = Document.objects.get(tenant_id=workspace.tenant_id, pk=document_id)
                    projection = prepare_rollback_markdown_projection(workspace=workspace, document=document)
                    for block in Block.objects.filter(
                        tenant_id=workspace.tenant_id,
                        source_document=document,
                        id__in=projection,
                    ).order_by("id"):
                        if block.current_revision_id is None:
                            raise TemplateMigrationError("rollback_legacy_block_unavailable")
                        _append_block_revision(
                            block=block,
                            actor_id=actor_id,
                            markdown=projection[block.id],
                            base_revision_id=block.current_revision_id,
                        )
        for workspace, document_id in members:
            with editable_template_workspace_scope(workspace, actor_id):
                reader = (
                    resolve_organization_workspace(actor, entity_id=workspace.organization.entity_id)
                    if workspace.organization
                    else resolve_msp_workspace(actor)
                )
                _transition_document_authority_locked(
                    workspace=workspace,
                    document_id=document_id,
                    actor_id=actor_id,
                    target=target,
                    reader_workspace=reader,
                    _group_staged=target == "repository",
                    _group_members=tuple(identity for _workspace, identity in members),
                )
        return "transitioned"
