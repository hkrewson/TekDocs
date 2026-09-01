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
        DocumentTopicType.UNSTRUCTURED, "Unstructured", "Start with a blank document.", ()
    ),
    DocumentTopicType.POLICY: TopicSchema(
        DocumentTopicType.POLICY,
        "Policy",
        "Set clear, enforceable rules and accountability.",
        (
            _s("purpose", "Purpose", "Why the policy exists and the risk it addresses."),
            _s("scope", "Scope", "Who and what the policy covers, including explicit exclusions."),
            _s("definitions", "Definitions", "Terms that a reasonable employee might interpret more than one way."),
            _s("policy-statement", "Policy statement", "Clear, testable requirements using must and must not."),
            _s(
                "roles-responsibilities",
                "Roles and responsibilities",
                "Accountability assigned to roles, not individuals.",
            ),
            _s("compliance-consequences", "Compliance and consequences", "What happens when the policy is breached."),
            _s("related", "Related documents", "Procedures, forms, resources, and related policies."),
            _s("revision-history", "Revision history", "A dated log of changes to the policy."),
        ),
    ),
    DocumentTopicType.PROCEDURE: TopicSchema(
        DocumentTopicType.PROCEDURE,
        "Procedure",
        "Document a repeatable operational process.",
        (
            _s("overview", "Overview", "A concise summary of the procedure."),
            _s("purpose", "Purpose", "What this procedure accomplishes."),
            _s("scope", "Scope", "Who, what, and which conditions the procedure covers."),
            _s(
                "responsibilities", "Responsibilities", "The roles responsible for carrying out and approving the work."
            ),
            _s("process", "Process", "The ordered steps to follow."),
            _s("related", "Related", "Related documents, support pages, forms, and resources."),
            _s("revision-history", "Revision history", "A dated log of changes to the procedure."),
        ),
    ),
    DocumentTopicType.GUIDE: TopicSchema(
        DocumentTopicType.GUIDE,
        "Guide",
        "Give end users a friendly, task-focused walkthrough.",
        (
            _s("overview", "Overview", "What the guide covers and what the reader will accomplish."),
            _s("walkthrough", "Walkthrough", "The steps the reader should follow."),
            _s("related", "Related", "Related documentation, support pages, and resources."),
            _s("revision-history", "Revision history", "A dated log of changes to the guide."),
        ),
    ),
    DocumentTopicType.TROUBLESHOOTING: TopicSchema(
        DocumentTopicType.TROUBLESHOOTING,
        "Troubleshooting",
        "Capture an issue, investigation, next steps, and resolution.",
        (
            _s("issue", "Issue", "What the user describes, recorded verbatim."),
            _s(
                "steps-to-reproduce",
                "Steps to reproduce",
                "If reproducible, the exact steps that make the issue occur.",
            ),
            _s("steps-taken", "Steps taken", "The exact troubleshooting or resolution steps already performed."),
            _s("next-steps", "Next steps", "The next troubleshooting actions expected, if any."),
            _s("related", "Related", "Documentation, support pages, or resources used during research."),
            _s("resolution", "Resolution", "A general overview of what resolved the issue."),
        ),
    ),
    DocumentTopicType.REFERENCE: TopicSchema(
        DocumentTopicType.REFERENCE,
        "Reference",
        "Authoritative values and constraints for lookup.",
        (
            _s("purpose", "Purpose", "What this reference describes."),
            _s("values", "Values and specifications", "The authoritative values readers should rely on."),
            _s("constraints", "Constraints and exceptions", "Limits, assumptions, and exceptions."),
            _s("examples", "Examples", "Examples showing correct interpretation or use."),
            _s("source", "Sources", "The authorities from which the information came."),
            _s("last-verified", "Last verified", "When and by whom the values were checked."),
            _s("related", "Related", "Related documentation and resources."),
            _s("revision-history", "Revision history", "A dated log of changes to the reference."),
        ),
    ),
    DocumentTopicType.SYSTEM_OVERVIEW: TopicSchema(
        DocumentTopicType.SYSTEM_OVERVIEW,
        "System overview",
        "Explain ownership, dependencies, and recovery.",
        (
            _s("overview", "Overview", "What the system is and what it does."),
            _s("purpose-scope", "Purpose and scope", "Who the system serves and the boundaries of this overview."),
            _s("owners", "Owners and contacts", "Business ownership, technical ownership, and support contacts."),
            _s("architecture", "Architecture", "The major components and how they fit together."),
            _s("dependencies", "Dependencies", "Required systems, services, and vendors."),
            _s(
                "data-integrations",
                "Data and integrations",
                "Important data flows, interfaces, and integration points.",
            ),
            _s("monitoring", "Monitoring and alerts", "Signals, alerts, and normal operating checks."),
            _s(
                "security-access",
                "Security and access",
                "Authentication, authorization, and sensitive-data considerations.",
            ),
            _s("recovery", "Backup and recovery", "Protection, restoration priorities, and procedure references."),
            _s("related", "Related", "Related procedures, diagrams, and resources."),
            _s("revision-history", "Revision history", "A dated log of changes to the overview."),
        ),
    ),
    DocumentTopicType.CHANGE_RUNBOOK: TopicSchema(
        DocumentTopicType.CHANGE_RUNBOOK,
        "Change runbook",
        "Execute a controlled change and retain evidence.",
        (
            _s("change-summary", "Change summary", "A concise description of the planned change."),
            _s("purpose", "Purpose", "Why the change is required."),
            _s("scope-impact", "Scope and impact", "Affected systems, users, risks, and expected interruption."),
            _s("prerequisites", "Prerequisites", "Approvals, access, tools, backups, and dependencies needed first."),
            _s("pre-checks", "Pre-change checks", "Readiness checks and the expected starting state."),
            _s("change-steps", "Implementation steps", "The ordered implementation steps."),
            _s("validation", "Validation", "Tests proving the change succeeded."),
            _s("rollback", "Rollback", "Rollback triggers and ordered steps for returning to a safe state."),
            _s("communication", "Communication", "Who must be informed before, during, and after the change."),
            _s("evidence", "Evidence", "Records to retain after execution."),
            _s("related", "Related", "Related procedures, tickets, approvals, and resources."),
            _s("revision-history", "Revision history", "A dated log of changes to the runbook."),
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
            "starter_markdown": seed_markdown(schema.type),
            "sections": [section.__dict__ for section in schema.sections],
        }
        for schema in SCHEMAS.values()
    ]


def seed_markdown(topic_type: str, existing: str = "") -> str:
    schema = SCHEMAS[topic_type]
    found_ids = [match.group(1) for line in existing.splitlines() if (match := MARKER.match(line))]
    if found_ids == [section.id for section in schema.sections]:
        return existing.rstrip() + ("\n" if existing else "")
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
