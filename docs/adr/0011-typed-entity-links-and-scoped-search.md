# ADR 0011: Typed entity links and scoped search

- Status: Accepted
- Date: 2026-08-08

## Decision

Use `EntityLink` as the stable relationship record between two Entity identities. Link types come from a maintained application catalog with explicit forward and inverse labels, symmetric behavior, allowed target Entity types, and any required organization classification. Callers may choose only a catalog value and target UUID; they cannot submit tenant ownership, endpoints beyond the selected source, or relationship metadata.

Directional links retain source and target meaning. The same record renders its forward label from the source and its inverse label as a backlink from the target. Symmetric `related_to` and `partnered_with` links use canonical UUID endpoint order so reverse duplicates cannot exist. Self-links and duplicate active typed links are rejected. Archival is append-preserving: archived links disappear from ordinary relationship views and cannot be mutated or restored, while the same endpoints may later receive a new active link.

Relationship visibility is derived from the URL-selected workspace before endpoint resolution. MSP scope includes only MSP-owned Entities. An organization workspace includes its own anchor and organization-owned Entities; active MSP-owned organization anchors are additionally eligible as explicit relationship targets and backlinks. This exception exposes the organization directory identity, not sibling organization-owned child records. Both link endpoints must belong to the exact tenant.

Entity search uses the same workspace visibility service as link reads and writes. It is bounded by approved Entity types, query length, page size, and page number. Results disclose only stable ID, display name, Entity type, a non-sensitive workspace label, and link-type eligibility. Eligibility is presentation guidance; creation revalidates the target under locks and is never authorized by a browser-supplied projection.

PostgreSQL enforces same-tenant endpoints, empty metadata, canonical symmetric ordering, immutable link identity, and immutable archived state. The application service provides operator-facing validation, serializable projections, value-free audit events, and policy checks. Until the central permission catalog lands, mutations remain installation-owner-plus-MFA operations.

## Consequences

- All current and future domains can share one auditable relationship and backlink contract without generic foreign keys or per-domain join conventions.
- Permission-aware search and relationship traversal cannot be broader than the active workspace even when a caller knows another Entity UUID.
- Future domains may extend the catalog through reviewed definitions and tests; they may not accept arbitrary relationship strings or unstructured metadata.
- Per-link notes, ordering, temporal validity, collection-scoped permissions, and relationship-specific custom fields require explicit later models rather than overloading `metadata`.
