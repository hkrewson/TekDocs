"""Versioned structured-topic contracts over portable canonical Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import DocumentTopicType

SCHEMA_VERSION = 1
MARKER = re.compile(r"^<!--\s*tekdocs:section\s+([a-z][a-z0-9_-]*)\s*-->\s*$")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")


@dataclass(frozen=True)
class Section:
    id: str
    label: str
    description: str


@dataclass(frozen=True)
class TopicSchema:
    type: str
    label: str
    description: str
    sections: tuple[Section, ...]


def _s(section_id: str, label: str, description: str) -> Section:
    return Section(section_id, label, description)


SCHEMAS: dict[str, TopicSchema] = {
    DocumentTopicType.UNSTRUCTURED: TopicSchema(
        DocumentTopicType.UNSTRUCTURED, "Unstructured", "Write freely without required sections.", ()
    ),
    DocumentTopicType.PROCEDURE: TopicSchema(
        DocumentTopicType.PROCEDURE,
        "Procedure",
        "Repeatable work with validation and a safe way back.",
        (
            _s("purpose", "Purpose", "What this procedure accomplishes."),
            _s("prerequisites", "Prerequisites", "Access, tools, inputs, and conditions needed first."),
            _s("risk-impact", "Risk and impact", "Expected impact and material risks."),
            _s("actions", "Actions", "The ordered steps to perform."),
            _s("validation", "Validation", "How to prove the result is correct."),
            _s("rollback", "Rollback", "How to return to the prior safe state."),
            _s("escalation", "Escalation", "When and where to escalate."),
        ),
    ),
    DocumentTopicType.TROUBLESHOOTING: TopicSchema(
        DocumentTopicType.TROUBLESHOOTING,
        "Troubleshooting",
        "Diagnose a condition and select a remedy.",
        (
            _s("condition", "Condition or symptom", "What is observed and when."),
            _s("diagnostics", "Diagnostics", "Checks that narrow the cause."),
            _s("causes", "Likely causes", "Known causes and distinguishing evidence."),
            _s("remedies", "Remedies", "Corrective actions and validation."),
            _s("escalation", "Escalation", "When and where to escalate."),
        ),
    ),
    DocumentTopicType.REFERENCE: TopicSchema(
        DocumentTopicType.REFERENCE,
        "Reference",
        "Authoritative values and constraints for lookup.",
        (
            _s("purpose", "Purpose", "What this reference describes."),
            _s("values", "Authoritative values", "The values readers should rely on."),
            _s("constraints", "Constraints", "Limits, assumptions, and exceptions."),
            _s("source", "Source", "The authority from which the values came."),
            _s("last-verified", "Last verified", "When and by whom the values were checked."),
        ),
    ),
    DocumentTopicType.SYSTEM_OVERVIEW: TopicSchema(
        DocumentTopicType.SYSTEM_OVERVIEW,
        "System overview",
        "Explain ownership, dependencies, and recovery.",
        (
            _s("purpose", "Purpose", "What the system does and for whom."),
            _s("owners", "Owners", "Business and technical ownership."),
            _s("dependencies", "Dependencies", "Required systems, services, and vendors."),
            _s("data-flow", "Data flow", "How information moves through the system."),
            _s("monitoring", "Monitoring", "Signals, alerts, and normal operating checks."),
            _s("recovery", "Recovery", "Restoration priorities and procedure references."),
        ),
    ),
    DocumentTopicType.CHANGE_RUNBOOK: TopicSchema(
        DocumentTopicType.CHANGE_RUNBOOK,
        "Change runbook",
        "Execute a controlled change and retain evidence.",
        (
            _s("pre-checks", "Pre-checks", "Readiness checks before the change."),
            _s("change-steps", "Change steps", "The ordered implementation steps."),
            _s("validation", "Validation", "Tests proving the change succeeded."),
            _s("rollback", "Rollback", "Triggers and steps for reverting."),
            _s("evidence", "Evidence", "Records to retain after execution."),
        ),
    ),
}


def catalog() -> list[dict[str, object]]:
    return [
        {
            "type": schema.type,
            "label": schema.label,
            "description": schema.description,
            "schema_version": SCHEMA_VERSION,
            "sections": [section.__dict__ for section in schema.sections],
        }
        for schema in SCHEMAS.values()
    ]


def seed_markdown(topic_type: str, existing: str = "") -> str:
    schema = SCHEMAS[topic_type]
    existing = "\n".join(line for line in existing.splitlines() if not MARKER.match(line))
    if not schema.sections:
        return existing + ("\n" if existing else "")
    chunks = []
    for index, section in enumerate(schema.sections):
        body = existing.strip() if index == 0 and existing.strip() else ""
        chunks.append(f"<!-- tekdocs:section {section.id} -->\n## {section.label}\n\n{body}".rstrip())
    return "\n\n".join(chunks) + "\n"


def inspect_markdown(topic_type: str, markdown: str) -> list[dict[str, object]]:
    schema = SCHEMAS[topic_type]
    if not schema.sections:
        return []
    required = [item.id for item in schema.sections]
    lines = markdown.splitlines()
    found: list[tuple[str, int, str]] = []
    for index, line in enumerate(lines):
        match = MARKER.match(line)
        if match:
            heading = HEADING.match(lines[index + 1]) if index + 1 < len(lines) else None
            found.append((match.group(1), index, heading.group(1) if heading else ""))
    findings: list[dict[str, object]] = []
    ids = [item[0] for item in found]
    for section_id in required:
        if ids.count(section_id) == 0:
            findings.append({"code": "topic.section.missing", "severity": "blocker", "section_id": section_id})
        elif ids.count(section_id) > 1:
            findings.append({"code": "topic.section.duplicate", "severity": "blocker", "section_id": section_id})
    for section_id, line_number, heading_text in found:
        if section_id not in required:
            findings.append(
                {
                    "code": "topic.section.unknown",
                    "severity": "warning",
                    "section_id": section_id,
                    "line": line_number + 1,
                }
            )
        if not heading_text:
            findings.append(
                {
                    "code": "topic.section.heading_missing",
                    "severity": "blocker",
                    "section_id": section_id,
                    "line": line_number + 1,
                }
            )
        next_line = next((candidate[1] for candidate in found if candidate[1] > line_number), len(lines))
        if not "\n".join(lines[line_number + 2 : next_line]).strip():
            findings.append(
                {
                    "code": "topic.section.empty",
                    "severity": "warning",
                    "section_id": section_id,
                    "line": line_number + 1,
                }
            )
    ordered = [item for item in ids if item in required]
    if ordered != sorted(ordered, key=required.index):
        findings.append({"code": "topic.section.order", "severity": "warning"})
    return findings
