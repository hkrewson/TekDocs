from __future__ import annotations

from typing import TypedDict

from django.db.models import Q

from apps.accounts.policy import (
    InstallationMemberContext,
    PermissionKey,
    accessible_organizations,
    context_has_permission,
)

from .models import DocumentPlacement, PlacementResolutionMode


class ReuseAudience(TypedDict):
    document_id: str
    document_title: str
    workspace_kind: str
    workspace_id: str | None
    workspace_name: str
    relationship: str
    resolution_mode: str
    will_update: bool


class ReuseImpact(TypedDict):
    block_id: str
    block_name: str
    revision_id: str
    revision_number: int
    checksum: str
    markdown: str
    can_edit_shared: bool
    can_detach: bool
    requires_mfa: bool
    audiences: list[ReuseAudience]
    live_audience_count: int
    pinned_audience_count: int
    truncated: bool


def _audience(
    *,
    placement: DocumentPlacement,
    workspace_kind: str,
    workspace_id: str | None,
    workspace_name: str,
    relationship: str,
) -> ReuseAudience:
    return {
        "document_id": str(placement.document.entity_id),
        "document_title": placement.document.entity.display_name,
        "workspace_kind": workspace_kind,
        "workspace_id": workspace_id,
        "workspace_name": workspace_name,
        "relationship": relationship,
        "resolution_mode": placement.resolution_mode,
        "will_update": placement.resolution_mode == PlacementResolutionMode.LIVE,
    }


def reuse_impact_for_placement(*, context: InstallationMemberContext, placement: DocumentPlacement) -> ReuseImpact:
    organization_ids = list(
        accessible_organizations(context, PermissionKey.DOCUMENTS_VIEW).values_list("id", flat=True)
    )
    can_view_msp = context_has_permission(context, PermissionKey.DOCUMENTS_VIEW)
    visibility = Q(document__organization_id__in=organization_ids) | Q(
        document__organization__isnull=True,
        document__listing_references__organization_id__in=organization_ids,
        document__listing_references__archived_at__isnull=True,
    )
    if can_view_msp:
        visibility |= Q(document__organization__isnull=True)

    uses = list(
        DocumentPlacement.objects.filter(
            tenant=context.tenant,
            block_id=placement.block_id,
            document__archived_at__isnull=True,
        )
        .filter(visibility)
        .select_related(
            "document",
            "document__entity",
            "document__organization",
            "document__organization__entity",
            "block",
            "block__entity",
            "block__current_revision",
            "pinned_revision",
        )
        .prefetch_related("document__listing_references__organization__entity")
        .distinct()
        .order_by("document__entity__display_name", "document_id", "position", "id")[:501]
    )
    truncated = len(uses) > 500
    audiences: list[ReuseAudience] = []
    for use in uses[:500]:
        relationship = (
            "source"
            if use.parent_id is None and use.position == 0 and use.block_id == placement.block_id
            else "placement"
        )
        if use.document.organization is not None and use.document.organization_id in organization_ids:
            audiences.append(
                _audience(
                    placement=use,
                    workspace_kind="organization",
                    workspace_id=str(use.document.organization.entity_id),
                    workspace_name=use.document.organization.entity.display_name,
                    relationship=relationship,
                )
            )
        elif use.document.organization is None and can_view_msp:
            audiences.append(
                _audience(
                    placement=use,
                    workspace_kind="msp",
                    workspace_id=None,
                    workspace_name=context.tenant.name,
                    relationship=relationship,
                )
            )
        if use.document.organization is None:
            for reference in use.document.listing_references.all():
                if reference.archived_at is None and reference.organization_id in organization_ids:
                    audiences.append(
                        _audience(
                            placement=use,
                            workspace_kind="organization",
                            workspace_id=str(reference.organization.entity_id),
                            workspace_name=reference.organization.entity.display_name,
                            relationship="listing",
                        )
                    )

    if len(audiences) > 500:
        audiences = audiences[:500]
        truncated = True

    revision = (
        placement.block.current_revision
        if placement.resolution_mode == PlacementResolutionMode.LIVE
        else placement.pinned_revision
    )
    if revision is None:
        raise ValueError("The selected placement does not resolve to a revision.")
    can_edit_shared = context_has_permission(
        context,
        PermissionKey.DOCUMENTS_EDIT,
        organization=placement.block.organization,
    )
    can_detach = not (placement.parent_id is None and placement.position == 0) and context_has_permission(
        context,
        PermissionKey.DOCUMENTS_EDIT,
        organization=placement.document.organization,
    )
    return {
        "block_id": str(placement.block.entity_id),
        "block_name": placement.block.entity.display_name,
        "revision_id": str(revision.id),
        "revision_number": revision.revision_number,
        "checksum": revision.checksum,
        "markdown": revision.markdown,
        "can_edit_shared": can_edit_shared,
        "can_detach": can_detach,
        "requires_mfa": True,
        "audiences": audiences,
        "live_audience_count": sum(audience["will_update"] for audience in audiences),
        "pinned_audience_count": sum(not audience["will_update"] for audience in audiences),
        "truncated": truncated,
    }
