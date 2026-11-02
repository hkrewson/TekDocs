"""Policy-scoped membership for ordinary cross-Workspace reuse handoff."""

from __future__ import annotations

from uuid import UUID

from .document_template_migration import TemplateMigrationError
from .library_authority_handoff import LibraryHandoffPlan, prepare_library_handoff, transition_library_authority
from .models import Block, Document, DocumentPlacement, Workspace, WorkspaceRepository
from .template_library_scope import editable_template_workspace_scope


def _shared_handoff_members(
    *, source_workspace: Workspace, source_document_id: UUID,
    destination_document_ids: tuple[UUID, ...], actor_id: UUID,
) -> list[tuple[Workspace, UUID]]:
    from apps.accounts.models import User
    from apps.accounts.policy import PermissionKey, accessible_organizations, require_installation_member

    from .document_migration_keys import content_key_authority_edges
    from .repository_service import _active_repository_transaction

    ids = set(destination_document_ids)
    if not ids or len(ids) != len(destination_document_ids) or len(ids) > 63 or source_document_id in ids:
        raise TemplateMigrationError("invalid_library_migration_group")
    with editable_template_workspace_scope(source_workspace, actor_id):
        if source_workspace.organization_id is not None or not Document.objects.filter(
            tenant_id=source_workspace.tenant_id, organization__isnull=True,
            entity__workspace=source_workspace, pk=source_document_id,
            archived_at__isnull=True,
        ).exists():
            raise TemplateMigrationError("library_source_unavailable")
    ids.add(source_document_id)
    member = require_installation_member(User.objects.get(pk=actor_id, is_active=True))
    organizations = accessible_organizations(member, PermissionKey.DOCUMENTS_EDIT)
    workspaces = [source_workspace, *Workspace.objects.filter(
        tenant_id=source_workspace.tenant_id, organization_id__in=organizations.values("id"),
    ).select_related("organization", "tenant").order_by("id")]
    members: list[tuple[Workspace, UUID]] = []
    for workspace in workspaces:
        with editable_template_workspace_scope(workspace, actor_id):
            members.extend((workspace, identity) for identity in Document.objects.filter(
                tenant_id=workspace.tenant_id, organization=workspace.organization,
                entity__workspace=workspace, id__in=ids, archived_at__isnull=True,
            ).values_list("id", flat=True))
    if {identity for _workspace, identity in members} != ids:
        raise TemplateMigrationError("library_destination_unavailable")
    active = _active_repository_transaction()
    if active is None:
        raise TemplateMigrationError("library_handoff_transaction_required")
    repositories = list(WorkspaceRepository.objects.filter(
        tenant_id=source_workspace.tenant_id, workspace_id__in={item[0].id for item in members},
    ).order_by("id"))
    if len(repositories) != len({item[0].id for item in members}):
        raise TemplateMigrationError("repository_missing")
    for repository in repositories:
        active.enlist(repository.id, write=False)
    members.sort(key=lambda item: (item[0].id, item[1]))
    # Git leases precede owner locks, matching writers. After all owner locks,
    # discover connectivity; the coordinator also checks global LIVE closure.
    for workspace, identity in members:
        with editable_template_workspace_scope(workspace, actor_id):
            list(Document.objects.select_for_update().filter(pk=identity, tenant_id=workspace.tenant_id))
            list(Block.objects.select_for_update().filter(
                tenant_id=workspace.tenant_id, source_document_id=identity,
            ).order_by("id"))
    edges: list[tuple[UUID, UUID]] = []
    for workspace in workspaces:
        local_ids = tuple(identity for location, identity in members if location.id == workspace.id)
        if not local_ids:
            continue
        with editable_template_workspace_scope(workspace, actor_id):
            edges.extend(DocumentPlacement.objects.filter(
                tenant_id=workspace.tenant_id, organization=workspace.organization,
                document_id__in=local_ids,
            ).exclude(block__source_document_id__isnull=True).values_list(
                "document_id", "block__source_document_id",
            ))
            edges.extend(content_key_authority_edges(workspace, local_ids))
    reachable = {source_document_id}
    while True:
        connected = {identity for left, right in edges if left in reachable or right in reachable
                     for identity in (left, right) if identity in ids}
        if connected.issubset(reachable):
            break
        reachable.update(connected)
    if reachable != ids:
        raise TemplateMigrationError("library_group_not_connected")
    return members


def prepare_shared_library_handoff(
    *, source_workspace: Workspace, source_document_id: UUID,
    destination_document_ids: tuple[UUID, ...], actor_id: UUID, target: str,
) -> LibraryHandoffPlan:
    return prepare_library_handoff(
        source_workspace=source_workspace, source_document_id=source_document_id,
        destination_document_ids=destination_document_ids, actor_id=actor_id, target=target,
        member_resolver=_shared_handoff_members,
    )


def transition_shared_library_authority(
    *, source_workspace: Workspace, source_document_id: UUID,
    destination_document_ids: tuple[UUID, ...], actor_id: UUID, target: str, plan_sha256: str,
) -> str:
    return transition_library_authority(
        source_workspace=source_workspace, source_document_id=source_document_id,
        destination_document_ids=destination_document_ids, actor_id=actor_id, target=target,
        plan_sha256=plan_sha256, member_resolver=_shared_handoff_members,
    )
