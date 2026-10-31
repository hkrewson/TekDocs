"""Explicit atomic authority handoff for a bounded shared live dependency group."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from django.db import connection, transaction
from django.db.models import Q

from .document_authority_handoff import (
    DocumentAuthorityHandoffError,
    _transition_document_authority_locked,
    prepare_rollback_markdown_projection,
)
from .document_migration_coexistence import document_coexistence_status
from .document_migration_export import build_simple_document_export
from .document_migration_keys import content_key_authority_edges
from .document_migration_publications import publication_migration_actor_allowed
from .documents import _append_block_revision
from .models import Block, Document, DocumentAuthority, DocumentPlacement, Workspace
from .publications import canonical_json
from .repository_service import pin_accepted_repository_for_publication
from .workspaces import ResolvedWorkspace

MAX_AUTHORITY_GROUP_DOCUMENTS = 64


@dataclass(frozen=True)
class AuthorityGroupPlan:
    document_ids: tuple[UUID, ...]
    base_commit: str
    plan_sha256: str


def _authorize_group(*, workspace: Workspace, actor_id: UUID, reader_workspace: ResolvedWorkspace) -> None:
    if (
        not publication_migration_actor_allowed(workspace=workspace, actor_id=actor_id)
        or reader_workspace.member.user.id != actor_id
        or reader_workspace.member.tenant.id != workspace.tenant_id
        or (reader_workspace.organization.id if reader_workspace.organization else None) != workspace.organization_id
    ):
        raise DocumentAuthorityHandoffError("publication_migration_not_authorized")


def _prepare_group(
    *,
    workspace: Workspace,
    document_ids: tuple[UUID, ...],
    actor_id: UUID,
    target: str,
    reader_workspace: ResolvedWorkspace,
    accepted_commit: str,
) -> AuthorityGroupPlan:
    if target not in {"repository", "legacy"}:
        raise DocumentAuthorityHandoffError("unsupported_authority_target")
    _authorize_group(workspace=workspace, actor_id=actor_id, reader_workspace=reader_workspace)
    ids = tuple(sorted(set(document_ids)))
    if not ids or len(ids) != len(document_ids) or len(ids) > MAX_AUTHORITY_GROUP_DOCUMENTS:
        raise DocumentAuthorityHandoffError("invalid_authority_group")
    scope = {"tenant_id": workspace.tenant_id, "organization_id": workspace.organization_id}
    documents = list(
        Document.objects.select_for_update(of=("self",))
        .filter(
            **scope,
            id__in=ids,
            entity__workspace=workspace,
        )
        .select_related("entity")
        .order_by("id")
    )
    if len(documents) != len(ids):
        raise DocumentAuthorityHandoffError("document_unavailable")
    # Placement writers lock their source block before insertion. Lock every
    # owned block before discovering inbound edges, including as-yet-unused ones.
    list(Block.objects.select_for_update().filter(**scope, source_document_id__in=ids).order_by("id"))
    edges = list(
        DocumentPlacement.objects.filter(
            **scope,
            document__entity__workspace=workspace,
            resolution_mode="live",
        )
        .filter(Q(document_id__in=ids) | Q(block__source_document_id__in=ids))
        .values_list("document_id", "block__source_document_id")
    )
    edges.extend(content_key_authority_edges(workspace, ids))
    if any(owner not in ids or consumer not in ids for consumer, owner in edges):
        raise DocumentAuthorityHandoffError("live_dependency_group_incomplete")
    modes = dict(
        DocumentAuthority.objects.select_for_update()
        .filter(
            workspace=workspace,
            content_id__in=ids,
        )
        .values_list("content_id", "authority")
    )
    if len(modes) != len(ids) or len(set(modes.values())) != 1:
        raise DocumentAuthorityHandoffError("mixed_group_authority")
    fingerprints = []
    rollback = target == "legacy" and set(modes.values()) == {"repository"}
    for document in documents:
        status = document_coexistence_status(workspace=workspace, document=document, reader_workspace=reader_workspace)
        blockers = cast(list[str], status["handoff_blockers"])
        if rollback:
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
            raise DocumentAuthorityHandoffError(*blockers)
        exported = build_simple_document_export(
            document,
            verify_attachments=True,
            allow_repository_divergence=rollback,
        )
        fingerprints.append(
            {
                "id": str(document.id),
                "authority": modes[document.id],
                "revisions": [(str(block), str(revision)) for block, revision in exported.blocks],
                "files": [(path, hashlib.sha256(source).hexdigest()) for path, source in exported.files],
                "attachments": [(str(identity), digest) for identity, digest in exported.attachment_digests],
                "history": cast(dict[str, object], status["publication_history"])["evidence_sha256"],
                "key_bindings": [(name, str(binding), str(target))
                                 for name, binding, target in exported.key_binding_ids],
                "key_sources": [(str(entity), str(block), str(revision), digest)
                                for entity, block, revision, digest in exported.key_content_sources],
                **(
                    {"template_enrollment": exported.template_enrollment_sha256}
                    if exported.template_enrollment_sha256 is not None
                    else {}
                ),
                **({"template_source": exported.template_source_sha256}
                   if exported.template_source_sha256 is not None else {}),
                "review": [document.review_state, document.review_content_sha256, str(document.last_reviewed_at)],
            }
        )
    digest = hashlib.sha256(
        canonical_json(
            {
                "workspace": str(workspace.id),
                "actor": str(actor_id),
                "target": target,
                "commit": accepted_commit,
                "documents": fingerprints,
                "live_edges": sorted((str(consumer), str(owner)) for consumer, owner in edges),
            }
        )
    ).hexdigest()
    return AuthorityGroupPlan(ids, accepted_commit, digest)


def prepare_authority_group(
    *,
    workspace: Workspace,
    document_ids: tuple[UUID, ...],
    actor_id: UUID,
    target: str,
    reader_workspace: ResolvedWorkspace,
) -> AuthorityGroupPlan:
    _authorize_group(workspace=workspace, actor_id=actor_id, reader_workspace=reader_workspace)
    with pin_accepted_repository_for_publication(workspace.repository.id) as repository, transaction.atomic():
        if repository.accepted_commit is None or repository.accepted_commit_id != repository.indexed_commit_id:
            raise DocumentAuthorityHandoffError("rollback_repository_not_ready")
        return _prepare_group(
            workspace=workspace,
            document_ids=document_ids,
            actor_id=actor_id,
            target=target,
            reader_workspace=reader_workspace,
            accepted_commit=repository.accepted_commit.object_id,
        )


def transition_authority_group(
    *,
    workspace: Workspace,
    document_ids: tuple[UUID, ...],
    actor_id: UUID,
    target: str,
    reader_workspace: ResolvedWorkspace,
    plan_sha256: str,
) -> str:
    _authorize_group(workspace=workspace, actor_id=actor_id, reader_workspace=reader_workspace)
    with pin_accepted_repository_for_publication(workspace.repository.id) as repository, transaction.atomic():
        if repository.accepted_commit is None or repository.accepted_commit_id != repository.indexed_commit_id:
            raise DocumentAuthorityHandoffError("rollback_repository_not_ready")
        plan = _prepare_group(
            workspace=workspace,
            document_ids=document_ids,
            actor_id=actor_id,
            target=target,
            reader_workspace=reader_workspace,
            accepted_commit=repository.accepted_commit.object_id,
        )
        if plan.plan_sha256 != plan_sha256:
            raise DocumentAuthorityHandoffError("preview_changed")
        states = list(DocumentAuthority.objects.filter(workspace=workspace, content_id__in=plan.document_ids))
        if all(state.authority == target for state in states):
            return "already_at_target"
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL tekdocs.document_authority_transition = 'on'")
        if target == "repository":
            # Roots first: SQL then sees every live consumer in repository
            # authority. Staged state is invisible outside this transaction.
            for state in states:
                state.authority = target
                state.save(update_fields=("authority", "updated_at"))
        else:
            documents = list(
                Document.objects.filter(
                    tenant_id=workspace.tenant_id,
                    organization=workspace.organization,
                    entity__workspace=workspace,
                    id__in=plan.document_ids,
                )
                .select_related("entity")
                .order_by("id")
            )
            # Project every owner before checking any composed consumer. This
            # also handles document dependency cycles between shared leaf blocks.
            for document in documents:
                projection = prepare_rollback_markdown_projection(workspace=workspace, document=document)
                for block in (
                    Block.objects.select_related("current_revision")
                    .filter(
                        tenant_id=workspace.tenant_id,
                        organization=workspace.organization,
                        source_document=document,
                        id__in=projection,
                    )
                    .order_by("id")
                ):
                    if block.current_revision_id is None:
                        raise DocumentAuthorityHandoffError("rollback_legacy_block_unavailable")
                    _append_block_revision(
                        block=block,
                        actor_id=actor_id,
                        markdown=projection[block.id],
                        base_revision_id=block.current_revision_id,
                    )
            for document in documents:
                status = document_coexistence_status(
                    workspace=workspace,
                    document=document,
                    reader_workspace=reader_workspace,
                )
                if status["content_copy_state"] != "in_sync" or status["read_projection_state"] != "matched":
                    raise DocumentAuthorityHandoffError("rollback_projection_not_matched")
        for document_id in plan.document_ids:
            _transition_document_authority_locked(
                workspace=workspace,
                document_id=document_id,
                actor_id=actor_id,
                target=target,
                reader_workspace=reader_workspace,
                _group_staged=target == "repository",
                _group_members=plan.document_ids,
            )
        return "transitioned"
