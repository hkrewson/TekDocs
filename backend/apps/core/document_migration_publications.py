"""Retained-history verification and bounded publication-bearing migration eligibility."""

from __future__ import annotations

import hashlib
from uuid import UUID

from django.core.exceptions import ImproperlyConfigured

from .document_migration_shape import DocumentMigrationShapeError, owned_placement_tree
from .models import Document, DocumentPublication, Workspace
from .publications import _timestamp, canonical_json, verify_publication, verify_retained_publication_custody


def publication_migration_actor_allowed(*, workspace: Workspace, actor_id: UUID) -> bool:
    """Keep the new history-bearing mutation path behind existing edit/MFA policy."""
    from rest_framework.exceptions import APIException

    from apps.accounts.models import User
    from apps.accounts.policy import PermissionKey, require_permission

    actor = User.objects.filter(pk=actor_id, is_active=True).first()
    if actor is None:
        return False
    try:
        member = require_permission(actor, PermissionKey.DOCUMENTS_EDIT, organization=workspace.organization)
    except APIException:
        return False
    return member.tenant.id == workspace.tenant_id


def assess_retained_publications(*, workspace: Workspace, document: Document) -> dict[str, object]:
    if (
        document.tenant_id != workspace.tenant_id
        or document.organization_id != workspace.organization_id
        or document.entity.workspace_id != workspace.id
        or not Document.objects.filter(
            pk=document.pk,
            tenant_id=workspace.tenant_id,
            organization=workspace.organization,
            entity__workspace=workspace,
        ).exists()
    ):
        raise ValueError("Document does not belong to the selected workspace")
    publications = list(
        DocumentPublication.objects.filter(
            document=document,
            tenant_id=workspace.tenant_id,
            organization=workspace.organization,
        )
        .select_related("entity", "supersedes", "organization")
        .order_by("id")
    )
    reasons: set[str] = set()
    if publications:
        placements = list(document.placements.select_related("block", "pinned_revision"))
        try:
            owned_placement_tree(document, placements)
        except DocumentMigrationShapeError:
            reasons.add("publication_document_shape_unsupported")
        if not any(item.block.source_document_id == document.id for item in placements):
            reasons.add("publication_document_shape_unsupported")
    evidence = []
    artifact_count = 0
    by_id = {item.id: item for item in publications}
    for publication in publications:
        artifacts = list(publication.artifacts.select_related("entity").order_by("id"))
        controls = list(publication.control_events.order_by("occurred_at", "id"))
        artifact_count += len(artifacts)
        if (
            publication.tenant_id != workspace.tenant_id
            or publication.organization_id != workspace.organization_id
            or publication.entity.workspace_id != workspace.id
            or any(
                item.tenant_id != workspace.tenant_id or item.organization_id != workspace.organization_id
                for item in artifacts
            )
            or any(
                item.tenant_id != workspace.tenant_id or item.organization_id != workspace.organization_id
                for item in controls
            )
            or any(item.entity.workspace_id != workspace.id for item in artifacts)
        ):
            reasons.add("publication_owner_mismatch")
        manifest = publication.manifest
        if not isinstance(manifest, dict):
            reasons.add("publication_manifest_invalid")
            continue
        if (
            manifest.get("format")
            not in {
                "tekdocs-static-publication/v2",
                "tekdocs-static-publication/v3",
                "tekdocs-static-publication/v4",
                "tekdocs-static-publication/v5",
                "tekdocs-static-publication/v6",
                "tekdocs-static-publication/v7", "tekdocs-static-publication/v8",
            }
            or publication.audience != "msp_internal"
            or sum(item.kind == "pdf" for item in artifacts) != 1
            or any(item.kind not in {"pdf", "attachment"} for item in artifacts)
            or any(item.kind == "attachment" and (
                item.source_attachment is None
                or item.source_attachment.document_id != document.id
                or item.source_attachment.owner_workspace_id != workspace.id
                or item.source_attachment.owner_content_id != document.id
            ) for item in artifacts)
        ):
            reasons.add("publication_shape_unsupported")
        expected = {
            "publication_id": str(publication.id),
            "publication_entity_id": str(publication.entity_id),
            "source_document_id": str(document.entity_id),
            "workspace": {
                "kind": "organization" if workspace.organization_id else "msp",
                "id": str(publication.organization.entity_id) if publication.organization else None,
            },
            "published_at": _timestamp(publication.published_at),
            "title": publication.title,
            "category": publication.category,
            "reason": publication.reason,
            "audience": publication.audience,
            "retention": publication.retention,
            "retention_review_on": publication.retention_review_on.isoformat()
            if publication.retention_review_on
            else None,
            "supersedes_id": str(publication.supersedes.entity_id) if publication.supersedes else None,
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            reasons.add("publication_metadata_mismatch")
        if publication.supersedes_id is not None:
            predecessor = by_id.get(publication.supersedes_id)
            if (
                predecessor is None
                or predecessor.id == publication.id
                or predecessor.published_at >= publication.published_at
            ):
                reasons.add("publication_supersession_invalid")
        actions = {item.action: item.occurred_at for item in controls}
        if "submitted" not in actions or any(
            action not in {"submitted", "approved", "withdrawn"} for action in actions
        ):
            reasons.add("publication_controls_invalid")
        elif any(timestamp < actions["submitted"] for timestamp in actions.values()):
            reasons.add("publication_controls_invalid")
        if "approved" in actions and "withdrawn" in actions and actions["withdrawn"] < actions["approved"]:
            reasons.add("publication_controls_invalid")
        try:
            if manifest.get("format") in {
                "tekdocs-static-publication/v5", "tekdocs-static-publication/v6",
                "tekdocs-static-publication/v7", "tekdocs-static-publication/v8",
            }:
                from .document_git_publications import verify_internal_git_publication

                if not verify_internal_git_publication(publication):
                    reasons.add("publication_git_source_invalid")
            if not verify_publication(publication)["valid"]:
                reasons.add("publication_signature_invalid")
            if not verify_retained_publication_custody(publication):
                reasons.add("publication_custody_invalid")
        except (OSError, ValueError, TypeError, AttributeError, ImproperlyConfigured):
            reasons.add("publication_verification_unavailable")
        evidence.append(
            {
                "id": str(publication.id),
                "entity_id": str(publication.entity_id),
                "digest": publication.content_digest,
                "signature": publication.signature,
                "metadata": expected,
                "artifacts": [
                    {"id": str(item.id), "entity_id": str(item.entity_id), "checksum": item.checksum}
                    for item in artifacts
                ],
                "controls": [
                    {
                        "id": str(item.id),
                        "action": item.action,
                        "reason": item.reason,
                        "actor": str(item.actor_id),
                        "at": item.occurred_at.isoformat(),
                    }
                    for item in controls
                ],
            }
        )
    return {
        "state": "blocked" if reasons else "verified" if publications else "absent",
        "publication_count": len(publications),
        "artifact_count": artifact_count,
        "reasons": sorted(reasons),
        "evidence_sha256": hashlib.sha256(canonical_json(evidence)).hexdigest()
        if publications and not reasons
        else None,
    }


def publication_migration_evidence(
    *, workspace: Workspace, document: Document, assessment: dict[str, object] | None = None
) -> str | None:
    """Verify the internal, permanent, reversible-composition migration boundary.

    The fingerprint binds a preview to retained history; it is neither permission
    to change authority nor a substitute for rechecking custody at execution.
    """
    from .document_migration_export import build_simple_document_export
    from .document_template_migration import TemplateMigrationError, template_enrollment_fingerprint
    from .documents import resolve_document
    from .models import DocumentAttachment
    from .repository_publication_preflight import repository_publication_preflight

    report = (
        assessment if assessment is not None else assess_retained_publications(workspace=workspace, document=document)
    )
    if report["state"] != "verified" or not isinstance(report["evidence_sha256"], str):
        return None
    if (
        document.archived_at is not None
        or DocumentPublication.objects.filter(document=document).exclude(retention="permanent").exists()
    ):
        return None
    try:
        template_enrollment_fingerprint(document)
        exported = build_simple_document_export(
            document, allow_repository_divergence=True, verify_attachments=True
        )
        if (
            exported.key_binding_ids
            or exported.resolved_entity_links
            or repository_publication_preflight(
                markdown=resolve_document(document).markdown,
                audience="msp_internal",
                topic_type=document.topic_type,
                frozen_attachment_ids=set(
                    DocumentAttachment.objects.filter(document=document, archived_at__isnull=True)
                    .values_list("entity_id", flat=True)
                ),
                frozen_primary_file=DocumentAttachment.objects.filter(
                    document=document, purpose="primary_file"
                ).exists(),
            )["blockers"]
        ):
            return None
    except (OSError, ValueError, ImproperlyConfigured, TemplateMigrationError):
        return None
    return report["evidence_sha256"]
