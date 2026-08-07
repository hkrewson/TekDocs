from apps.core.rendering import render_markdown, render_pdf


def test_markdown_renderer_disables_raw_html_and_unsafe_urls() -> None:
    rendered = render_markdown("# Safe\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))")

    assert "<h1>Safe</h1>" in rendered
    assert "<script>" not in rendered
    assert 'href="javascript:' not in rendered


def test_markdown_renderer_preserves_stable_entity_links() -> None:
    rendered = render_markdown("[Router](tekdocs://entity/00000000-0000-4000-8000-000000000001)")

    assert 'href="tekdocs://entity/00000000-0000-4000-8000-000000000001"' in rendered


def test_pdf_renderer_produces_a_pdf_document() -> None:
    rendered = render_pdf("# Static publication\n\nImmutable content.")

    assert rendered.startswith(b"%PDF-")
    assert len(rendered) > 1_000
    assert rendered == render_pdf("# Static publication\n\nImmutable content.")
