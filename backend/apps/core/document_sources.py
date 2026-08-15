from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from html.parser import HTMLParser
from uuid import UUID

import urllib3
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from urllib3.exceptions import HTTPError

from .approved_egress import (
    ApprovedEgressError,
    normalize_public_https_url,
    pinned_https_pool,
    resolve_public_https_target,
)
from .documents import PlacementConflict, primary_placement, update_shared_block
from .models import AuditEvent, DocumentRemoteObservation, DocumentRemoteSource, DocumentSourceKind

MAX_REMOTE_DOCUMENT_BYTES = 2 * 1024 * 1024


class RemoteDocumentError(RuntimeError):
    """A value-free remote-source failure safe for retained evidence."""


class _MarkdownHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed = 0
        self.href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "template", "noscript"}:
            self.suppressed += 1
            return
        if self.suppressed:
            return
        if tag in {"p", "div", "section", "article", "br", "hr"}:
            self.parts.append("\n\n" if tag != "br" else "\n")
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append(f"\n\n{'#' * int(tag[1])} ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("*")
        elif tag == "code":
            self.parts.append("`")
        elif tag == "a":
            self.parts.append("[")
            self.href = dict(attrs).get("href")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "template", "noscript"}:
            self.suppressed = max(0, self.suppressed - 1)
            return
        if self.suppressed:
            return
        if tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("*")
        elif tag == "code":
            self.parts.append("`")
        elif tag == "a":
            self.parts.append(f"]({self.href})" if self.href and self.href.startswith(("https://", "http://")) else "]")
            self.href = None

    def handle_data(self, data: str) -> None:
        if not self.suppressed:
            self.parts.append(data)

    def markdown(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        output: list[str] = []
        for line in lines:
            if line or (output and output[-1]):
                output.append(line)
        return "\n".join(output).strip() + "\n"


def html_to_markdown(value: str) -> str:
    parser = _MarkdownHTMLParser()
    parser.feed(value)
    parser.close()
    return parser.markdown()


def validate_remote_source_url(value: str) -> str:
    return normalize_public_https_url(value, label="Document source", allow_query=True)


def _digest_header(value: str | None) -> str:
    return sha256(value.encode()).hexdigest() if value else ""


@transaction.atomic
def fetch_remote_document(source: DocumentRemoteSource) -> DocumentRemoteObservation:
    error_code = ""
    status_code: int | None = None
    content_type = ""
    markdown = ""
    etag_digest = ""
    modified_digest = ""
    try:
        target = resolve_public_https_target(source.url, label="Document source", allow_query=True)
        pool = pinned_https_pool(
            target, connect_timeout=3.0, read_timeout=12.0, pool_factory=urllib3.HTTPSConnectionPool
        )
        try:
            response = pool.urlopen(
                "GET",
                target.path,
                headers={"Host": target.hostname, "Accept": "text/markdown,text/plain,text/html;q=0.8"},
                redirect=False,
                assert_same_host=False,
                preload_content=False,
            )
            status_code = response.status
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            etag_digest = _digest_header(response.headers.get("ETag"))
            modified_digest = _digest_header(response.headers.get("Last-Modified"))
            if status_code != 200:
                response.close()
                raise RemoteDocumentError("remote_http_error")
            if content_type not in {"text/markdown", "text/plain", "text/html", "application/xhtml+xml"}:
                response.close()
                raise RemoteDocumentError("remote_content_type_invalid")
            body = response.read(MAX_REMOTE_DOCUMENT_BYTES + 1)
            response.close()
            if len(body) > MAX_REMOTE_DOCUMENT_BYTES:
                raise RemoteDocumentError("remote_response_too_large")
            text = body.decode("utf-8")
            kind = source.source_kind
            if kind == DocumentSourceKind.AUTO:
                kind = DocumentSourceKind.HTML if "html" in content_type else DocumentSourceKind.MARKDOWN
            markdown = html_to_markdown(text) if kind == DocumentSourceKind.HTML else text.rstrip() + "\n"
        finally:
            pool.close()
    except (ApprovedEgressError, HTTPError, UnicodeDecodeError, ValidationError, RemoteDocumentError) as exc:
        error_code = (
            str(exc) if isinstance(exc, ApprovedEgressError | RemoteDocumentError) else "remote_connection_failed"
        )
    digest = sha256(markdown.encode()).hexdigest() if markdown else ""
    previous = source.observations.exclude(state="failed").first()
    state = "failed" if error_code else ("unchanged" if previous and previous.content_digest == digest else "changed")
    observation = DocumentRemoteObservation.objects.create(
        tenant=source.tenant,
        organization=source.organization,
        source=source,
        state=state,
        status_code=status_code,
        content_type=content_type,
        etag_digest=etag_digest,
        last_modified_digest=modified_digest,
        content_digest=digest,
        canonical_markdown=markdown,
        error_code=error_code,
    )
    source.last_checked_at = timezone.now()
    source.next_check_at = source.last_checked_at + timedelta(minutes=source.check_interval_minutes)
    source.save(update_fields=("last_checked_at", "next_check_at", "updated_at"))
    return observation


@transaction.atomic
def apply_remote_observation(*, observation: DocumentRemoteObservation, actor_id: UUID) -> None:
    source = DocumentRemoteSource.objects.select_for_update().select_related("document").get(pk=observation.source_id)
    if observation.source_id != source.id or observation.state == "failed" or not observation.canonical_markdown:
        raise PlacementConflict("Only a successful retained source observation can be applied.")
    placement = primary_placement(source.document)
    if placement.block.current_revision_id is None:
        raise PlacementConflict("The document block does not have a current revision.")
    update_shared_block(
        placement=placement,
        actor_id=actor_id,
        markdown=observation.canonical_markdown,
        base_revision_id=placement.block.current_revision_id,
    )
    source.last_applied_observation = observation
    source.save(update_fields=("last_applied_observation", "updated_at"))
    AuditEvent.objects.create(
        tenant=source.tenant,
        actor_id=actor_id,
        action="document.remote_source_applied",
        entity_id=source.document.entity_id,
        metadata={"observation_id": str(observation.id)},
    )
