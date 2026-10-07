"""Read-only mapping of unambiguous legacy document entity references."""

from __future__ import annotations

from django.db.models import Q

from .models import Document, EntityLink, EntityLinkType
from .relationships import ENTITY_TYPE_VIEW_PERMISSION


class DocumentMigrationRelationshipError(ValueError):
    pass


def portable_document_entity_references(document: Document) -> list[dict[str, str]]:
    """Map outgoing, supported exact-workspace references to neutral mentions."""

    links = (
        EntityLink.objects.filter(archived_at__isnull=True)
        .filter(Q(source_id=document.entity_id) | Q(target_id=document.entity_id))
        .select_related("source", "target")
        .order_by("id")
    )
    targets: set[str] = set()
    for link in links:
        target = link.target
        if (
            link.tenant_id != document.tenant_id
            or link.source_id != document.entity_id
            or link.source.tenant_id != document.tenant_id
            or link.source.organization_id != document.organization_id
            or link.source.workspace_id != document.entity.workspace_id
            or link.link_type != EntityLinkType.REFERENCES
            or link.metadata != {}
            or target.tenant_id != document.tenant_id
            or target.organization_id != document.organization_id
            or target.workspace_id != document.entity.workspace_id
            or target.entity_type not in ENTITY_TYPE_VIEW_PERMISSION
            or target.archived_at is not None
        ):
            raise DocumentMigrationRelationshipError("relationship_mapping_required")
        targets.add(str(target.id))
    return [{"id": target_id, "relationship": "mention"} for target_id in sorted(targets)]
