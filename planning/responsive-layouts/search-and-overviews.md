# Search and focused overviews

This Phase 7 checkpoint replaces the remaining expansive Search and overview
patterns with bounded result navigation and short operational entry points. It
keeps version 0.8.46 and does not change record permissions or deployment state.

## Search

- MSP and organization Search use the same authorized, ranked server query.
  Query, result type, page and page size are URL-addressed; the default page is
  25 records and the interface offers 25, 50 or 100.
- Results remain compact links with identity, a short safe excerpt, workspace,
  update time and review state. Provider tickets retain external-link behavior.
- A result-type condition is visible outside the filter menu and can be removed
  directly. Search and page-size changes reset paging.
- Loading, minimum-query, empty and failure states are distinct. Retry repeats
  only the read while preserving the current query, filter, page and page size.
- The API accepts page sizes through 100 for the shared interface while retaining
  its legacy default of 15 and compatibility with smaller explicit sizes. Search
  still caps pages, query length and the total candidate budget.

## MSP overview

The MSP Overview no longer repeats every sidebar capability in a large status
table. It provides four short starting points for client organizations, Search,
Reminders and Activity. The sidebar remains the complete feature navigation.

## Organization overview

The organization profile remains visible and relationship management remains in
the workspace. Mapped HaloPSA tickets now render as a compact observation feed
that prioritizes ticket identity, status/priority, owner, freshness and its
provider link. The prior four-column table and isolated horizontal scrolling are
removed. A failed ticket read can be retried without hiding the organization
profile or changing workspace context.

## Compatibility and security

Search ranking, deterministic tie-breaking, permission filtering, safe excerpts,
provider mapping, organization scope and relationship writes are unchanged.
No domain model or database migration is introduced. OpenAPI and generated
browser types record the additive page-size ceiling.

## Verification

Coverage includes large-page API search, legacy explicit page sizes, query/type/
page/page-size restoration, retry after failed reads, provider deep links, long
organization and ticket values, and absence of the former overview/ticket tables.
The maintained browser matrix exercises 320, 390, 768, 1024, 1280 and 1440 CSS
pixels across Chromium, Firefox and WebKit, including accessibility and horizontal
overflow at 390 pixels. The live-stack journey verifies a real PostgreSQL-backed
record through Search and both overview routes.

This checkpoint does not complete Phase 7. Notifications, recycle bin, metadata,
account/access/setup/help/status and the client portal remain in the phase scope.
