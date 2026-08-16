from __future__ import annotations

import re
from collections.abc import Mapping
from html import escape
from io import BytesIO
from typing import NotRequired, TypedDict
from uuid import UUID

import nh3
from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.footnote import footnote_plugin
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Image, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

from .diagram_exports import DiagramExportArtifact

CALLOUT_TYPES = frozenset({"note", "tip", "important", "warning", "caution"})
_CALLOUT_PATTERN = re.compile(r"^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\](?:[ \t]*\n|[ \t]+)?")
_HIGHLIGHT_PATTERN = re.compile(r"(?<![\w=])==(?=\S)([^=\n]*?\S)==(?![\w=])")
_TASK_PATTERN = re.compile(r"^\[([ xX])\][ \t]+")
_ENTITY_TARGET_PATTERN = re.compile(
    r"^tekdocs://entity/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})$"
)
_ATTACHMENT_TARGET_PATTERN = re.compile(
    r"^tekdocs://attachment/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})$"
)


class RenderedEntityMention(TypedDict):
    id: str
    display_name: str
    entity_type: str
    workspace_label: str


class RenderedAttachment(TypedDict):
    id: str
    filename: str
    size: int
    download_url: NotRequired[str]


def _replace_inline_content(markdown: MarkdownIt, token: Token, value: str, env: dict[str, object]) -> None:
    children: list[Token] = []
    markdown.inline.parse(value, markdown, env, children)
    token.content = value
    token.children = children


def _semantic_blocks(markdown: MarkdownIt):  # type: ignore[no-untyped-def]
    def transform(state):  # type: ignore[no-untyped-def]
        tokens = state.tokens
        for index, token in enumerate(tokens):
            if token.type == "blockquote_open":
                closing = next(
                    (
                        candidate
                        for candidate in tokens[index + 1 :]
                        if candidate.type in {"inline", "blockquote_close"}
                    ),
                    None,
                )
                if closing is not None and closing.type == "inline":
                    match = _CALLOUT_PATTERN.match(closing.content)
                    if match:
                        callout_type = match.group(1).lower()
                        token.attrSet("class", f"callout callout-{callout_type}")
                        token.attrSet("data-callout", callout_type)
                        body = closing.content[match.end() :]
                        _replace_inline_content(markdown, closing, body, state.env)
                        title = Token("html_inline", "", 0)
                        title.content = f'<strong class="callout-title">{escape(callout_type.title())}</strong><br>'
                        closing.children = [title, *(closing.children or [])]

            if token.type == "list_item_open":
                inline = next(
                    (candidate for candidate in tokens[index + 1 :] if candidate.type in {"inline", "list_item_close"}),
                    None,
                )
                if inline is not None and inline.type == "inline":
                    match = _TASK_PATTERN.match(inline.content)
                    if match:
                        checked = match.group(1).lower() == "x"
                        token.attrSet("class", "task-list-item")
                        _replace_inline_content(markdown, inline, inline.content[match.end() :], state.env)
                        checkbox = Token("html_inline", "", 0)
                        checked_attribute = " checked" if checked else ""
                        label = "Completed task" if checked else "Incomplete task"
                        checkbox.content = f'<input type="checkbox" disabled{checked_attribute} aria-label="{label}"> '
                        inline.children = [checkbox, *(inline.children or [])]

            if token.type == "th_open":
                style = token.attrGet("style") or ""
                alignment = next((value for value in ("left", "center", "right") if value in style), None)
                token.attrs = {name: value for name, value in token.attrItems() if name != "style"}
                if alignment:
                    token.attrSet("class", f"align-{alignment}")

        for token in tokens:
            if token.type != "inline" or not token.children:
                continue
            children: list[Token] = []
            for child in token.children:
                if child.type != "text" or "==" not in child.content:
                    children.append(child)
                    continue
                cursor = 0
                for match in _HIGHLIGHT_PATTERN.finditer(child.content):
                    if match.start() > cursor:
                        plain = Token("text", "", 0)
                        plain.content = child.content[cursor : match.start()]
                        children.append(plain)
                    opening = Token("mark_open", "mark", 1)
                    closing = Token("mark_close", "mark", -1)
                    marked = Token("text", "", 0)
                    marked.content = match.group(1)
                    children.extend((opening, marked, closing))
                    cursor = match.end()
                if cursor < len(child.content):
                    plain = Token("text", "", 0)
                    plain.content = child.content[cursor:]
                    children.append(plain)
            token.children = children

    markdown.core.ruler.after("inline", "tekdocs_semantic_blocks", transform)


def _entity_reference_cards(markdown: MarkdownIt):  # type: ignore[no-untyped-def]
    def transform(state):  # type: ignore[no-untyped-def]
        mentions = state.env.get("entity_mentions", {})
        if not isinstance(mentions, Mapping):
            mentions = {}
        for token in state.tokens:
            if token.type != "inline" or not token.children:
                continue
            children = token.children
            index = 0
            while index < len(children):
                opening = children[index]
                if opening.type != "link_open":
                    index += 1
                    continue
                target = opening.attrGet("href") or ""
                match = _ENTITY_TARGET_PATTERN.fullmatch(target)
                if match is None:
                    index += 1
                    continue
                closing_index = next(
                    (
                        candidate
                        for candidate in range(index + 1, len(children))
                        if children[candidate].type == "link_close"
                    ),
                    None,
                )
                if closing_index is None:
                    index += 1
                    continue
                entity_id = str(UUID(match.group(1)))
                projection = mentions.get(entity_id)
                opening.type = "span_open"
                opening.tag = "span"
                opening.attrs = {}
                opening.attrSet("data-entity-id", entity_id)
                label = Token("text", "", 0)
                if isinstance(projection, Mapping):
                    display_name = str(projection.get("display_name", "Referenced record"))
                    entity_type = str(projection.get("entity_type", "record"))
                    entity_type_label = entity_type.replace("_", " ")
                    workspace_label = str(projection.get("workspace_label", ""))
                    opening.attrSet("class", "entity-reference")
                    opening.attrSet("data-entity-type", entity_type)
                    opening.attrSet("aria-label", f"{entity_type_label} reference: {display_name}")
                    label.content = f"{display_name} · {entity_type_label} · {workspace_label}"
                else:
                    opening.attrSet("class", "entity-reference entity-reference-unavailable")
                    opening.attrSet("aria-label", "Unavailable entity reference")
                    label.content = "Unavailable reference"
                closing = children[closing_index]
                closing.type = "span_close"
                closing.tag = "span"
                children[index + 1 : closing_index] = [label]
                index += 3

    markdown.core.ruler.after("tekdocs_semantic_blocks", "tekdocs_entity_reference_cards", transform)


def _attachment_reference_cards(markdown: MarkdownIt):  # type: ignore[no-untyped-def]
    def transform(state):  # type: ignore[no-untyped-def]
        attachments = state.env.get("attachments", {})
        if not isinstance(attachments, Mapping):
            attachments = {}
        for token in state.tokens:
            if token.type != "inline" or not token.children:
                continue
            children = token.children
            index = 0
            while index < len(children):
                opening = children[index]
                if opening.type != "link_open":
                    index += 1
                    continue
                match = _ATTACHMENT_TARGET_PATTERN.fullmatch(opening.attrGet("href") or "")
                if match is None:
                    index += 1
                    continue
                closing_index = next(
                    (
                        candidate
                        for candidate in range(index + 1, len(children))
                        if children[candidate].type == "link_close"
                    ),
                    None,
                )
                if closing_index is None:
                    index += 1
                    continue
                attachment_id = str(UUID(match.group(1)))
                projection = attachments.get(attachment_id)
                label = Token("text", "", 0)
                if isinstance(projection, Mapping):
                    filename = str(projection.get("filename", "Managed attachment"))
                    size = int(projection.get("size", 0))
                    download_url = str(projection.get("download_url", ""))
                    opening.attrs = {}
                    if download_url:
                        opening.attrSet("href", download_url)
                    else:
                        opening.type = "span_open"
                        opening.tag = "span"
                        closing = children[closing_index]
                        closing.type = "span_close"
                        closing.tag = "span"
                    opening.attrSet("class", "attachment-reference")
                    opening.attrSet("data-attachment-id", attachment_id)
                    opening.attrSet("aria-label", f"Download attachment: {filename}")
                    label.content = f"{filename} · {size} bytes"
                else:
                    opening.type = "span_open"
                    opening.tag = "span"
                    opening.attrs = {}
                    opening.attrSet("class", "attachment-reference attachment-reference-unavailable")
                    opening.attrSet("data-attachment-id", attachment_id)
                    opening.attrSet("aria-label", "Unavailable attachment reference")
                    closing = children[closing_index]
                    closing.type = "span_close"
                    closing.tag = "span"
                    label.content = "Unavailable attachment"
                children[index + 1 : closing_index] = [label]
                index += 3

    markdown.core.ruler.after("tekdocs_entity_reference_cards", "tekdocs_attachment_reference_cards", transform)


_MARKDOWN = (
    MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
    .enable(("table", "strikethrough"))
    .use(footnote_plugin)
    .use(_semantic_blocks)
    .use(_entity_reference_cards)
    .use(_attachment_reference_cards)
)
_REFERENCE_SCAN_MARKDOWN = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "input",
    "li",
    "mark",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "span",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
_ATTRIBUTES = {
    "a": {"href", "title", "id", "class", "aria-label", "data-attachment-id"},
    "blockquote": {"class", "data-callout"},
    "code": {"class"},
    "input": {"type", "checked", "disabled", "aria-label"},
    "li": {"id", "class"},
    "ol": {"class"},
    "strong": {"class"},
    "span": {"class", "data-entity-id", "data-entity-type", "data-attachment-id", "aria-label"},
    "th": {"class"},
}
_URL_SCHEMES = {"http", "https", "mailto", "tekdocs"}


def split_markdown_sections(markdown: str, *, limit: int = 500) -> list[tuple[str, str]]:
    """Split imported Markdown at top-level semantic boundaries without splitting constructs."""

    if not markdown:
        return [("rich_text", "")]
    if re.search(r"\[\^[^\]\n]+\]", markdown):
        # Footnote definitions and references must remain in one render context.
        return [("rich_text", markdown.strip("\n"))]
    lines = markdown.splitlines(keepends=True)
    candidates: list[tuple[int, int, str]] = []
    for token in _MARKDOWN.parse(markdown):
        if token.level != 0 or token.map is None:
            continue
        start, end = token.map
        if end <= start or (candidates and start < candidates[-1][1]):
            continue
        kind = (
            "heading"
            if token.type == "heading_open"
            else "code"
            if token.type in {"fence", "code_block"}
            else "rich_text"
        )
        candidates.append((start, end, kind))

    sections: list[tuple[str, str]] = []
    cursor = 0
    for start, end, kind in candidates:
        if start > cursor and "".join(lines[cursor:start]).strip():
            sections.append(("rich_text", "".join(lines[cursor:start]).strip("\n")))
        content = "".join(lines[start:end]).strip("\n")
        if content:
            sections.append((kind, content))
        cursor = max(cursor, end)
    if cursor < len(lines) and "".join(lines[cursor:]).strip():
        sections.append(("rich_text", "".join(lines[cursor:]).strip("\n")))
    if not sections:
        sections = [("rich_text", markdown.strip("\n"))]
    if len(sections) > limit:
        retained = sections[: limit - 1]
        retained.append(("rich_text", "\n\n".join(content for _, content in sections[limit - 1 :])))
        return retained
    return sections


def entity_ids_in_markdown(markdown: str) -> set[UUID]:
    entity_ids: set[UUID] = set()
    for token in _REFERENCE_SCAN_MARKDOWN.parse(markdown):
        for child in token.children or ():
            if child.type != "link_open":
                continue
            target = child.attrGet("href")
            if not isinstance(target, str):
                continue
            match = _ENTITY_TARGET_PATTERN.fullmatch(target)
            if match is not None:
                entity_ids.add(UUID(match.group(1)))
    return entity_ids


def attachment_ids_in_markdown(markdown: str) -> set[UUID]:
    attachment_ids: set[UUID] = set()
    for token in _REFERENCE_SCAN_MARKDOWN.parse(markdown):
        for child in token.children or ():
            if child.type != "link_open":
                continue
            target = child.attrGet("href")
            if not isinstance(target, str):
                continue
            match = _ATTACHMENT_TARGET_PATTERN.fullmatch(target)
            if match is not None:
                attachment_ids.add(UUID(match.group(1)))
    return attachment_ids


def render_markdown(
    markdown: str,
    *,
    entity_mentions: Mapping[str, RenderedEntityMention] | None = None,
    attachments: Mapping[str, RenderedAttachment] | None = None,
) -> str:
    rendered = _MARKDOWN.render(
        markdown,
        {"entity_mentions": entity_mentions or {}, "attachments": attachments or {}},
    )
    return nh3.clean(rendered, tags=_TAGS, attributes=_ATTRIBUTES, url_schemes=_URL_SCHEMES)


def render_pdf(
    markdown: str,
    *,
    title: str = "TekDocs publication",
    publication_id: str = "",
    published_at: str = "",
    audience: str = "",
    reason: str = "",
    diagrams: tuple[DiagramExportArtifact, ...] = (),
) -> bytes:
    output = BytesIO()
    styles = getSampleStyleSheet()
    story: list[Flowable] = []
    heading_level: int | None = None
    list_depth = 0
    table_rows: list[list[Flowable]] | None = None
    table_row: list[Flowable] | None = None
    table_header_cell = False
    diagram_index = 0

    if publication_id:
        story.extend(
            (
                Paragraph(escape(title), styles["Title"]),
                Paragraph(
                    escape(f"STATIC publication {publication_id} | Published {published_at} | Audience {audience}"),
                    styles["BodyText"],
                ),
                Paragraph(escape(f"Publication reason: {reason}"), styles["BodyText"]),
                Spacer(1, 14),
            )
        )

    for token in _MARKDOWN.parse(markdown):
        if token.type == "table_open":
            table_rows = []
        elif token.type == "tr_open" and table_rows is not None:
            table_row = []
        elif token.type == "th_open":
            table_header_cell = True
        elif token.type in {"th_close", "td_close"}:
            table_header_cell = False
        elif token.type == "tr_close" and table_rows is not None and table_row is not None:
            table_rows.append(table_row)
            table_row = None
        elif token.type == "table_close" and table_rows:
            table = Table(table_rows, repeatRows=1, hAlign="LEFT")
            table.setStyle(
                TableStyle(
                    (
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8ECE8")),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#808780")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    )
                )
            )
            story.extend((table, Spacer(1, 8)))
            table_rows = None
        elif token.type == "heading_open":
            heading_level = int(token.tag[1])
        elif token.type == "heading_close":
            heading_level = None
        elif token.type in {"bullet_list_open", "ordered_list_open"}:
            list_depth += 1
        elif token.type in {"bullet_list_close", "ordered_list_close"}:
            list_depth = max(0, list_depth - 1)
        elif token.type == "inline" and token.content.strip():
            if table_row is not None:
                cell_style = styles["Heading5"] if table_header_cell else styles["BodyText"]
                table_row.append(Paragraph(escape(token.content), cell_style))
            else:
                style = styles[f"Heading{min(heading_level, 3)}"] if heading_level else styles["BodyText"]
                prefix = f"{'  ' * (list_depth - 1)}- " if list_depth else ""
                story.extend((Paragraph(escape(prefix + token.content), style), Spacer(1, 6)))
        elif token.type == "fence" and token.info.strip().casefold() == "mermaid":
            item = diagrams[diagram_index] if diagram_index < len(diagrams) else None
            diagram_index += 1
            title_text = item.source.title if item is not None else "Technical diagram"
            story.append(Paragraph(escape(title_text), styles["Heading3"]))
            if item is not None and item.source.description:
                story.append(Paragraph(escape(item.source.description), styles["BodyText"]))
            if item is not None and item.png is not None:
                image = Image(BytesIO(item.png), width=468, height=312, kind="proportional")
                image._restrictSize(468, 360)
                story.extend((image, Spacer(1, 6)))
            else:
                story.append(
                    Paragraph("The diagram could not be rendered; its canonical source follows.", styles["BodyText"])
                )
            story.extend((Preformatted(token.content, styles["Code"]), Spacer(1, 6)))
        elif token.type in {"fence", "code_block"}:
            story.extend((Preformatted(token.content, styles["Code"]), Spacer(1, 6)))

    if not story:
        story.append(Paragraph(" ", styles["BodyText"]))

    document = SimpleDocTemplate(
        output,
        pagesize=LETTER,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54,
        title=title,
        author="TekDocs",
    )

    def invariant_canvas(*args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["invariant"] = 1
        return Canvas(*args, **kwargs)

    def page_footer(canvas, doc):  # type: ignore[no-untyped-def]
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        footer = (
            f"TekDocs STATIC {publication_id} | Page {doc.page}"
            if publication_id
            else f"TekDocs | Page {doc.page}"
        )
        canvas.drawString(54, 28, footer)
        canvas.restoreState()

    document.build(story, canvasmaker=invariant_canvas, onFirstPage=page_footer, onLaterPages=page_footer)
    return output.getvalue()
