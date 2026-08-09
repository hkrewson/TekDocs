# ADR 0023: Shared-block impact, detach, and entity mentions

- Status: Accepted for `0.2.5`
- Date: 2026-08-09

## Context

Live placement resolution makes one block visible in several documents and client listings. Editing through a containing document must not imply authority over the source block, and an editor needs to understand which authorized audiences will receive a new revision. Users without source authority still need a safe way to customize their containing document. Stable entity references also need a portable Markdown representation without trusting an authored label as authorization evidence.

## Decision

Backlinks and reuse impact are derived from the indexed `DocumentPlacement` graph and active `DocumentationListingReference` rows. No duplicate backlink table is introduced. Projections include only documents and client listing audiences the requester may view; hidden use counts are not returned. Live placements are marked as changing with the next shared revision, while pinned placements are explicitly unchanged.

A shared-block update begins from an authorized destination document and placement, but mutation authority is evaluated against the block's owning MSP or organization scope through `documents.edit`. It uses the immutable revision append service, requires the exact base revision, and retains the existing optimistic-concurrency response. Permission to edit a containing document never grants source mutation.

Detach requires `documents.edit` on the destination. It copies the placement's currently resolved immutable Markdown into a new destination-owned block and initial revision, then atomically repoints the existing placement in live mode. Placement identity, order, parent, and children remain stable. The primary placement cannot detach through this workflow. PostgreSQL's existing placement scope trigger validates the replacement edge.

Entity mentions are canonical Markdown links in the exact form `tekdocs://entity/{uuid}`. Workspace-scoped search supplies the UUID and display label for authoring. During preview, the server parses those targets, resolves only entities visible in the selected authorized workspace, replaces authored labels with server-owned reference-card text, and emits one generic unavailable card for missing or unauthorized targets. Client sanitization remains defense in depth.

## Consequences

- Backlinks always reflect current placement and listing state without synchronization jobs.
- Impact responses intentionally omit any indication that hidden clients or documents exist.
- Detached content stops receiving source revisions but retains immutable provenance through its creation audit and initial checksum.
- Mention source remains portable Markdown; rendered identity is contextual and permission-aware.
- Reordering, block-level ownership transfer, and mention backlinks across all historical revisions remain outside this slice.
