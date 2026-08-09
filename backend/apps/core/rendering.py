from __future__ import annotations

import re
from html import escape
from io import BytesIO

import nh3
from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.footnote import footnote_plugin
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Paragraph, Preformatted, SimpleDocTemplate, Spacer

CALLOUT_TYPES = frozenset({"note", "tip", "important", "warning", "caution"})
_CALLOUT_PATTERN = re.compile(r"^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\](?:[ \t]*\n|[ \t]+)?")
_HIGHLIGHT_PATTERN = re.compile(r"(?<![\w=])==(?=\S)([^=\n]*?\S)==(?![\w=])")
_TASK_PATTERN = re.compile(r"^\[([ xX])\][ \t]+")


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
                        title.content = (
                            f'<strong class="callout-title">{escape(callout_type.title())}</strong><br>'
                        )
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
                        checkbox.content = (
                            f'<input type="checkbox" disabled{checked_attribute} aria-label="{label}"> '
                        )
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


_MARKDOWN = (
    MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
    .enable(("table", "strikethrough"))
    .use(footnote_plugin)
    .use(_semantic_blocks)
)
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
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
_ATTRIBUTES = {
    "a": {"href", "title", "id", "class", "aria-label"},
    "blockquote": {"class", "data-callout"},
    "code": {"class"},
    "input": {"type", "checked", "disabled", "aria-label"},
    "li": {"id", "class"},
    "ol": {"class"},
    "strong": {"class"},
    "th": {"class"},
}
_URL_SCHEMES = {"http", "https", "mailto", "tekdocs"}


def render_markdown(markdown: str) -> str:
    rendered = _MARKDOWN.render(markdown)
    return nh3.clean(rendered, tags=_TAGS, attributes=_ATTRIBUTES, url_schemes=_URL_SCHEMES)


def render_pdf(markdown: str) -> bytes:
    output = BytesIO()
    styles = getSampleStyleSheet()
    story: list[Flowable] = []
    heading_level: int | None = None
    list_depth = 0

    for token in _MARKDOWN.parse(markdown):
        if token.type == "heading_open":
            heading_level = int(token.tag[1])
        elif token.type == "heading_close":
            heading_level = None
        elif token.type in {"bullet_list_open", "ordered_list_open"}:
            list_depth += 1
        elif token.type in {"bullet_list_close", "ordered_list_close"}:
            list_depth = max(0, list_depth - 1)
        elif token.type == "inline" and token.content.strip():
            style = styles[f"Heading{min(heading_level, 3)}"] if heading_level else styles["BodyText"]
            prefix = f"{'  ' * (list_depth - 1)}• " if list_depth else ""
            story.extend((Paragraph(escape(prefix + token.content), style), Spacer(1, 6)))
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
        title="TekDocs publication",
        author="TekDocs",
    )

    def invariant_canvas(*args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["invariant"] = 1
        return Canvas(*args, **kwargs)

    document.build(story, canvasmaker=invariant_canvas)
    return output.getvalue()
