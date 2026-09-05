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
RENDERER_HEALTH_MAX_AGE_SECONDS = 5
RENDERER_PROCESS_TIMEOUT_BASE_SECONDS = 30
RENDERER_PROCESS_TIMEOUT_PER_DIAGRAM_SECONDS = 6
RENDERER_PROCESS_TIMEOUT_MAX_SECONDS = 55
#: Diagram families TekDocs renders and regression-tests as part of the 1.x
#: compatibility contract. Other Mermaid families remain editable and may render,
#: but publication preflight warns that their output is best-effort.
SUPPORTED_DIAGRAM_FAMILIES = (
    "flowchart",
    "sequence",
    "class",
    "state",
    "entity_relationship",
)
_DIAGRAM_FAMILY_ALIASES = {
    "flowchart": "flowchart",
    "graph": "flowchart",
    "sequencediagram": "sequence",
    "classdiagram": "class",
    "statediagram": "state",
    "statediagram-v2": "state",
    "erdiagram": "entity_relationship",
}
#: The renderer identifies its own version; this module does not keep a second copy to
#: compare against. A duplicated constant cannot be updated by a dependency bump, so it
#: would silently attest the wrong renderer in a signed manifest while every check still
#: passed. What is enforced here is the shape of the report, not its value.
RENDERER_REPORT = re.compile(r"^@mermaid-js/mermaid-cli@[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$")

#: Recorded when no renderer ran. Naming a version here would claim a render that did
#: not happen.
UNRENDERED_VERSION = "not-rendered"

#: The failures the isolated renderer can report. The code is matched against this set
#: before it reaches an error message: the renderer is a separate process writing a file,
#: so its output is input, and unvalidated input does not get interpolated into text an
#: operator will read as authoritative.
RENDERER_FAILURE_CODES = frozenset(
    {
        "invalid_request",
        "render_failed",
        "renderer_timeout",
        "incomplete_render",
        "oversized_render",
        "raster_failed",
        "incomplete_raster",
        "oversized_raster",
    }
)
RENDERER_FAILURE_TO_DIAGRAM_CODE = {
    "invalid_request": "diagram.renderer.invalid_response",
    "render_failed": "diagram.source.invalid",
    "renderer_timeout": "diagram.renderer.timeout",
    "incomplete_render": "diagram.output.incomplete",
    "oversized_render": "diagram.output.oversized",
    "raster_failed": "diagram.raster.failed",
    "incomplete_raster": "diagram.raster.failed",
    "oversized_raster": "diagram.output.oversized",
}
_MARKDOWN = MarkdownIt("commonmark", {"html": False})
_TITLE = re.compile(r"^\s*accTitle:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_DESCRIPTION = re.compile(r"^\s*accDescr:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_JOB_ID = re.compile(r"^[0-9a-f]{32}$")
_MERMAID_DIRECTIVE = re.compile(r"^\s*%%\{", re.MULTILINE)
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
    """A safe diagram failure with a stable preflight code.

    The message may be shown to a person. It must never include Mermaid source,
    renderer stderr, filesystem paths, or other customer-controlled values.
    """

    def __init__(self, message: str, *, code: str = "diagram.render_failed") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class DiagramSource:
    index: int
    source: str
    source_checksum: str
    title: str
    description: str
    family: str = "unsupported"


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


def diagram_family(source: str) -> str:
    """Return a stable contract name without exposing untrusted source tokens."""

    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        folded = stripped.casefold()
        if folded.startswith(("acctitle:", "accdescr:")):
            continue
        token = folded.split(maxsplit=1)[0]
        return _DIAGRAM_FAMILY_ALIASES.get(token, "unsupported")
    return "unsupported"


def diagram_render_wait_seconds(count: int) -> int:
    """Return a bounded wait that covers the renderer's batch-aware deadline."""

    worker_timeout = min(
        RENDERER_PROCESS_TIMEOUT_MAX_SECONDS,
        RENDERER_PROCESS_TIMEOUT_BASE_SECONDS + count * RENDERER_PROCESS_TIMEOUT_PER_DIAGRAM_SECONDS,
    )
    configured_maximum = int(getattr(settings, "TEKDOCS_DIAGRAM_RENDER_TIMEOUT_SECONDS", 60))
    return min(configured_maximum, worker_timeout + 5)


def diagram_sources(markdown: str) -> tuple[DiagramSource, ...]:
    values: list[DiagramSource] = []
    for token in _MARKDOWN.parse(markdown):
        if token.type != "fence" or token.info.strip().casefold() != "mermaid":
            continue
        source = token.content.rstrip("\n")
        if len(source) > MAX_SOURCE_CHARACTERS:
            raise DiagramRenderError(
                "A Mermaid diagram exceeds the 50,000-character limit.",
                code="diagram.source.oversized",
            )
        if len(values) >= MAX_DIAGRAMS:
            raise DiagramRenderError(
                "A document may contain at most 20 Mermaid diagrams.",
                code="diagram.count.exceeded",
            )
        if source.lstrip().startswith("---") or _MERMAID_DIRECTIVE.search(source):
            raise DiagramRenderError(
                "Mermaid configuration directives are not supported.",
                code="diagram.directive.unsupported",
            )
        title_match = _TITLE.search(source)
        description_match = _DESCRIPTION.search(source)
        values.append(
            DiagramSource(
                index=len(values) + 1,
                source=source,
                source_checksum=hashlib.sha256(source.encode("utf-8")).hexdigest(),
                title=(title_match.group(1).strip() if title_match else "Technical diagram")[:240],
                description=(description_match.group(1).strip() if description_match else "")[:1000],
                family=diagram_family(source),
            )
        )
    return tuple(values)


def sanitize_svg(content: bytes) -> bytes:
    if len(content) > MAX_SVG_BYTES:
        raise DiagramRenderError(
            "A rendered diagram exceeds the SVG size limit.",
            code="diagram.output.oversized",
        )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DiagramRenderError(
            "The diagram renderer returned invalid SVG.",
            code="diagram.output.invalid",
        ) from exc
    _validate_svg_content(text)
    cleaned = nh3.clean(
        text,
        tags=_SVG_TAGS,
        attributes=_SVG_ATTRIBUTES,
        clean_content_tags=set(),
        url_schemes=set(),
    ).strip()
    # nh3 decodes character references while normalizing the SVG. Recheck the
    # normalized result so an encoded CSS URL cannot become active after the first
    # inspection. CSS escapes are refused in style contexts because they can hide
    # url(), a scheme, or @import from a textual allowlist.
    _validate_svg_content(cleaned)
    if not cleaned.startswith("<svg") or "</svg>" not in cleaned:
        raise DiagramRenderError(
            "The diagram renderer returned invalid SVG.",
            code="diagram.output.invalid",
        )
    encoded = cleaned.encode("utf-8")
    if len(encoded) > MAX_SVG_BYTES:
        raise DiagramRenderError(
            "A sanitized diagram exceeds the SVG size limit.",
            code="diagram.output.oversized",
        )
    return encoded


def _validate_svg_content(text: str) -> None:
    lowered = text.casefold()
    scanned = lowered.replace('xmlns="http://www.w3.org/2000/svg"', "").replace(
        'xmlns:xlink="http://www.w3.org/1999/xlink"', ""
    )
    forbidden = ("<script", "<foreignobject", "javascript:", "data:", "http:", "https:", "@import")
    if any(value in scanned for value in forbidden):
        raise DiagramRenderError(
            "The diagram renderer returned unsafe SVG.",
            code="diagram.output.unsafe",
        )
    for match in re.finditer(r"url\(([^)]*)\)", text, re.IGNORECASE):
        reference = match.group(1).strip().strip("'\"")
        if not reference.startswith("#"):
            raise DiagramRenderError(
                "The diagram renderer returned an unsafe SVG reference.",
                code="diagram.output.unsafe",
            )
    styles = re.findall(r"<style(?:\s[^>]*)?>(.*?)</style>", text, re.IGNORECASE | re.DOTALL)
    styles.extend(
        match.group(2)
        for match in re.finditer(r"\sstyle\s*=\s*([\"'])(.*?)\1", text, re.IGNORECASE | re.DOTALL)
    )
    if any("\\" in style for style in styles):
        raise DiagramRenderError(
            "The diagram renderer returned unsafe SVG styling.",
            code="diagram.output.unsafe",
        )


def _rejected_detail(result: object, *, expected_count: int) -> str | None:
    """What to report about a renderer result, or None when it is a successful render.

    The renderer is a separate process writing a file, so its result is input. A code is
    repeated only when it is one this module knows; anything else is reported as
    unrecognised rather than interpolated into a message an operator reads as
    authoritative.
    """

    if not isinstance(result, dict):
        return "unrecognised result"
    if result.get("status") != "ok" or result.get("count") != expected_count:
        reported = result.get("code")
        return reported if reported in RENDERER_FAILURE_CODES else "unrecognised result"
    if not RENDERER_REPORT.fullmatch(str(result.get("renderer", ""))):
        return "unrecognised renderer version"
    return None


def _fallback(sources: tuple[DiagramSource, ...]) -> tuple[DiagramExportArtifact, ...]:
    return tuple(
        DiagramExportArtifact(source=source, state="text_fallback", renderer_version=UNRENDERED_VERSION)
        for source in sources
    )


def diagram_renderer_health() -> str:
    """Return a coarse, value-free state for the shared renderer heartbeat."""

    configured = str(getattr(settings, "TEKDOCS_DIAGRAM_JOB_DIRECTORY", "")).strip()
    if not configured:
        return "not_configured"
    root = Path(configured)
    try:
        if not root.is_absolute() or not root.is_dir() or root.is_symlink():
            return "unavailable"
        marker = root / ".renderer-ready"
        if not marker.is_file() or marker.is_symlink():
            return "unavailable"
        if time.time() - marker.stat().st_mtime > RENDERER_HEALTH_MAX_AGE_SECONDS:
            return "stale"
    except OSError:
        return "unavailable"
    return "ready"


def diagram_renderer_diagnostics() -> dict[str, object]:
    """Return bounded, value-free renderer telemetry for authorized operators."""

    status = diagram_renderer_health()
    result: dict[str, object] = {
        "status": status,
        "version": None,
        "capacity": MAX_ACTIVE_JOBS,
        "queue": {"waiting": 0, "processing": 0, "total": 0},
        "recent_failures": [],
        "last_checked_at": None,
    }
    configured = str(getattr(settings, "TEKDOCS_DIAGRAM_JOB_DIRECTORY", "")).strip()
    if not configured:
        return result
    root = Path(configured)
    try:
        if not root.is_absolute() or not root.is_dir() or root.is_symlink():
            return result
        jobs = [item for item in root.iterdir() if item.is_dir() and _JOB_ID.fullmatch(item.name)]
        waiting = sum(1 for item in jobs if (item / "ready").is_file())
        processing = sum(1 for item in jobs if (item / "processing").is_file())
        result["queue"] = {"waiting": waiting, "processing": processing, "total": len(jobs)}
        telemetry_path = root / ".renderer-diagnostics.json"
        if not telemetry_path.is_file() or telemetry_path.is_symlink() or telemetry_path.stat().st_size > 16_384:
            return result
        telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return result
    if not isinstance(telemetry, dict):
        return result
    version = telemetry.get("renderer")
    if isinstance(version, str) and RENDERER_REPORT.fullmatch(version):
        result["version"] = version
    now_ms = int(time.time() * 1000)
    checked_at = telemetry.get("checked_at")
    if isinstance(checked_at, int) and 0 < checked_at <= now_ms + 60_000:
        result["last_checked_at"] = checked_at
    failures: list[dict[str, object]] = []
    reported_failures = telemetry.get("recent_failures")
    if isinstance(reported_failures, list):
        for item in reported_failures[-10:]:
            if not isinstance(item, dict) or item.get("code") not in RENDERER_FAILURE_CODES:
                continue
            occurred_at = item.get("occurred_at")
            if not isinstance(occurred_at, int) or not 0 < occurred_at <= now_ms + 60_000:
                continue
            failures.append({"code": item["code"], "occurred_at": occurred_at})
    result["recent_failures"] = failures
    return result


def render_diagram_exports(markdown: str, *, required: bool = False) -> tuple[DiagramExportArtifact, ...]:
    sources = diagram_sources(markdown)
    if not sources:
        return ()
    configured = str(getattr(settings, "TEKDOCS_DIAGRAM_JOB_DIRECTORY", "")).strip()
    if not configured:
        if required:
            raise DiagramRenderError(
                "The isolated diagram renderer is unavailable.",
                code="diagram.renderer.unavailable",
            )
        return _fallback(sources)
    root = Path(configured)
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        if required:
            raise DiagramRenderError(
                "The isolated diagram renderer is unavailable.",
                code="diagram.renderer.unavailable",
            )
        return _fallback(sources)
    try:
        active = sum(1 for item in root.iterdir() if item.is_dir() and _JOB_ID.fullmatch(item.name))
    except OSError:
        if required:
            raise DiagramRenderError(
                "The isolated diagram renderer is unavailable.",
                code="diagram.renderer.unavailable",
            ) from None
        return _fallback(sources)
    if active >= MAX_ACTIVE_JOBS:
        if required:
            raise DiagramRenderError(
                "The isolated diagram renderer is busy.",
                code="diagram.renderer.busy",
            )
        return _fallback(sources)

    job = root / uuid4().hex
    try:
        job.mkdir(mode=0o700)
        request_path = job / "request.json"
        ready_path = job / "ready"
        input_paths: list[Path] = []
        for source in sources:
            input_path = job / f"input-{source.index}.mmd"
            input_path.write_text(f"{source.source}\n", encoding="utf-8")
            input_paths.append(input_path)
        request_path.write_text(
            json.dumps({"count": len(sources)}, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        ready_path.write_bytes(b"")
        for path in (*input_paths, request_path, ready_path):
            path.chmod(0o600)
        deadline = time.monotonic() + diagram_render_wait_seconds(len(sources))
        result_path = job / "result.json"
        while time.monotonic() < deadline and not result_path.is_file():
            time.sleep(0.05)
        if not result_path.is_file():
            raise DiagramRenderError(
                "The isolated diagram renderer timed out.",
                code="diagram.renderer.timeout",
            )
        result = json.loads(result_path.read_text(encoding="utf-8"))
        detail = _rejected_detail(result, expected_count=len(sources))
        if detail is not None:
            raise DiagramRenderError(
                "The isolated diagram renderer rejected the diagram.",
                code=RENDERER_FAILURE_TO_DIAGRAM_CODE.get(detail, "diagram.renderer.invalid_response"),
            )
        # Validated above, so this is the version that actually produced the bytes below.
        renderer_version = str(result["renderer"])
        artifacts: list[DiagramExportArtifact] = []
        for source in sources:
            svg_path = job / f"output-{source.index}.svg"
            png_path = job / f"output-{source.index}.png"
            if not svg_path.is_file() or not png_path.is_file():
                raise DiagramRenderError(
                    "The diagram renderer did not return every requested artifact.",
                    code="diagram.output.incomplete",
                )
            svg = sanitize_svg(svg_path.read_bytes())
            png = png_path.read_bytes()
            if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > MAX_PNG_BYTES:
                raise DiagramRenderError(
                    "The diagram renderer returned invalid PNG output.",
                    code="diagram.raster.failed",
                )
            artifacts.append(
                DiagramExportArtifact(
                    source=source,
                    state="rendered",
                    renderer_version=renderer_version,
                    svg=svg,
                    png=png,
                )
            )
        return tuple(artifacts)
    except (DiagramRenderError, OSError, ValueError, json.JSONDecodeError) as error:
        if required:
            if isinstance(error, DiagramRenderError):
                raise error from None
            code = "diagram.renderer.unavailable" if isinstance(error, OSError) else "diagram.renderer.invalid_response"
            raise DiagramRenderError("A required diagram could not be rendered.", code=code) from None
        return _fallback(sources)
    finally:
        shutil.rmtree(job, ignore_errors=True)


def diagram_manifest(artifacts: tuple[DiagramExportArtifact, ...]) -> list[dict[str, object]]:
    return [
        {
            "index": item.source.index,
            "title": item.source.title,
            "description": item.source.description,
            "family": item.source.family,
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
