from __future__ import annotations

from typing import TypedDict

from .relationships import entities_for_mentions
from .rendering import entity_ids_in_markdown
from .workspaces import ResolvedWorkspace


class EntityMention(TypedDict):
    id: str
    display_name: str
    entity_type: str
    workspace_label: str


def resolve_entity_mentions(*, workspace: ResolvedWorkspace, markdown: str) -> dict[str, EntityMention]:
    entity_ids = entity_ids_in_markdown(markdown)
    records = entities_for_mentions(workspace=workspace, entity_ids=entity_ids)
    mentions: dict[str, EntityMention] = {}
    for entity in records:
        organization = entity.organization
        if organization is not None:
            workspace_label = organization.entity.display_name
        elif entity.entity_type == "organization":
            workspace_label = "MSP organization directory"
        else:
            workspace_label = workspace.member.tenant.name
        mentions[str(entity.id)] = {
            "id": str(entity.id),
            "display_name": entity.display_name,
            "entity_type": entity.entity_type,
            "workspace_label": workspace_label,
        }
    return mentions
