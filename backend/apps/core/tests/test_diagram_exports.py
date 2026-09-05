from __future__ import annotations

import base64
import hashlib
import os
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from django.test import override_settings

from apps.core.diagram_exports import (
    MAX_DIAGRAMS,
    MAX_SOURCE_CHARACTERS,
    RENDERER_FAILURE_TO_DIAGRAM_CODE,
    UNRENDERED_VERSION,
    DiagramExportArtifact,
    DiagramRenderError,
    DiagramSource,
    _rejected_detail,
    diagram_family,
    diagram_manifest,
    diagram_render_wait_seconds,
    diagram_sources,
    embed_diagrams_in_html,
    render_diagram_exports,
    sanitize_svg,
)
from apps.core.document_exports import (
    DocumentExportSnapshot,
    export_bundle,
    export_docx,
    export_html,
    export_pdf,
)
from apps.core.publications import retained_publication_diagrams

MARKDOWN = """```mermaid
flowchart LR
  accTitle: Request path
  accDescr: A request moves from browser to API.
  Browser --> API
```
"""


def test_mermaid_source_metadata_and_manifest_are_stable():
    source = diagram_sources(MARKDOWN)[0]
    assert source.index == 1
    assert source.title == "Request path"
    assert source.description == "A request moves from browser to API."
    assert source.family == "flowchart"
    assert source.source_checksum == hashlib.sha256(source.source.encode()).hexdigest()

    artifact = DiagramExportArtifact(
        source=source,
        state="rendered",
        renderer_version="renderer-test",
        svg=b"<svg><title>Request path</title></svg>",
        png=b"\x89PNG\r\n\x1a\ncontent",
    )
    record = diagram_manifest((artifact,))[0]
    assert record["source_checksum"] == source.source_checksum
    assert record["svg_checksum"] == hashlib.sha256(artifact.svg or b"").hexdigest()
    assert record["png_checksum"] == hashlib.sha256(artifact.png or b"").hexdigest()
    assert record["family"] == "flowchart"
    assert "path" not in record


@override_settings(TEKDOCS_DIAGRAM_JOB_DIRECTORY="")
def test_editable_render_falls_back_but_required_render_fails_closed():
    fallback = render_diagram_exports(MARKDOWN)
    assert fallback[0].state == "text_fallback"
    assert fallback[0].svg is None
    with pytest.raises(DiagramRenderError, match="unavailable") as caught:
        render_diagram_exports(MARKDOWN, required=True)
    assert caught.value.code == "diagram.renderer.unavailable"


@pytest.mark.parametrize(
    ("markdown", "expected_code"),
    (
        (
            f"```mermaid\nflowchart LR\nA[{'x' * MAX_SOURCE_CHARACTERS}]\n```\n",
            "diagram.source.oversized",
        ),
        (
            "\n".join("```mermaid\nflowchart LR\nA-->B\n```" for _ in range(MAX_DIAGRAMS + 1)),
            "diagram.count.exceeded",
        ),
        (
            "```mermaid\n%%{init: {'theme': 'dark'}}%%\nflowchart LR\nA-->B\n```\n",
            "diagram.directive.unsupported",
        ),
        (
            "```mermaid\n---\nconfig:\n  theme: dark\n---\nflowchart LR\nA-->B\n```\n",
            "diagram.directive.unsupported",
        ),
    ),
)
def test_source_policy_failures_have_stable_codes(markdown, expected_code):
    with pytest.raises(DiagramRenderError) as caught:
        diagram_sources(markdown)

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ("flowchart LR\nA-->B", "flowchart"),
        ("graph TD\nA-->B", "flowchart"),
        ("sequenceDiagram\nA->>B: Request", "sequence"),
        ("classDiagram\nclass Router", "class"),
        ("stateDiagram-v2\n[*] --> Ready", "state"),
        ("stateDiagram\n[*] --> Ready", "state"),
        ("erDiagram\nCUSTOMER ||--o{ ORDER : places", "entity_relationship"),
        ("%% a comment\naccTitle: Timeline\ngantt\ntitle Work", "unsupported"),
        ("", "unsupported"),
    ),
)
def test_diagram_family_contract_is_stable(source, expected):
    assert diagram_family(source) == expected


@override_settings(TEKDOCS_DIAGRAM_RENDER_TIMEOUT_SECONDS=60)
@pytest.mark.parametrize(("count", "expected"), ((1, 41), (5, 60), (20, 60)))
def test_diagram_batch_wait_is_bounded_and_scales_with_document_size(count, expected):
    assert diagram_render_wait_seconds(count) == expected


def test_svg_sanitizer_rejects_active_and_external_content():
    with pytest.raises(DiagramRenderError, match="unsafe") as active:
        sanitize_svg(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
    assert active.value.code == "diagram.output.unsafe"
    with pytest.raises(DiagramRenderError, match="unsafe") as external:
        sanitize_svg(b'<svg xmlns="http://www.w3.org/2000/svg"><style>.x{fill:url(https://bad)}</style></svg>')
    assert external.value.code == "diagram.output.unsafe"


@pytest.mark.parametrize(
    "svg",
    (
        '<svg xmlns="http://www.w3.org/2000/svg"><rect style="fill:u\\72l(\\68ttps\\3a//example.invalid/x)"/></svg>',
        (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<rect style="fill:&#x75;rl(&#x68;ttps&#x3a;//example.invalid/x)"/></svg>'
        ),
        (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<style>.x{fill:&#x75;rl(&#x68;ttps&#x3a;//example.invalid/x)}</style></svg>'
        ),
    ),
)
def test_svg_sanitizer_rejects_obfuscated_external_css_references(svg):
    with pytest.raises(DiagramRenderError, match="unsafe"):
        sanitize_svg(svg.encode())


def test_exported_html_has_graphic_alt_text_and_source_fallback():
    source = DiagramSource(1, "flowchart LR\nA-->B", "a" * 64, "Service flow", "A reaches B.")
    artifact = DiagramExportArtifact(
        source=source,
        state="rendered",
        renderer_version="renderer-test",
        svg=b"<svg><title>Service flow</title></svg>",
        png=b"\x89PNG\r\n\x1a\ncontent",
    )
    html = embed_diagrams_in_html(
        '<pre><code class="language-mermaid">flowchart LR\nA--&gt;B</code></pre>',
        (artifact,),
    )
    assert 'alt="Service flow"' in html
    assert "A reaches B." in html
    assert "Accessible diagram source" in html
    assert "flowchart LR" in html


def test_graphical_artifacts_are_carried_by_every_derived_export():
    source = DiagramSource(1, "flowchart LR\nA-->B", "a" * 64, "Service flow", "A reaches B.")
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    artifact = DiagramExportArtifact(
        source=source,
        state="rendered",
        renderer_version="renderer-test",
        svg=b"<svg><title>Service flow</title></svg>",
        png=png,
    )
    markdown = "```mermaid\nflowchart LR\nA-->B\n```\n"
    html = export_html(title="Runbook", markdown=markdown, diagrams=(artifact,))
    assert b"Content-Security-Policy" in html
    assert b"data:image/svg+xml;base64," in html
    assert export_pdf(title="Runbook", markdown=markdown, diagrams=(artifact,)).startswith(b"%PDF")
    docx = export_docx(title="Runbook", markdown=markdown, diagrams=(artifact,))
    with ZipFile(BytesIO(docx)) as archive:
        assert any(name.startswith("word/media/") for name in archive.namelist())
        assert b"flowchart LR" in archive.read("word/document.xml")
    snapshot = DocumentExportSnapshot(
        title="Runbook",
        markdown=markdown,
        sanitized_html=export_html(title="Runbook", markdown=markdown, diagrams=(artifact,)).decode(),
        manifest={"diagrams": diagram_manifest((artifact,))},
        digest="b" * 64,
        attachments=(),
        diagrams=(artifact,),
    )
    with ZipFile(BytesIO(export_bundle(snapshot))) as archive:
        assert archive.read("diagrams/001.svg") == artifact.svg
        assert archive.read("diagrams/001.png") == artifact.png
        assert archive.read("document/document.md") == markdown.encode()


def test_pre_0824_static_manifest_keeps_text_fallback_compatibility():
    publication = SimpleNamespace(canonical_markdown=MARKDOWN, manifest={"format": "tekdocs-static-publication/v2"})
    diagrams = retained_publication_diagrams(publication)
    assert diagrams[0].state == "text_fallback"
    assert diagrams[0].renderer_version == "legacy-static-text-fallback"


SUPPORTED_FAMILY_MARKDOWN = MARKDOWN + """
```mermaid
sequenceDiagram
  accTitle: Request exchange
  accDescr: A browser sends a request to an API.
  participant Browser
  participant API
  Browser->>API: Request
```

```mermaid
classDiagram
  accTitle: Service classes
  accDescr: A router depends on a switch.
  class Router
  class Switch
  Router --> Switch
```

```mermaid
stateDiagram-v2
  accTitle: Device state
  accDescr: A device moves from offline to ready.
  [*] --> Offline
  Offline --> Ready
```

```mermaid
erDiagram
  accTitle: Customer orders
  accDescr: A customer may place several orders.
  CUSTOMER ||--o{ ORDER : places
```
"""


@pytest.mark.renderer_runtime
def test_supported_diagram_families_render_when_runtime_is_requested(settings):
    if os.environ.get("TEKDOCS_RUN_DIAGRAM_RUNTIME") != "true":
        pytest.skip("isolated renderer runtime not configured")
    artifacts = render_diagram_exports(SUPPORTED_FAMILY_MARKDOWN, required=True)
    assert tuple(item.source.family for item in artifacts) == (
        "flowchart",
        "sequence",
        "class",
        "state",
        "entity_relationship",
    )
    assert all(item.state == "rendered" for item in artifacts)
    assert all(item.svg and item.svg.startswith(b"<svg") for item in artifacts)
    assert all(item.png and item.png.startswith(b"\x89PNG\r\n\x1a\n") for item in artifacts)


@pytest.mark.renderer_runtime
def test_isolated_renderer_is_deterministic_when_runtime_is_requested(settings):
    if os.environ.get("TEKDOCS_RUN_DIAGRAM_RUNTIME") != "true":
        pytest.skip("isolated renderer runtime not configured")
    first = render_diagram_exports(MARKDOWN, required=True)[0]
    second = render_diagram_exports(MARKDOWN, required=True)[0]
    assert first.svg_checksum == second.svg_checksum
    assert first.png_checksum == second.png_checksum
    assert first.svg == second.svg
    assert first.png == second.png


@pytest.mark.parametrize(
    ("reported", "expected"),
    (
        ({"status": "error", "code": "renderer_timeout"}, "renderer_timeout"),
        ({"status": "error", "code": "oversized_render"}, "oversized_render"),
        ({"status": "error", "code": "raster_failed"}, "raster_failed"),
        # A renderer result is input. An unrecognised code is reported as such rather
        # than repeated into a message an operator would read as authoritative.
        ({"status": "error", "code": "<script>alert(1)</script>"}, "unrecognised result"),
        ({"status": "error"}, "unrecognised result"),
        ({"status": "ok", "count": 99, "renderer": "@mermaid-js/mermaid-cli@11.16.0"}, "unrecognised result"),
        # A version this module cannot recognise is refused rather than recorded: the
        # value ends up in a signed manifest, so unvalidated renderer text must not reach it.
        ({"status": "ok", "count": 1, "renderer": "totally-different-renderer"}, "unrecognised renderer version"),
        (
            {"status": "ok", "count": 1, "renderer": "@mermaid-js/mermaid-cli@not.a.version"},
            "unrecognised renderer version",
        ),
        ({"status": "ok", "count": 1}, "unrecognised renderer version"),
        ("not a mapping at all", "unrecognised result"),
    ),
)
def test_a_rejected_render_names_which_failure_the_renderer_reported(reported, expected):
    assert _rejected_detail(reported, expected_count=1) == expected


@pytest.mark.parametrize(
    ("renderer_code", "finding_code"),
    (
        ("render_failed", "diagram.source.invalid"),
        ("renderer_timeout", "diagram.renderer.timeout"),
        ("incomplete_render", "diagram.output.incomplete"),
        ("oversized_render", "diagram.output.oversized"),
        ("raster_failed", "diagram.raster.failed"),
    ),
)
def test_renderer_failures_map_to_stable_preflight_codes(renderer_code, finding_code):
    assert RENDERER_FAILURE_TO_DIAGRAM_CODE[renderer_code] == finding_code


def test_a_successful_render_result_is_not_reported_as_a_failure():
    ok = {"status": "ok", "count": 2, "renderer": "@mermaid-js/mermaid-cli@11.16.0"}

    assert _rejected_detail(ok, expected_count=2) is None
    # A count that disagrees with what was asked for is a failure, not a success.
    assert _rejected_detail(ok, expected_count=3) == "unrecognised result"


def test_a_newer_renderer_version_is_accepted_without_a_code_change():
    # The point of reading the version from the renderer: a dependency bump must not
    # require editing this module, and must not silently attest the old version.
    later = {"status": "ok", "count": 1, "renderer": "@mermaid-js/mermaid-cli@11.17.3"}

    assert _rejected_detail(later, expected_count=1) is None


def test_an_artifact_that_never_rendered_claims_no_renderer():
    from apps.core.diagram_exports import _fallback, diagram_sources

    sources = diagram_sources("```mermaid\nflowchart LR\nA-->B\n```\n")

    assert _fallback(sources)[0].renderer_version == UNRENDERED_VERSION
