from __future__ import annotations

from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from markdown_it import MarkdownIt

from .rendering import render_markdown, render_pdf

EXPORT_FORMATS = frozenset({"md", "html", "pdf", "docx"})
_MARKDOWN = MarkdownIt("commonmark", {"html": False}).enable("table")


def export_html(*, title: str, markdown: str, retained_html: str | None = None) -> bytes:
    body = retained_html if retained_html is not None else render_markdown(markdown)
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{escape(title)}</title></head><body><main>{body}</main></body></html>\n"
    ).encode()


def export_pdf(*, title: str, markdown: str) -> bytes:
    return render_pdf(markdown, title=title)


def _document_paragraphs(markdown: str) -> list[tuple[str, str]]:
    paragraphs: list[tuple[str, str]] = []
    list_depth = 0
    paragraph_style = "Normal"
    for token in _MARKDOWN.parse(markdown):
        if token.type == "heading_open":
            paragraph_style = f"Heading{token.tag.removeprefix('h')}"
        elif token.type == "heading_close":
            paragraph_style = "Normal"
        elif token.type in {"bullet_list_open", "ordered_list_open"}:
            list_depth += 1
        elif token.type in {"bullet_list_close", "ordered_list_close"}:
            list_depth = max(0, list_depth - 1)
        elif token.type == "inline":
            text = token.content
            if list_depth:
                text = f"• {text}"
            paragraphs.append((paragraph_style, text))
        elif token.type in {"fence", "code_block"}:
            paragraphs.append(("Code", token.content.rstrip()))
    return paragraphs or [("Normal", "")]


def _zip_entry(name: str, content: str) -> tuple[ZipInfo, bytes]:
    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    return info, content.encode("utf-8")


def export_docx(*, title: str, markdown: str) -> bytes:
    paragraphs = [("Title", title), *_document_paragraphs(markdown)]
    body = "".join(
        f'<w:p><w:pPr><w:pStyle w:val="{escape(style)}"/></w:pPr>'
        f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'
        for style, text in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}<w:sectPr/></w:body></w:document>"
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/></w:style>'
        + "".join(
            f'<w:style w:type="paragraph" w:styleId="Heading{level}"><w:name w:val="heading {level}"/></w:style>'
            for level in range(1, 7)
        )
        + "</w:styles>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'
    )
    package_relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    document_relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/></Relationships>'
    )
    entries = (
        ("[Content_Types].xml", content_types),
        ("_rels/.rels", package_relationships),
        ("word/_rels/document.xml.rels", document_relationships),
        ("word/document.xml", document),
        ("word/styles.xml", styles),
    )
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for name, content in entries:
            info, encoded = _zip_entry(name, content)
            archive.writestr(info, encoded)
    return output.getvalue()
