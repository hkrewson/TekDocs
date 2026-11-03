"""Git-owned binding inputs for the existing field/content resolution engine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import Q, QuerySet

from apps.accounts.policy import DataAudience, PermissionKey, context_has_permission, entity_visible_to_audience

from .document_key_fields import ADDRESSABLE_ENTITY_TYPES
from .models import Block, ContentNode, Document, DocumentKeyBinding, Entity, WorkspaceRepository
from .workspaces import ResolvedWorkspace


def canonical_key_bindings(bindings: Mapping[str, object]) -> dict[str, str]:
    """Use one UUID representation without rewriting the retained Git source."""
    return {name: str(UUID(str(target))) for name, target in bindings.items()}


def native_fragment_nodes(repository: WorkspaceRepository) -> QuerySet[ContentNode]:
    """Exclude legacy Block identities, including copied, archived and rolled-back shadows."""
    legacy_ids = Block.objects.filter(
        tenant_id=repository.tenant_id, organization=repository.workspace.organization,
        entity__workspace_id=repository.workspace_id,
    ).values('id')
    return ContentNode.objects.filter(
        repository=repository, tenant_id=repository.tenant_id, workspace_id=repository.workspace_id,
        organization=repository.workspace.organization, kind='fragment',
        indexed_commit_id=repository.accepted_commit_id,
    ).exclude(content_id__in=legacy_ids).filter(
        ~Q(frontmatter__properties__lifecycle='archived') | Q(frontmatter__properties__lifecycle__isnull=True),
    )


@dataclass(frozen=True, slots=True)
class RepositoryKeyBinding:
    target_entity_id: UUID
    target_entity: Entity | None
    updated_at: datetime
    fragment_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class RepositoryKeyContext:
    repository: WorkspaceRepository
    bindings: dict[str, str]
    updated_at: datetime

    def selected_bindings(self, names: set[str], *, lock: bool) -> dict[str, RepositoryKeyBinding]:
        targets = {UUID(target) for name, target in self.bindings.items() if name in names}
        entities = Entity.objects.filter(
            id__in=targets, tenant_id=self.repository.tenant_id,
            workspace_id=self.repository.workspace_id,
            organization=self.repository.workspace.organization,
        ).exclude(entity_type='document_block').order_by('id')
        if lock:
            entities = entities.select_for_update()
        by_entity = {entity.id: entity for entity in entities}
        fragments = set(native_fragment_nodes(self.repository).filter(
            content_id__in=targets,
        ).values_list('content_id', flat=True))
        return {
            name: RepositoryKeyBinding(
                UUID(target), by_entity.get(UUID(target)), self.updated_at,
                UUID(target) if UUID(target) in fragments and UUID(target) not in by_entity else None,
            )
            for name, target in self.bindings.items()
            if name in names and (UUID(target) in by_entity or UUID(target) in fragments)
        }


def key_context_for_node(
    *, repository: WorkspaceRepository, node: ContentNode, document: Document | None,
) -> Document | RepositoryKeyContext | None:
    if (node.kind != 'document' or repository.accepted_commit_id != repository.indexed_commit_id
            or node.indexed_commit_id != repository.accepted_commit_id):
        return None
    bindings = node.frontmatter.get('key_bindings', {})
    if document is not None:
        if document.archived_at is not None:
            return None
        active = {name: str(target) for name, target in DocumentKeyBinding.objects.filter(
            document=document, archived_at__isnull=True,
        ).values_list('name', 'target_entity_id')}
        return document if active == bindings else None
    if repository.accepted_commit is None or Document.objects.filter(
        id=node.content_id, tenant_id=repository.tenant_id,
        organization=repository.workspace.organization, entity__workspace_id=repository.workspace_id,
    ).exists():
        return None
    return RepositoryKeyContext(repository, canonical_key_bindings(bindings), repository.accepted_commit.created_at)


def validate_native_key_targets(
    *, workspace: ResolvedWorkspace, repository: WorkspaceRepository, bindings: dict[str, str],
) -> None:
    """Only visible exact-Workspace records or current native fragments may be declared."""
    from .content_authoring import ContentAuthoringError

    context = (
        RepositoryKeyContext(repository, canonical_key_bindings(bindings), repository.accepted_commit.created_at)
        if repository.accepted_commit is not None else None
    )
    selected = context.selected_bindings(set(bindings), lock=False) if context else {}
    for name in bindings:
        binding = selected.get(name)
        if binding is None:
            raise ContentAuthoringError('Key target is unavailable in this Workspace')
        if binding.fragment_id is not None:
            node = ContentNode.objects.get(repository=repository, content_id=binding.fragment_id)
            if (node.frontmatter.get('properties', {}).get('lifecycle') == 'archived'
                    or not context_has_permission(
                        workspace.member, PermissionKey.DOCUMENTS_VIEW, organization=workspace.organization,
                    )):
                raise ContentAuthoringError('Key target is unavailable in this Workspace')
        elif (
            binding.target_entity is None
            or binding.target_entity.entity_type not in ADDRESSABLE_ENTITY_TYPES
            or not entity_visible_to_audience(
                workspace.member, binding.target_entity, audience=DataAudience.MSP_STAFF,
                organization=workspace.organization,
            )
        ):
            raise ContentAuthoringError('Key target is unavailable in this Workspace')
