from __future__ import annotations

from html import escape
from io import BytesIO

import nh3
from markdown_it import MarkdownIt
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Paragraph, Preformatted, SimpleDocTemplate, Spacer

_MARKDOWN = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
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
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
_ATTRIBUTES = {"a": {"href", "title"}, "code": {"class"}}
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
