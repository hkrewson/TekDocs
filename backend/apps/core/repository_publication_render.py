"""Offline HTML projection from signed repository-publication inputs only."""

from __future__ import annotations

import hashlib
from typing import Any

from .document_key_freeze import verify_frozen_field_keys
from .rendering import RenderedAttachment, RenderedEntityMention, render_markdown, render_pdf

RENDERED_SNAPSHOT_FORMAT = "tekdocs-repository-rendered-snapshot/v1"
MAX_RENDERED_HTML_BYTES = 4 * 1024 * 1024
PDF_SNAPSHOT_FORMAT = "tekdocs-repository-pdf-snapshot/v1"
MAX_RENDERED_PDF_BYTES = 8 * 1024 * 1024


def frozen_repository_markdown(*, markdown: str, manifest: dict[str, Any]) -> str:
    key_snapshot = manifest.get("key_snapshot")
    if key_snapshot is None:
        return markdown
    if not verify_frozen_field_keys(markdown, key_snapshot):
        raise ValueError("Field-key snapshot is unavailable")
    frozen = key_snapshot["markdown"]
    if not isinstance(frozen, str):
        raise ValueError("Field-key snapshot Markdown is unavailable")
    return frozen


def retained_pdf_snapshot(*, markdown: str, manifest: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    title = manifest.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Repository document title is unavailable")
    content = render_pdf(frozen_repository_markdown(markdown=markdown, manifest=manifest), title=title)
    if not content.startswith(b"%PDF-") or len(content) > MAX_RENDERED_PDF_BYTES:
        raise ValueError("Rendered publication PDF is unavailable or exceeds its size limit")
    return (
        {
            "format": PDF_SNAPSHOT_FORMAT,
            "filename": "snapshot.pdf",
            "media_type": "application/pdf",
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        },
        content,
    )


def verify_retained_pdf_snapshot(*, markdown: str, manifest: dict[str, Any], content: bytes) -> bool:
    snapshot = manifest.get("pdf_snapshot")
    if not isinstance(snapshot, dict) or set(snapshot) != {"format", "filename", "media_type", "size", "sha256"}:
        return False
    if (
        snapshot.get("format") != PDF_SNAPSHOT_FORMAT
        or snapshot.get("filename") != "snapshot.pdf"
        or snapshot.get("media_type") != "application/pdf"
        or type(snapshot.get("size")) is not int
        or snapshot["size"] != len(content)
        or len(content) > MAX_RENDERED_PDF_BYTES
        or snapshot.get("sha256") != hashlib.sha256(content).hexdigest()
    ):
        return False
    try:
        expected, rendered = retained_pdf_snapshot(markdown=markdown, manifest=manifest)
    except (ValueError, TypeError):
        return False
    return snapshot == expected and content == rendered


def render_repository_evidence_html(*, markdown: str, manifest: dict[str, Any]) -> str:
    """Render frozen dependencies without consulting Git, assets, or source files."""

    frozen_markdown = frozen_repository_markdown(markdown=markdown, manifest=manifest)

    cards = manifest.get("entity_cards")
    attachments = manifest.get("attachments")
    if not isinstance(cards, list) or not isinstance(attachments, list):
        raise ValueError("Frozen reference cards are unavailable")
    entity_mentions: dict[str, RenderedEntityMention] = {}
    for card in cards:
        if (
            not isinstance(card, dict)
            or set(card) != {"id", "display_name", "entity_type", "workspace_label"}
            or not all(isinstance(card[field], str) and card[field] for field in card)
        ):
            raise ValueError("Frozen entity card is invalid")
        entity_mentions[card["id"]] = RenderedEntityMention(
            id=card["id"],
            display_name=card["display_name"],
            entity_type=card["entity_type"],
            workspace_label=card["workspace_label"],
        )

    rendered_attachments: dict[str, RenderedAttachment] = {}
    for descriptor in attachments:
        if (
            not isinstance(descriptor, dict)
            or not isinstance(descriptor.get("source_id"), str)
            or not isinstance(descriptor.get("filename"), str)
            or not descriptor["filename"]
            or type(descriptor.get("size")) is not int
            or descriptor["size"] < 0
        ):
            raise ValueError("Frozen attachment card is invalid")
        source_id = descriptor["source_id"]
        rendered_attachments[source_id] = RenderedAttachment(
            id=source_id,
            filename=descriptor["filename"],
            size=descriptor["size"],
        )

    # No download URL is introduced here: the retained bytes have no routed
    # distribution decision yet. The renderer creates an inert attachment card.
    html = render_markdown(
        frozen_markdown,
        entity_mentions=entity_mentions,
        attachments=rendered_attachments,
    )
    if len(html.encode("utf-8")) > MAX_RENDERED_HTML_BYTES:
        raise ValueError("Rendered publication HTML exceeds its size limit")
    return html


def retained_rendered_snapshot(*, markdown: str, manifest: dict[str, Any]) -> dict[str, str]:
    html = render_repository_evidence_html(markdown=markdown, manifest=manifest)
    return {
        "format": RENDERED_SNAPSHOT_FORMAT,
        "html": html,
        "sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
    }


def verify_retained_rendered_snapshot(*, markdown: str, manifest: dict[str, Any]) -> bool:
    snapshot = manifest.get("rendered_snapshot")
    if not isinstance(snapshot, dict) or set(snapshot) != {"format", "html", "sha256"}:
        return False
    if snapshot.get("format") != RENDERED_SNAPSHOT_FORMAT or not isinstance(snapshot.get("html"), str):
        return False
    try:
        expected = retained_rendered_snapshot(markdown=markdown, manifest=manifest)
    except (ValueError, TypeError):
        return False
    return snapshot == expected
