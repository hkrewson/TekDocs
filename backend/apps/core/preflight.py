"""Deterministic, content-safe documentation preflight shared by release surfaces."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass
from typing import Any

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils import timezone

from apps.accounts.policy import DataAudience

from .diagram_exports import DiagramRenderError, diagram_sources, render_diagram_exports
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
        "Restore the section heading in the editor.",
    ),
    "topic.section.duplicate": (
        "blocker",
        "A required topic section appears more than once.",
        "Keep one heading for this section.",
    ),
    "topic.section.empty": ("warning", "A required topic section is empty.", "Add useful content to the section."),
    "topic.section.order": (
        "warning",
        "Required topic sections are out of the guided order.",
        "Move the sections into the suggested order.",
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
    "diagram.family.unsupported": (
        "warning",
        "A diagram type is outside the TekDocs 1.0 support contract.",
        "Use a flowchart, sequence, class, state, or entity-relationship diagram for guaranteed 1.x compatibility.",
    ),
    "diagram.render_failed": (
        "blocker",
        "A diagram cannot be rendered into retained publication artifacts.",
        "Open the diagram editor, correct the source, and run the check again.",
    ),
    "diagram.count.exceeded": (
        "blocker",
        "This document contains more diagrams than one publication can safely render.",
        "Split the document or reduce it to 20 diagrams, then run the check again.",
    ),
    "diagram.directive.unsupported": (
        "blocker",
        "A diagram uses a Mermaid configuration directive that TekDocs does not support.",
        "Remove the configuration block or init directive from the Mermaid source.",
    ),
    "diagram.output.incomplete": (
        "blocker",
        "The diagram renderer did not return every required publication file.",
        "Run the check again. If it still fails, review the renderer service health.",
    ),
    "diagram.output.invalid": (
        "blocker",
        "The diagram renderer returned an invalid SVG file.",
        "Run the check again. If it still fails, review the renderer service health.",
    ),
    "diagram.output.oversized": (
        "blocker",
        "A rendered diagram is too large to retain safely.",
        "Simplify the diagram or divide it into smaller diagrams.",
    ),
    "diagram.output.unsafe": (
        "blocker",
        "A rendered diagram contains content TekDocs cannot retain safely.",
        "Remove links, embedded content, or custom styling from the Mermaid source.",
    ),
    "diagram.raster.failed": (
        "blocker",
        "TekDocs could not create the diagram image required for downloads.",
        "Run the check again. If it still fails, review the renderer service health.",
    ),
    "diagram.renderer.busy": (
        "blocker",
        "The diagram renderer is handling too many jobs.",
        "Wait briefly, then run the check again.",
    ),
    "diagram.renderer.invalid_response": (
        "blocker",
        "The diagram renderer returned a response TekDocs could not verify.",
        "Review the renderer service version and health, then run the check again.",
    ),
    "diagram.renderer.timeout": (
        "blocker",
        "The diagram renderer did not finish in time.",
        "Simplify the diagram or run the check again. If it persists, review renderer capacity.",
    ),
    "diagram.renderer.unavailable": (
        "blocker",
        "The diagram renderer is unavailable.",
        "Restore the renderer service, then run the check again.",
    ),
    "diagram.source.invalid": (
        "blocker",
        "The diagram source could not be rendered.",
        "Open the diagram editor, correct the Mermaid source, and run the check again.",
    ),
    "diagram.source.oversized": (
        "blocker",
        "A diagram contains more than 50,000 characters.",
        "Simplify the diagram or divide it into smaller diagrams.",
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
    except DiagramRenderError as error:
        code = error.code if error.code in FINDING_CATALOG else "diagram.render_failed"
        findings.append(_finding(code, target="editor"))
        diagrams = ()
    for diagram in diagrams:
        folded_source = diagram.source.casefold()
        if "acctitle:" not in folded_source or "accdescr:" not in folded_source:
            findings.append(_finding("diagram.accessibility", target="editor"))
    if any(diagram.family == "unsupported" for diagram in diagrams):
        findings.append(_finding("diagram.family.unsupported", target="editor"))
    if diagrams:
        try:
            render_diagram_exports(resolved.markdown, required=True)
        except DiagramRenderError as error:
            code = error.code if error.code in FINDING_CATALOG else "diagram.render_failed"
            findings.append(_finding(code, target="editor"))
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
