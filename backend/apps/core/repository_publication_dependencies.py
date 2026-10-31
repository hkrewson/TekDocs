"""Freeze permission-visible record dependencies for retained Git publications."""

from __future__ import annotations

import hashlib
from typing import Any

from apps.accounts.models import User
from apps.accounts.policy import DataAudience, InstallationMemberContext, entity_visible_to_audience

from .content_index_models import ContentNode
from .document_key_freeze import KeyFreezeConflict, freeze_document_keys, verify_frozen_field_keys
from .document_key_models import DocumentKeyBinding
from .document_keys import key_targets_in_markdown
from .document_migration_keys import DocumentMigrationKeyError, portable_document_keys
from .entity_mentions import resolve_entity_mentions
from .models import Document, Entity, PublicationAudience, WorkspaceRepository
from .publications import MAX_PUBLICATION_MARKDOWN_BYTES
from .rendering import RenderedEntityMention, entity_ids_in_markdown
from .workspaces import resolve_msp_workspace, resolve_organization_workspace


class RepositoryPublicationDependencyError(RuntimeError):
    """A current reference cannot be frozen under the caller's permission scope."""


def freeze_repository_entity_cards(
    *,
    repository: WorkspaceRepository,
    markdown: str,
    audience: str,
    actor: User,
    member: InstallationMemberContext,
) -> list[RenderedEntityMention]:
    """Freeze only permission-visible, exact-Workspace entity display cards."""

    requested = entity_ids_in_markdown(markdown)
    if not requested:
        return []
    if len(requested) > 200:
        raise RepositoryPublicationDependencyError("Repository publication preflight blocked: repository.entity.limit")
    organization = repository.workspace.organization
    workspace = (
        resolve_organization_workspace(actor, entity_id=organization.entity_id)
        if organization is not None
        else resolve_msp_workspace(actor)
    )
    projections = resolve_entity_mentions(workspace=workspace, markdown=markdown, lock=True)
    if set(projections) != {str(entity_id) for entity_id in requested}:
        raise RepositoryPublicationDependencyError(
            "Repository publication preflight blocked: repository.entity.unavailable"
        )
    records = {
        entity.id: entity
        for entity in Entity.objects.filter(
            id__in=requested,
            tenant_id=repository.tenant_id,
            workspace_id=repository.workspace_id,
            organization=organization,
            archived_at__isnull=True,
        )
    }
    data_audience = (
        DataAudience.CLIENT_PORTAL if audience == PublicationAudience.CLIENT_VISIBLE else DataAudience.MSP_STAFF
    )
    if len(records) != len(requested) or any(
        not entity_visible_to_audience(member, records[entity_id], audience=data_audience, organization=organization)
        for entity_id in requested
        if entity_id in records
    ):
        raise RepositoryPublicationDependencyError(
            "Repository publication preflight blocked: repository.entity.unavailable"
        )
    return [
        {
            "id": projections[str(entity_id)]["id"],
            "display_name": projections[str(entity_id)]["display_name"],
            "entity_type": projections[str(entity_id)]["entity_type"],
            "workspace_label": projections[str(entity_id)]["workspace_label"],
        }
        for entity_id in sorted(requested)
    ]


def freeze_repository_key_snapshot(
    *,
    repository: WorkspaceRepository,
    node: ContentNode,
    document: Document | None,
    markdown: str,
    audience: str,
    actor: User,
    signed_at: str,
) -> dict[str, Any] | None:
    """Freeze only portable field keys whose authored bindings match the live owner."""
    if not key_targets_in_markdown(markdown):
        return None
    if document is None:
        raise RepositoryPublicationDependencyError(
            "Repository publication preflight blocked: repository.key.unavailable"
        )
    # Hold active binding identities stable through portable parity and resolution.
    list(DocumentKeyBinding.objects.select_for_update().filter(document=document, archived_at__isnull=True))
    try:
        bindings, _identities = portable_document_keys(document, markdown)
        if bindings != node.frontmatter.get("key_bindings", {}):
            raise RepositoryPublicationDependencyError(
                "Repository publication preflight blocked: repository.key.binding_mismatch"
            )
        organization = repository.workspace.organization
        workspace = (
            resolve_organization_workspace(actor, entity_id=organization.entity_id)
            if organization is not None
            else resolve_msp_workspace(actor)
        )
        frozen = freeze_document_keys(
            workspace=workspace,
            document=document,
            markdown=markdown,
            audience=(
                DataAudience.CLIENT_PORTAL if audience == PublicationAudience.CLIENT_VISIBLE else DataAudience.MSP_STAFF
            ),
            resolved_at=signed_at,
            lock=True,
        )
    except (DocumentMigrationKeyError, KeyFreezeConflict) as exc:
        raise RepositoryPublicationDependencyError(
            "Repository publication preflight blocked: repository.key.unavailable"
        ) from exc
    if len(frozen.markdown.encode("utf-8")) > MAX_PUBLICATION_MARKDOWN_BYTES:
        raise RepositoryPublicationDependencyError("Repository publication preflight blocked: repository.key.limit")
    snapshot = {
        "markdown": frozen.markdown,
        "sha256": hashlib.sha256(frozen.markdown.encode("utf-8")).hexdigest(),
        "records": list(frozen.manifest_records),
    }
    if not verify_frozen_field_keys(markdown, snapshot):
        raise RepositoryPublicationDependencyError(
            "Repository publication preflight blocked: repository.key.unavailable"
        )
    return snapshot
