# ADR 0002: Canonical content and revisions

- Status: Accepted
- Date: 2026-08-07

## Decision

Store canonical block content as Markdown. Editor HTML/JSON is transient. Store immutable block revisions in PostgreSQL and compose documents through live or pinned placements. Git is an export destination, not the transactional revision store.

Raw HTML and executable MDX are outside the supported dialect. STATIC publication resolves dependencies into immutable Markdown, sanitized HTML, a signed manifest, and PDF.
