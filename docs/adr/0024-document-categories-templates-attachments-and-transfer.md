# ADR 0024: Document categories, templates, attachments, and Markdown transfer

- Status: Accepted for `0.2.6`
- Date: 2026-08-09

## Context

Reusable blocks now support composition and safe shared editing, but authors still need recognizable document types, repeatable starting points, private supporting files, and a portable way to move Markdown into or out of TekDocs. File handling is a new hostile-input boundary and cannot rely on a public media URL, an authored filename, or a browser-provided content type.

## Decision

Documents receive one deliberately portable built-in category: `general`, `policy`, `procedure`, `guide`, or `reference`. A separate `is_template` flag identifies reusable sources without conflating document meaning with lifecycle. Index filtering is applied after the existing exact-workspace/reference visibility query.

Template instantiation is a copy operation, not transclusion. The caller must view the source template and edit the destination workspace. TekDocs resolves the template composition, creates a new destination-owned document with its own primary block and revision, copies source-document attachments under new UUIDs and randomized storage names, and rewrites their stable Markdown targets. A managed attachment target outside the source document fails closed so the copy cannot silently retain a hidden or brittle dependency.

`DocumentAttachment` records have stable UUIDs plus tenant, workspace, and owning-document scope. Stored object names contain generated identifiers rather than original filenames. TekDocs accepts a bounded allowlist of inert technical-documentation formats, derives the effective media type from bytes and filename rules, records size and SHA-256, and never extracts archives or renders attachment bytes in authenticated pages. Downloads resolve through the owning document's normal `documents.view` boundary and use `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, and private cache controls. Removal is soft; retained bytes support future publication and recovery work.

Authored attachment references use only `tekdocs://attachment/{uuid}`. Secure preview requires the selected document context, discards the authored label, and emits either an authorized server-owned attachment card or one generic unavailable state. No direct storage URL enters canonical Markdown.

Markdown import accepts one UTF-8 `.md` file under 1 MiB plus explicit title/category/template metadata, then creates the document through the normal initial immutable revision path. Export emits the document's deterministic resolved Markdown as a forced-download `.md` response. It does not bundle attachment bytes, editor HTML, secrets, or authorization metadata.

## Consequences

- The fixed category set is intentionally modest; custom taxonomies and multi-category tagging require a later product decision rather than an unbounded metadata table in this slice.
- Template instances are safe to customize and do not receive later source changes.
- Attachment bytes remain private application data even when local filesystem storage is selected. S3-compatible storage can implement the same provider boundary later without changing Markdown.
- Exported Markdown preserves stable TekDocs attachment references but does not pretend those references are portable files. A future archive export may package authorized attachments under an explicit manifest.
- Virus scanning is deployment-specific future defense in depth. This slice minimizes exposure with tight limits, byte validation, no extraction, no inline serving, and a malicious upload corpus.
