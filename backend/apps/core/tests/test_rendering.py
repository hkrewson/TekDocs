from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import InstallationState
from apps.core.rendering import render_markdown, render_pdf


class RenderedHTMLProbe(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attributes: list[tuple[str, str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attributes.extend((tag, name, value) for name, value in attrs)


def test_markdown_renderer_disables_raw_html_and_unsafe_urls() -> None:
    rendered = render_markdown("# Safe\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))")

    assert "<h1>Safe</h1>" in rendered
    assert "<script>" not in rendered
    assert 'href="javascript:' not in rendered


def test_markdown_renderer_resolves_entity_links_from_server_projections() -> None:
    rendered = render_markdown("[Router](tekdocs://entity/00000000-0000-4000-8000-000000000001)")
    assert 'class="entity-reference entity-reference-unavailable"' in rendered
    assert "Unavailable reference" in rendered
    assert "Router" not in rendered

    rendered = render_markdown(
        "[Authored name](tekdocs://entity/00000000-0000-4000-8000-000000000001)",
        entity_mentions={
            "00000000-0000-4000-8000-000000000001": {
                "id": "00000000-0000-4000-8000-000000000001",
                "display_name": "Core Router",
                "entity_type": "hardware_asset",
                "workspace_label": "Acme",
            }
        },
    )
    assert "Core Router · hardware asset · Acme" in rendered
    assert "Authored name" not in rendered
    assert 'href="tekdocs:' not in rendered


def test_markdown_renderer_resolves_attachment_links_from_server_projections() -> None:
    target = "00000000-0000-4000-8000-000000000002"
    unavailable = render_markdown(f"[misleading](tekdocs://attachment/{target})")
    assert "Unavailable attachment" in unavailable
    assert "misleading" not in unavailable
    assert 'href="tekdocs:' not in unavailable

    rendered = render_markdown(
        f"[wrong name](tekdocs://attachment/{target})",
        attachments={
            target: {
                "id": target,
                "filename": "network-map.pdf",
                "size": 42,
                "download_url": "/api/v1/documents/document/attachments/attachment/download",
            }
        },
    )
    assert "network-map.pdf · 42 bytes" in rendered
    assert "wrong name" not in rendered
    assert 'class="attachment-reference"' in rendered
    assert 'href="/api/v1/documents/document/attachments/attachment/download"' in rendered


def test_markdown_renderer_supports_the_tekdocs_dialect() -> None:
    rendered = render_markdown(
        "~~retired~~ and ==verify this==\n\n"
        "> [!WARNING]\n> Rebooting disconnects the site.\n\n"
        "- [x] Export configuration\n- [ ] Confirm rollback owner\n\n"
        "| Port | Purpose |\n| :--- | ---: |\n| 1 | WAN |\n\n"
        "A footnote.[^1]\n\n[^1]: Retained context.\n"
    )

    assert "<s>retired</s>" in rendered
    assert "<mark>verify this</mark>" in rendered
    assert 'class="callout callout-warning"' in rendered
    assert 'data-callout="warning"' in rendered
    assert '<strong class="callout-title">Warning</strong>' in rendered
    assert "[!WARNING]" not in rendered
    assert rendered.count('type="checkbox"') == 2
    assert 'checked=""' in rendered
    assert 'class="align-left"' in rendered
    assert 'class="align-right"' in rendered
    assert "footnote" in rendered


@pytest.mark.parametrize(
    "payload",
    (
        '<script>alert("stored")</script>',
        '<img src=x onerror="alert(1)">',
        '<svg><a xlink:href="javascript:alert(1)">unsafe</a></svg>',
        "[unsafe](javascript:alert(1))",
        "[unsafe](data:text/html;base64,PHNjcmlwdD4=)",
        "<style>body { display: none }</style>",
        '<iframe srcdoc="<script>alert(1)</script>"></iframe>',
        '<div style="position:fixed;inset:0">spoof</div>',
        "export const run = () => alert(1)\n\n<Component />",
    ),
)
def test_markdown_renderer_malicious_corpus_cannot_emit_executable_or_authored_html(payload: str) -> None:
    rendered = render_markdown(payload)
    probe = RenderedHTMLProbe()
    probe.feed(rendered)

    assert not {"script", "style", "iframe", "svg", "img", "div"}.intersection(probe.tags)
    assert all(name != "style" and not name.startswith("on") for _tag, name, _value in probe.attributes)
    assert all(
        urlsplit(value or "").scheme in {"", "http", "https", "mailto", "tekdocs"}
        for _tag, name, value in probe.attributes
        if name in {"href", "src"}
    )


def test_pdf_renderer_produces_a_pdf_document() -> None:
    rendered = render_pdf("# Static publication\n\nImmutable content.")

    assert rendered.startswith(b"%PDF-")
    assert len(rendered) > 1_000
    assert rendered == render_pdf("# Static publication\n\nImmutable content.")


@pytest.mark.django_db
def test_authenticated_document_reader_can_request_a_sanitized_preview(client) -> None:  # type: ignore[no-untyped-def]
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    installation = bootstrap_owner(
        tenant_name="Preview MSP",
        owner_email="preview-owner@example.invalid",
        owner_display_name="Preview Owner",
        password="Preview-password-42!",
    )
    client.force_login(installation.owner)

    response = client.post(
        reverse("markdown-render"),
        {"markdown": "# Preview\n\n==Check== <script>alert(1)</script>"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {
        "html": "<h1>Preview</h1>\n<p><mark>Check</mark> &lt;script&gt;alert(1)&lt;/script&gt;</p>\n"
    }


@pytest.mark.django_db
def test_markdown_preview_rejects_anonymous_and_oversized_requests(client) -> None:  # type: ignore[no-untyped-def]
    anonymous_response = client.post(reverse("markdown-render"), {"markdown": "safe"}, content_type="application/json")
    assert anonymous_response.status_code == 403

    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    installation = bootstrap_owner(
        tenant_name="Bounded Preview MSP",
        owner_email="bounded-preview-owner@example.invalid",
        owner_display_name="Bounded Preview Owner",
        password="Preview-password-42!",
    )
    client.force_login(installation.owner)
    response = client.post(
        reverse("markdown-render"),
        {"markdown": "x" * 1_000_001},
        content_type="application/json",
    )
    assert response.status_code == 400
