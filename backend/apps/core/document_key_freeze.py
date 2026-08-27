"""Freeze authorized field-key values into evidence and export Markdown (ADR 0089)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import partial

from apps.accounts.policy import DataAudience

from .document_key_resolution import KeyResolutionKind, ResolutionState, ResolvedKey, resolve_markdown_keys
from .document_keys import MAXIMUM_KEYS_PER_DOCUMENT, key_targets_in_markdown, keys_in_markdown
from .models import Document
from .workspaces import ResolvedWorkspace

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_KEY_AUTOLINK = re.compile(r"<(tekdocs://key/[^<>\s]+)>")
_MARKDOWN_PUNCTUATION = frozenset(r"\`*_{}[]<>()#+-.!|")
MAXIMUM_FROZEN_MARKDOWN_BYTES = 2 * 1024 * 1024
MAXIMUM_CONTENT_KEY_DEPTH = 32


class KeyFreezeConflict(ValueError):
    """A key could not be frozen for the intended output audience."""


@dataclass(frozen=True, slots=True)
class FrozenKeyDocument:
    markdown: str
    manifest_records: tuple[dict[str, object], ...]


def _ordered_unique_records(records: list[dict[str, object]]) -> tuple[dict[str, object], ...]:
    by_expression: dict[str, dict[str, object]] = {}
    for record in records:
        expression = str(record["expression"])
        prior = by_expression.setdefault(expression, record)
        if prior != record:
            raise KeyFreezeConflict("One key expression resolved through conflicting dependency paths.")
    return tuple(by_expression[expression] for expression in sorted(by_expression))


def _finalize_resolution_timestamp(
    records: list[dict[str, object]], *, document: Document, resolved_at: str | None
) -> list[dict[str, object]]:
    """Apply one honest timestamp without making unchanged editable bundles drift.

    STATIC passes its actual publication instant. Editable exports use the newest
    retained input-state timestamp in the locked snapshot: it changes whenever a
    resolved source changes, while repeated exports of identical state remain byte
    deterministic.
    """
    state_timestamps = [document.updated_at.isoformat()]
    state_timestamps.extend(
        str(record["_source_state_at"])
        for record in records
        if isinstance(record.get("_source_state_at"), str)
    )
    common_timestamp = resolved_at or max(state_timestamps)
    return [
        {
            **{key: value for key, value in record.items() if key != "_source_state_at"},
            "resolved_at": common_timestamp,
        }
        for record in records
    ]


def _safe_inline_value(value: str) -> str:
    """Return one inert Markdown inline scalar without changing its visible text."""
    compact = " ".join(value.split())
    return "".join(f"\\{character}" if character in _MARKDOWN_PUNCTUATION else character for character in compact)


def _literal_replacement(_match: re.Match[str], *, value: str) -> str:
    return value


def _replace_key_autolinks(markdown: str, replacements: dict[str, str]) -> str:
    """Replace parsed key autolinks while leaving fenced, indented, and inline code literal."""
    parsed_targets = set(key_targets_in_markdown(markdown))
    output: list[str] = []
    fence_character = ""
    fence_length = 0
    code_span_length = 0

    for line in markdown.splitlines(keepends=True):
        fence = _FENCE.match(line)
        if fence_character:
            output.append(line)
            marker = fence.group(1) if fence else ""
            if (
                fence is not None
                and marker[0] == fence_character
                and len(marker) >= fence_length
                and not fence.group(2).strip()
            ):
                fence_character = ""
                fence_length = 0
            continue
        if fence:
            marker = fence.group(1)
            fence_character = marker[0]
            fence_length = len(marker)
            output.append(line)
            continue
        if code_span_length == 0 and (line.startswith("    ") or line.startswith("\t")):
            output.append(line)
            continue

        index = 0
        rendered: list[str] = []
        while index < len(line):
            if line[index] == "`":
                end = index + 1
                while end < len(line) and line[end] == "`":
                    end += 1
                run_length = end - index
                if code_span_length == 0:
                    code_span_length = run_length
                elif code_span_length == run_length:
                    code_span_length = 0
                rendered.append(line[index:end])
                index = end
                continue
            if code_span_length == 0 and line[index] == "<":
                match = _KEY_AUTOLINK.match(line, index)
                if match and match.group(1) in parsed_targets and match.group(1) in replacements:
                    rendered.append(replacements[match.group(1)])
                    index = match.end()
                    continue
            rendered.append(line[index])
            index += 1
        output.append("".join(rendered))
    return "".join(output)


def _manifest_record(
    result: ResolvedKey, *, resolved_at: str, dependency_chain: tuple[str, ...] = ()
) -> dict[str, object]:
    return {
        "kind": result.kind.value,
        "expression": result.expression,
        "value": result.value,
        "source_entity_id": str(result.source_entity_id),
        "source_entity_type": result.source_entity_type,
        "source_fingerprint": result.source_fingerprint,
        "provenance": result.provenance.value if result.provenance is not None else "local",
        "resolved_at": resolved_at,
        "source_revision_id": str(result.source_revision_id) if result.source_revision_id is not None else None,
        "source_revision_number": result.source_revision_number,
        "dependency_chain": list(dependency_chain),
        "_source_state_at": result.source_state_at.isoformat() if result.source_state_at is not None else None,
    }


def _expand_content_keys(
    *,
    workspace: ResolvedWorkspace,
    document: Document,
    markdown: str,
    audience: DataAudience,
    resolved_at: str | None,
    expressions: set[str],
    lock: bool,
    ancestry: tuple[str, ...] = (),
    depth: int = 0,
) -> tuple[str, list[dict[str, object]]]:
    if depth >= MAXIMUM_CONTENT_KEY_DEPTH:
        raise KeyFreezeConflict(
            f"Document content keys exceed the {MAXIMUM_CONTENT_KEY_DEPTH}-level expansion limit."
        )
    keys, _unparsable = keys_in_markdown(markdown)
    expressions.update(key.expression for key in keys)
    if len(expressions) > MAXIMUM_KEYS_PER_DOCUMENT:
        raise KeyFreezeConflict("Document keys exceed the 200-key resolution limit.")
    content_keys = [key for key in keys if key.path == ("content",)]
    if not content_keys:
        return markdown, []

    resolutions = resolve_markdown_keys(
        markdown,
        context=workspace.member,
        document=document,
        audience=audience,
        organization=workspace.organization,
        lock=lock,
    )
    expanded = markdown
    records: list[dict[str, object]] = []
    for key in content_keys:
        result = resolutions[key.target]
        if result.state != ResolutionState.RESOLVED or result.kind != KeyResolutionKind.CONTENT:
            raise KeyFreezeConflict("One or more document keys could not be resolved for the selected audience.")
        source_id = str(result.source_entity_id)
        if source_id in ancestry:
            raise KeyFreezeConflict("Circular content-key expansion detected.")
        child, child_records = _expand_content_keys(
            workspace=workspace,
            document=document,
            markdown=result.value,
            audience=audience,
            resolved_at=resolved_at,
            ancestry=(*ancestry, source_id),
            depth=depth + 1,
            expressions=expressions,
            lock=lock,
        )
        pattern = re.compile(rf"(?m)^ {{0,3}}<{re.escape(key.target)}>[ \t]*(?:\n|$)")
        expanded, count = pattern.subn(
            partial(_literal_replacement, value=child.rstrip("\n") + "\n"), expanded
        )
        expected = key_targets_in_markdown(markdown).count(key.target)
        if count != expected:
            raise KeyFreezeConflict("Content keys must appear on a line by themselves.")
        dependency_chain = (*ancestry, source_id)
        records.append(
            _manifest_record(result, resolved_at=resolved_at or "", dependency_chain=dependency_chain)
        )
        records.extend(child_records)
    if len(expanded.encode("utf-8")) > MAXIMUM_FROZEN_MARKDOWN_BYTES:
        raise KeyFreezeConflict("Resolved document content exceeds the 2 MiB rendering limit.")
    return expanded, records


def expand_rendered_content_keys(
    *, workspace: ResolvedWorkspace, document: Document | None, markdown: str
) -> str:
    """Expand valid content keys for a live read; leave failures for explicit markers."""
    if document is None:
        return markdown
    try:
        expanded, _records = _expand_content_keys(
            workspace=workspace,
            document=document,
            markdown=markdown,
            audience=(
                DataAudience.CLIENT_PORTAL
                if workspace.member.surface == "client_portal"
                else DataAudience.MSP_STAFF
            ),
            resolved_at="",
            expressions=set(),
            lock=False,
        )
    except KeyFreezeConflict:
        return markdown
    return expanded


def freeze_document_keys(
    *,
    workspace: ResolvedWorkspace,
    document: Document,
    markdown: str,
    audience: DataAudience,
    resolved_at: str | None,
    lock: bool = True,
) -> FrozenKeyDocument:
    """Resolve all parsed keys under row locks and return one canonical frozen projection."""
    expressions: set[str] = set()
    expanded_markdown, content_records = _expand_content_keys(
        workspace=workspace,
        document=document,
        markdown=markdown,
        audience=audience,
        resolved_at=resolved_at,
        expressions=expressions,
        lock=lock,
    )
    keys, unparsable = keys_in_markdown(expanded_markdown)
    if not keys and not unparsable:
        records = _ordered_unique_records(
            _finalize_resolution_timestamp(content_records, document=document, resolved_at=resolved_at)
        )
        return FrozenKeyDocument(markdown=expanded_markdown, manifest_records=records)

    resolutions = resolve_markdown_keys(
        expanded_markdown,
        context=workspace.member,
        document=document,
        audience=audience,
        organization=workspace.organization,
        lock=lock,
    )
    if unparsable or any(
        result.state != ResolutionState.RESOLVED or result.kind != KeyResolutionKind.FIELD
        for result in resolutions.values()
    ):
        raise KeyFreezeConflict("One or more document keys could not be resolved for the selected audience.")

    replacements = {target: _safe_inline_value(result.value) for target, result in resolutions.items()}
    frozen_markdown = _replace_key_autolinks(expanded_markdown, replacements)
    remaining, malformed = keys_in_markdown(frozen_markdown)
    if remaining or malformed:
        raise KeyFreezeConflict("One or more document keys could not be frozen safely.")

    records = _ordered_unique_records(
        _finalize_resolution_timestamp(
            [
                *content_records,
                *(_manifest_record(result, resolved_at=resolved_at or "") for result in resolutions.values()),
            ],
            document=document,
            resolved_at=resolved_at,
        )
    )
    return FrozenKeyDocument(markdown=frozen_markdown, manifest_records=records)
