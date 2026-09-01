"""Deterministic, content-safe documentation preflight shared by release surfaces."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass
from typing import Any

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils import timezone

from apps.accounts.policy import DataAudience

from .diagram_exports import diagram_sources, render_diagram_exports
from .document_attachments import copy_attachment_content
from .document_key_freeze import KeyFreezeConflict, freeze_document_keys
from .entity_mentions import resolve_entity_mentions
from .models import Document, DocumentAttachment, DocumentReviewState, PublicationAudience
from .rendering import entity_ids_in_markdown
from .topic_schemas import inspect_markdown

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    summary: str
    remediation: str
    target: str = "document"
    section_id: str | None = None
    line: int | None = None


FINDING_CATALOG = {
    "document.empty": ("blocker", "The document has no publishable content.", "Add content before publishing."),
    "document.archived": ("blocker", "The document is archived.", "Restore the document or choose an active document."),
    "document.unowned": ("warning", "The document has no owner.", "Assign an accountable owner in Document settings."),
    "document.review.pending": ("warning", "Review is still pending.", "Complete the requested review."),
    "document.review.changes_requested": (
        "blocker",
        "A reviewer requested changes.",
        "Address the review note and request review again.",
    ),
    "document.review.stale": ("warning", "The document review is due.", "Review the document and record approval."),
    "topic.section.missing": (
        "blocker",
        "A required topic section is missing.",
        "Restore the section marker and heading in the editor.",
    ),
    "topic.section.duplicate": (
        "blocker",
        "A required topic section appears more than once.",
        "Keep one semantic marker for this section.",
    ),
    "topic.section.heading_missing": (
        "blocker",
        "A topic marker is not followed by a heading.",
        "Add a Markdown heading immediately after the marker.",
    ),
    "topic.section.empty": ("warning", "A required topic section is empty.", "Add useful content to the section."),
    "topic.section.order": (
        "warning",
        "Required topic sections are out of the guided order.",
        "Move the marked sections into the suggested order.",
    ),
    "topic.section.unknown": (
        "warning",
        "An unknown semantic section marker is present.",
        "Remove it or replace it with a marker from the current schema.",
    ),
    "document.keys.unresolved": (
        "blocker",
        "One or more document keys cannot be resolved for this audience.",
        "Open Document keys and repair the unresolved or inaccessible binding.",
    ),
    "attachment.unavailable": (
        "blocker",
        "A referenced attachment is missing, unsafe, or unavailable.",
        "Replace or remove the attachment reference.",
    ),
    "remote.observation.unapplied": (
        "warning",
        "The monitored source has a newer unapplied observation.",
        "Review and apply or dismiss the remote observation.",
    ),
    "template.enrollment.invalid": (
        "blocker",
        "The document's template enrollment is no longer active.",
        "Repair or remove the template enrollment before publishing.",
    ),
    "template.update.available": (
        "warning",
        "A newer template revision is available.",
        "Review the template update and explicitly apply or decline its changes.",
    ),
    "diagram.accessibility": (
        "warning",
        "A diagram lacks a useful accessible title or description.",
        "Add accTitle and accDescr lines to the Mermaid source.",
    ),
    "diagram.render_failed": (
        "blocker",
        "A diagram cannot be rendered into retained publication artifacts.",
        "Open the diagram editor, correct the source, and run the check again.",
    ),
    "entity.unavailable": (
        "blocker",
        "A referenced TekDocs record is missing or unavailable to this audience.",
        "Replace or remove the record link.",
    ),
}


def _finding(code: str, *, target: str = "document", section_id: object = None, line: object = None) -> Finding:
    severity, summary, remediation = FINDING_CATALOG[code]
    return Finding(
        code,
        severity,
        summary,
        remediation,
        target,
        str(section_id) if section_id is not None else None,
        line if isinstance(line, int) else None,
    )


def run_document_preflight(*, workspace, document: Document, resolved, audience: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    findings: list[Finding] = []
    if document.archived_at:
        findings.append(_finding("document.archived"))
    if not resolved.markdown.strip():
        findings.append(_finding("document.empty"))
    if document.owner_id is None:
        findings.append(_finding("document.unowned"))
    if document.review_state == DocumentReviewState.PENDING:
        findings.append(_finding("document.review.pending"))
    elif document.review_state == DocumentReviewState.CHANGES_REQUESTED:
        findings.append(_finding("document.review.changes_requested"))
    if document.review_due_on and document.review_due_on <= timezone.localdate():
        findings.append(_finding("document.review.stale"))
    for item in inspect_markdown(document.topic_type, resolved.markdown):
        findings.append(_finding(str(item["code"]), section_id=item.get("section_id"), line=item.get("line")))
    try:
        freeze_document_keys(
            workspace=workspace,
            document=document,
            markdown=resolved.markdown,
            audience=DataAudience.CLIENT_PORTAL
            if audience == PublicationAudience.CLIENT_VISIBLE
            else DataAudience.MSP_STAFF,
            resolved_at=timezone.now().isoformat(),
            lock=False,
        )
    except KeyFreezeConflict:
        findings.append(_finding("document.keys.unresolved", target="keys"))
    attachment_ids = set()
    from .rendering import attachment_ids_in_markdown

    attachment_ids.update(attachment_ids_in_markdown(resolved.markdown))
    attachment_records = list(
        DocumentAttachment.objects.filter(
            document=document, entity_id__in=attachment_ids, archived_at__isnull=True, scan_status="clean"
        )
    )
    available = {item.entity_id for item in attachment_records}
    if attachment_ids - available:
        findings.append(_finding("attachment.unavailable", target="attachments"))
    else:
        try:
            for attachment in attachment_records:
                copy_attachment_content(attachment)
        except ValidationError:
            findings.append(_finding("attachment.unavailable", target="attachments"))
    requested_entities = entity_ids_in_markdown(resolved.markdown)
    resolved_entities = resolve_entity_mentions(workspace=workspace, markdown=resolved.markdown, lock=False)
    if {str(item) for item in requested_entities} != set(resolved_entities):
        findings.append(_finding("entity.unavailable", target="editor"))
    try:
        source = document.remote_source
    except ObjectDoesNotExist:
        source = None
    changed_observations = source.observations.filter(state="changed") if source is not None else None
    if source is not None and changed_observations is not None and source.last_applied_observation_id is not None:
        changed_observations = changed_observations.exclude(id=source.last_applied_observation_id)
    if changed_observations is not None and changed_observations.exists():
        findings.append(_finding("remote.observation.unapplied", target="remote-source"))
    try:
        enrollment = document.template_enrollment
    except ObjectDoesNotExist:
        enrollment = None
    if enrollment is not None:
        if enrollment.archived_at is not None:
            findings.append(_finding("template.enrollment.invalid", target="document-settings"))
        else:
            latest_template_revision = enrollment.source_template.template_revisions.order_by(
                "-revision_number"
            ).first()
            if latest_template_revision is not None and latest_template_revision.id != enrollment.applied_revision_id:
                findings.append(_finding("template.update.available", target="document-settings"))
    try:
        diagrams = diagram_sources(resolved.markdown)
    except ValueError:
        findings.append(_finding("diagram.render_failed", target="editor"))
        diagrams = ()
    for diagram in diagrams:
        folded_source = diagram.source.casefold()
        if "acctitle:" not in folded_source or "accdescr:" not in folded_source:
            findings.append(_finding("diagram.accessibility", target="editor"))
    if diagrams:
        try:
            render_diagram_exports(resolved.markdown, required=True)
        except ValueError:
            findings.append(_finding("diagram.render_failed", target="editor"))
    findings.sort(
        key=lambda item: (
            {"blocker": 0, "warning": 1, "info": 2}[item.severity],
            item.code,
            item.section_id or "",
            item.line or 0,
        )
    )
    digest = hashlib.sha256(resolved.markdown.encode()).hexdigest()
    result = {
        "version": "tekdocs-preflight/v1",
        "scope": "document",
        "scope_id": str(document.entity_id),
        "composition_digest": digest,
        "audience": audience,
        "valid": not any(item.severity == "blocker" for item in findings),
        "counts": {level: sum(item.severity == level for item in findings) for level in ("blocker", "warning", "info")},
        "findings": [asdict(item) for item in findings],
    }
    logger.info("documentation_preflight scope=document codes=%s", ",".join(item.code for item in findings))
    return result


def catalog() -> list[dict[str, str]]:
    return [
        {"code": code, "severity": values[0], "summary": values[1], "remediation": values[2]}
        for code, values in sorted(FINDING_CATALOG.items())
    ]


def run_map_preflight(*, documentation_map, findings) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Normalize the map inspector through the same release-check service boundary."""
    ordered = sorted(findings, key=lambda item: (item.severity != "blocker", item.code, str(item.entry_id or "")))
    digest = documentation_map.current_revision.content_digest if documentation_map.current_revision else ""
    result = {
        "version": "tekdocs-preflight/v1",
        "scope": "documentation_map",
        "scope_id": str(documentation_map.entity_id),
        "composition_digest": digest,
        "valid": not any(item.severity == "blocker" for item in ordered),
        "counts": {
            level: sum(item.severity == level for item in ordered) for level in ("blocker", "warning", "information")
        },
        "findings": ordered,
    }
    logger.info("documentation_preflight scope=map codes=%s", ",".join(item.code for item in ordered))
    return result
