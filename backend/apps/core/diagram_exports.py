from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import time
from dataclasses import dataclass
from html import escape
from pathlib import Path
from uuid import uuid4

import nh3
from django.conf import settings
from markdown_it import MarkdownIt

MAX_DIAGRAMS = 20
MAX_SOURCE_CHARACTERS = 50_000
MAX_SVG_BYTES = 2 * 1024 * 1024
MAX_PNG_BYTES = 5 * 1024 * 1024
MAX_ACTIVE_JOBS = 8
RENDERER_VERSION = "@mermaid-js/mermaid-cli@11.16.0"
_MARKDOWN = MarkdownIt("commonmark", {"html": False})
_TITLE = re.compile(r"^\s*accTitle:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_DESCRIPTION = re.compile(r"^\s*accDescr:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_JOB_ID = re.compile(r"^[0-9a-f]{32}$")
_RENDERED_FENCE = re.compile(r'<pre><code class="language-mermaid">.*?</code></pre>\s*', re.DOTALL)
_SVG_TAGS = {
    "circle",
    "clipPath",
    "defs",
    "desc",
    "ellipse",
    "g",
    "line",
    "marker",
    "path",
    "polygon",
    "polyline",
    "rect",
    "style",
    "svg",
    "text",
    "title",
    "tspan",
}
_SVG_ATTRIBUTES = {
    "*": {
        "aria-describedby",
        "aria-labelledby",
        "class",
        "clip-path",
        "d",
        "dominant-baseline",
        "fill",
        "fill-opacity",
        "font-family",
        "font-size",
        "font-style",
        "font-weight",
        "height",
        "id",
        "marker-end",
        "marker-height",
        "marker-start",
        "marker-units",
        "marker-width",
        "orient",
        "points",
        "preserveAspectRatio",
        "refX",
        "refY",
        "role",
        "rx",
        "ry",
        "stroke",
        "stroke-dasharray",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-opacity",
        "stroke-width",
        "style",
        "text-anchor",
        "transform",
        "viewBox",
        "width",
        "x",
        "x1",
        "x2",
        "xmlns",
        "y",
        "y1",
        "y2",
    }
}


class DiagramRenderError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DiagramSource:
    index: int
    source: str
    source_checksum: str
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class DiagramExportArtifact:
    source: DiagramSource
    state: str
    renderer_version: str
    svg: bytes | None = None
    png: bytes | None = None

    @property
    def svg_checksum(self) -> str | None:
        return hashlib.sha256(self.svg).hexdigest() if self.svg is not None else None

    @property
    def png_checksum(self) -> str | None:
        return hashlib.sha256(self.png).hexdigest() if self.png is not None else None


def diagram_sources(markdown: str) -> tuple[DiagramSource, ...]:
    values: list[DiagramSource] = []
    for token in _MARKDOWN.parse(markdown):
        if token.type != "fence" or token.info.strip().casefold() != "mermaid":
            continue
        source = token.content.rstrip("\n")
        if len(source) > MAX_SOURCE_CHARACTERS:
            raise DiagramRenderError("A Mermaid diagram exceeds the 50,000-character limit.")
        if len(values) >= MAX_DIAGRAMS:
            raise DiagramRenderError("A document may contain at most 20 Mermaid diagrams.")
        title_match = _TITLE.search(source)
        description_match = _DESCRIPTION.search(source)
        values.append(
            DiagramSource(
                index=len(values) + 1,
                source=source,
                source_checksum=hashlib.sha256(source.encode("utf-8")).hexdigest(),
                title=(title_match.group(1).strip() if title_match else "Technical diagram")[:240],
                description=(description_match.group(1).strip() if description_match else "")[:1000],
            )
        )
    return tuple(values)


def _sanitize_svg(content: bytes) -> bytes:
    if len(content) > MAX_SVG_BYTES:
        raise DiagramRenderError("A rendered diagram exceeds the SVG size limit.")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DiagramRenderError("The diagram renderer returned invalid SVG.") from exc
    lowered = text.casefold()
    scanned = lowered.replace('xmlns="http://www.w3.org/2000/svg"', "").replace(
        'xmlns:xlink="http://www.w3.org/1999/xlink"', ""
    )
    forbidden = ("<script", "<foreignobject", "javascript:", "data:", "http:", "https:", "@import")
    if any(value in scanned for value in forbidden):
        raise DiagramRenderError("The diagram renderer returned unsafe SVG.")
    for match in re.finditer(r"url\(([^)]*)\)", text, re.IGNORECASE):
        reference = match.group(1).strip().strip("'\"")
        if not reference.startswith("#"):
            raise DiagramRenderError("The diagram renderer returned an unsafe SVG reference.")
    for style in re.findall(r"<style(?:\s[^>]*)?>(.*?)</style>", text, re.IGNORECASE | re.DOTALL):
        if "\\" in style:
            raise DiagramRenderError("The diagram renderer returned unsafe SVG styling.")
    cleaned = nh3.clean(
        text,
        tags=_SVG_TAGS,
        attributes=_SVG_ATTRIBUTES,
        clean_content_tags=set(),
        url_schemes=set(),
    ).strip()
    if not cleaned.startswith("<svg") or "</svg>" not in cleaned:
        raise DiagramRenderError("The diagram renderer returned invalid SVG.")
    encoded = cleaned.encode("utf-8")
    if len(encoded) > MAX_SVG_BYTES:
        raise DiagramRenderError("A sanitized diagram exceeds the SVG size limit.")
    return encoded


def _fallback(sources: tuple[DiagramSource, ...]) -> tuple[DiagramExportArtifact, ...]:
    return tuple(
        DiagramExportArtifact(source=source, state="text_fallback", renderer_version=RENDERER_VERSION)
        for source in sources
    )


def render_diagram_exports(markdown: str, *, required: bool = False) -> tuple[DiagramExportArtifact, ...]:
    sources = diagram_sources(markdown)
    if not sources:
        return ()
    configured = str(getattr(settings, "TEKDOCS_DIAGRAM_JOB_DIRECTORY", "")).strip()
    if not configured:
        if required:
            raise DiagramRenderError("The isolated diagram renderer is unavailable.")
        return _fallback(sources)
    root = Path(configured)
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        if required:
            raise DiagramRenderError("The isolated diagram renderer is unavailable.")
        return _fallback(sources)
    active = sum(1 for item in root.iterdir() if item.is_dir() and _JOB_ID.fullmatch(item.name))
    if active >= MAX_ACTIVE_JOBS:
        if required:
            raise DiagramRenderError("The isolated diagram renderer is busy.")
        return _fallback(sources)

    job = root / uuid4().hex
    try:
        job.mkdir(mode=0o700)
        markdown_batch = "\n\n".join(f"```mermaid\n{source.source}\n```" for source in sources) + "\n"
        input_path = job / "input.md"
        request_path = job / "request.json"
        ready_path = job / "ready"
        input_path.write_text(markdown_batch, encoding="utf-8")
        request_path.write_text(
            json.dumps({"count": len(sources)}, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        ready_path.write_bytes(b"")
        for path in (input_path, request_path, ready_path):
            path.chmod(0o600)
        deadline = time.monotonic() + int(getattr(settings, "TEKDOCS_DIAGRAM_RENDER_TIMEOUT_SECONDS", 20))
        result_path = job / "result.json"
        while time.monotonic() < deadline and not result_path.is_file():
            time.sleep(0.05)
        if not result_path.is_file():
            raise DiagramRenderError("The isolated diagram renderer timed out.")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result != {"status": "ok", "count": len(sources), "renderer": RENDERER_VERSION}:
            raise DiagramRenderError("The isolated diagram renderer rejected the diagram.")
        artifacts: list[DiagramExportArtifact] = []
        for source in sources:
            svg = _sanitize_svg((job / f"output-{source.index}.svg").read_bytes())
            png = (job / f"output-{source.index}.png").read_bytes()
            if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > MAX_PNG_BYTES:
                raise DiagramRenderError("The diagram renderer returned invalid PNG output.")
            artifacts.append(
                DiagramExportArtifact(
                    source=source,
                    state="rendered",
                    renderer_version=RENDERER_VERSION,
                    svg=svg,
                    png=png,
                )
            )
        return tuple(artifacts)
    except (DiagramRenderError, OSError, ValueError, json.JSONDecodeError):
        if required:
            raise DiagramRenderError("A required diagram could not be rendered reproducibly.") from None
        return _fallback(sources)
    finally:
        shutil.rmtree(job, ignore_errors=True)


def diagram_manifest(artifacts: tuple[DiagramExportArtifact, ...]) -> list[dict[str, object]]:
    return [
        {
            "index": item.source.index,
            "title": item.source.title,
            "description": item.source.description,
            "source_checksum": item.source.source_checksum,
            "renderer_version": item.renderer_version,
            "state": item.state,
            "svg_checksum": item.svg_checksum,
            "png_checksum": item.png_checksum,
        }
        for item in artifacts
    ]


def html_diagram_figure(item: DiagramExportArtifact) -> str:
    caption = f"<figcaption>{escape(item.source.title)}</figcaption>"
    description = f"<p>{escape(item.source.description)}</p>" if item.source.description else ""
    if item.svg is not None:
        payload = base64.b64encode(item.svg).decode("ascii")
        graphic = f'<img alt="{escape(item.source.title)}" src="data:image/svg+xml;base64,{payload}" role="img">'
    else:
        graphic = "<p>The diagram could not be rendered. Its source remains available below.</p>"
    source = escape(item.source.source)
    return (
        f'<figure class="mermaid-diagram-export">{caption}{description}{graphic}'
        f"<details><summary>Accessible diagram source</summary><pre><code>{source}</code></pre></details></figure>"
    )


def embed_diagrams_in_html(html: str, artifacts: tuple[DiagramExportArtifact, ...]) -> str:
    if not artifacts:
        return html
    cursor = 0

    def replace(_match: re.Match[str]) -> str:
        nonlocal cursor
        if cursor >= len(artifacts):
            raise DiagramRenderError("Rendered diagram count does not match the Markdown source.")
        value = html_diagram_figure(artifacts[cursor])
        cursor += 1
        return value

    result = _RENDERED_FENCE.sub(replace, html)
    if cursor != len(artifacts):
        raise DiagramRenderError("Rendered diagram count does not match the Markdown source.")
    return result
