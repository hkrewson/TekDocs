# ADR 0021: Immutable block revisions and optimistic concurrency

- Status: Accepted for `0.2.3`
- Date: 2026-08-09

## Context

Stable blocks were introduced with mutable Markdown so the first persistence slice could prove workspace ownership and browser-to-PostgreSQL behavior. Reusable content cannot safely build on last-write-wins mutation: shared uses need stable historical targets, authors need accountable history, and concurrent editors must not silently destroy one another's changes.

## Decision

`Block` remains the stable addressable identity and holds one nullable `current_revision` pointer for migration and creation sequencing. Canonical Markdown moves to append-only `BlockRevision` rows containing a stable UUID, exact tenant/organization/block scope, parent revision, sequential revision number, server-calculated SHA-256 checksum, author, and creation time.

A document update must submit `base_revision_id`. The service locks the document and block in one transaction. When the base equals the current pointer and content changed, it appends one revision and advances the pointer atomically. Unchanged content retains the existing revision. When the base is stale, the service makes no change and returns `409 revision_conflict`, current revision metadata/content, and a unified diff between the submitted base and current content. The browser retains its draft and disables repeated save until the author explicitly acknowledges the current revision after reconciling its changes into the retained draft.

History endpoints resolve revisions only through an already authorized document route. Client projections of MSP documents may read the same history but do not gain source mutation authority. Sibling organization and foreign revision identifiers return the same unavailable result as other scoped resources.

Django model methods reject update/delete, and PostgreSQL triggers reject raw mutation while validating revision sequence, parent, block scope, and current-pointer ownership. Forced RLS applies to revision rows under the existing transaction-local runtime scope. PostgreSQL remains the live revision system; Git remains a later sanitized export boundary.

## Consequences

- Existing block Markdown is transformed into revision 1 while retaining document, block, placement, and entity identities.
- History grows append-only; pagination and large-history performance remain owned by `0.2.9`.
- SHA-256 is an integrity/change identifier, not a signature or proof of authorship.
- Live/pinned placement semantics and transclusion remain `0.2.4`; this ADR supplies their immutable target primitive.
- Conflict responses intentionally include only content already visible through the requested document route.
