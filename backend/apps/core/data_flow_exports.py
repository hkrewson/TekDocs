"""Deterministic exports of a retained data-flow snapshot (ADR 0088).

Every format is built from the snapshot's stored payload rather than from live
records, so an export taken today and the same export taken next year are
byte-identical unless the snapshot itself differs.
"""

from __future__ import annotations

import csv
import io
from html import escape

from .data_flows import canonical_json
from .diagram_exports import DiagramRenderError, sanitize_svg
from .models import DataFlowSnapshot

#: Rows drawn in the diagram. The structured formats carry everything; the picture is
#: a summary, and an unbounded one stops being readable long before it stops rendering.
MAXIMUM_DIAGRAM_ROWS = 60

CSV_COLUMNS = (
    "name",
    "source",
    "destination",
    "direction",
    "transfer_mechanism",
    "data_classification",
    "protection",
    "crosses_trust_boundary",
    "provenance",
    "review_due_on",
    "purpose",
    "revision_number",
)


def snapshot_json(snapshot: DataFlowSnapshot) -> bytes:
    """The snapshot as retained, in canonical form.

    Identifiers and timestamps are projected as strings here rather than handed to the
    encoder as objects, so this cannot fail at serialization time on a value the
    encoder does not know.
    """

    return canonical_json(
        {
            "id": str(snapshot.id),
            "title": snapshot.title,
            "reason": snapshot.reason,
            "content_digest": snapshot.content_digest,
            "flow_count": snapshot.flow_count,
            "created_at": snapshot.created_at.isoformat(),
            "payload": snapshot.flows,
        }
    )


def _rows(snapshot: DataFlowSnapshot) -> list[dict[str, object]]:
    payload = snapshot.flows
    flows = payload.get("flows", []) if isinstance(payload, dict) else []
    return [flow for flow in flows if isinstance(flow, dict)]


def snapshot_csv(snapshot: DataFlowSnapshot) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for flow in _rows(snapshot):
        writer.writerow([("" if flow.get(column) is None else flow.get(column)) for column in CSV_COLUMNS])
    return stream.getvalue()


def _label(value: object, limit: int = 34) -> str:
    """Text safe to place inside the diagram.

    The shared sanitizer rejects any SVG containing a URL scheme, which is a sound rule
    for renderer output but would let a flow legitimately named after an endpoint URL
    break its own export. Neutralising the scheme in the drawn label costs nothing —
    the JSON and CSV exports still carry the value in full.
    """

    text = str(value)
    for scheme in ("http:", "https:", "data:", "javascript:"):
        text = text.replace(scheme, scheme.replace(":", " "))
    if len(text) > limit:
        text = f"{text[: limit - 1]}…"
    return escape(text)


def snapshot_svg(snapshot: DataFlowSnapshot) -> bytes:
    """A bounded, sanitized diagram of the retained flows.

    Geometry uses rects and lines only. The shared allowlist admits neither `cx`/`cy`
    nor `viewBox`, so a circle-based drawing would silently lose its shapes on the way
    through sanitization.
    """

    flows = _rows(snapshot)
    drawn = flows[:MAXIMUM_DIAGRAM_ROWS]
    truncated = len(flows) - len(drawn)
    height = 60 + max(len(drawn), 1) * 64 + (30 if truncated else 0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="820" height="{height}">',
        f'<rect x="0" y="0" width="820" height="{height}" fill="#ffffff"/>',
        f'<text x="20" y="32" font-family="sans-serif" font-size="15" fill="#23241f">'
        f"{_label(snapshot.title, 70)}</text>",
    ]
    for index, flow in enumerate(drawn):
        top = 56 + index * 64
        middle = top + 22
        boundary = bool(flow.get("crosses_trust_boundary"))
        parts.append(
            f'<rect x="20" y="{top}" width="250" height="44" rx="6" ry="6" fill="#f4f2ec" stroke="#c5c1b7"/>'
            f'<text x="34" y="{middle + 5}" font-family="sans-serif" font-size="12" fill="#23241f">'
            f"{_label(flow.get('source', ''))}</text>"
            f'<line x1="270" y1="{middle}" x2="550" y2="{middle}" stroke="{"#7a3328" if boundary else "#6d6d65"}"'
            f' stroke-width="{2 if boundary else 1}"/>'
            f'<text x="410" y="{middle - 8}" text-anchor="middle" font-family="sans-serif" font-size="10"'
            f' fill="#6d6d65">{_label(flow.get("data_classification", ""), 28)}</text>'
            f'<text x="410" y="{middle + 16}" text-anchor="middle" font-family="sans-serif" font-size="10"'
            f' fill="#6d6d65">{_label(flow.get("protection", ""), 28)}</text>'
            f'<rect x="550" y="{top}" width="250" height="44" rx="6" ry="6" fill="#f4f2ec" stroke="#c5c1b7"/>'
            f'<text x="564" y="{middle + 5}" font-family="sans-serif" font-size="12" fill="#23241f">'
            f"{_label(flow.get('destination', ''))}</text>"
        )
    if truncated:
        parts.append(
            f'<text x="20" y="{height - 14}" font-family="sans-serif" font-size="11" fill="#6d6d65">'
            f"{truncated} further flows are recorded in this snapshot and not drawn.</text>"
        )
    try:
        return sanitize_svg("".join((*parts, "</svg>")).encode("utf-8"))
    except DiagramRenderError as exc:  # pragma: no cover - defence, not an expected path
        raise DiagramRenderError("The data-flow diagram could not be produced safely.") from exc
