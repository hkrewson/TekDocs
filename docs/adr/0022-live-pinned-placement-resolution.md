# ADR 0022: Live and pinned structured placement resolution

- Status: Accepted for `0.2.4`
- Date: 2026-08-09

## Context

Immutable block revisions provide stable content targets, but a reusable document needs an explicit composition contract. Encoding transclusion markers inside Markdown would make a TekDocs-specific token part of the authoring dialect, complicate visual-editor round trips, and require permission decisions while parsing text. Flat block lists also leave no meaningful structural boundary for nested reuse or circular-reference detection.

## Decision

`DocumentPlacement` is the structural composition record. Each placement belongs to the destination document and selects one stable `Block`. It resolves in one of two modes:

- `live` resolves `Block.current_revision` at read time and cannot carry a pinned revision;
- `pinned` resolves one exact immutable `BlockRevision`, which must belong to the placed block.

Placements form an optional parent-child tree inside one document. Siblings receive stable integer positions and resolve by `(position, UUID)`. Rendering walks roots and descendants depth first, preserves each selected revision's Markdown, normalizes only boundary newlines, and emits a final newline for non-empty compositions. Resolution is bounded to 500 placements and 32 levels. The API returns the primary editable Markdown separately from assembled Markdown and an ordered resolution manifest.

Creating a transclusion selects the primary block of a document already visible through the destination workspace. Same-workspace documents may be reused directly. An MSP-owned block may enter a client document only while its source document has an active listing reference in that client. Sibling-client and foreign-tenant sources remain non-disclosing. A listing reference cannot be archived or deleted while client placements depend on its primary block.

Application validation rejects self-transclusion, a target block repeated in its ancestor chain, an invalid pinned revision, a foreign parent, and removal of a placement that still has children. PostgreSQL independently enforces workspace/source eligibility, parent scope, pinned-target integrity, self-parenting, and recursive ancestor-cycle rejection. The primary position-zero block remains live and cannot be removed or pinned.

## Consequences

- Canonical authored content remains Markdown; composition metadata does not become an editor extension.
- Editing a source block updates every live placement while pinned placements remain stable.
- Structured nesting supplies a deterministic future boundary for backlinks, reuse impact, and detach behavior in `0.2.5`.
- Reordering and graphical tree editing are not part of this slice. New placements append deterministically to their selected sibling list.
- STATIC publication will later resolve this same manifest to exact revisions before signing.
