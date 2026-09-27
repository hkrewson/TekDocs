# Pre-1.0 core-code decomposition

Issue #40. Application version remains 0.8.46. This record owns the bounded
decomposition sequence and the evidence needed to prove that moving code does not
change public behavior.

## Dependency direction

- `Documentation.tsx` remains the route-level coordinator. It owns URL state,
  request lifecycles, dirty-form policy, selected records and mutations.
- Focused panels receive typed data and explicit callbacks. They do not fetch,
  navigate, change URL parameters or create a second copy of document state.
- Domain/API modules remain below the coordinator. Extracted panels may import
  shared API types and localization, but not the browser client singleton.
- CSS and accessible names remain shared until a panel has a distinct visual
  contract. Decomposition alone does not create new containers or styles.

## Frontend checkpoint: history and section conversion

`DocumentHistoryPanel` now owns the revision list, retained-revision inspection,
loading/error treatment and paging controls. `DocumentRestructurePanel` owns the
review of blockers, warnings and proposed legacy-section boundaries. The
Documentation coordinator still performs every read and mutation and supplies
the current result through typed props.

This seam was selected because both panels already have explicit open/close
boundaries and no independent server state. Their extraction reduces the route
component without inventing a parallel state authority, changing markup, or
weakening the shared unsaved-change guard.

## Remaining sequence

1. Extract the key-binding and reusable-content panels behind the same explicit
   data/callback boundary.
2. Move document collection URL/filter state into a focused hook while keeping
   URL names and browser history behavior unchanged.
3. Move record-loading and stale-request cancellation into a document-domain
   hook with coordinator-owned selection.
4. Split backend document serializers/views by the existing authoring, reuse,
   templates, review, publication, attachment, key, source and export domains.
5. Split Django models only after import/dependency mapping is recorded; retain
   the `core` app label, table names and compatibility imports with zero schema
   drift.

Each slice must pass type/lint/component behavior checks. URL, browser, OpenAPI,
migration, production-image and recovery gates recur when the affected boundary
requires them. The full release gate remains a final clean-candidate action rather
than a per-extraction development loop.
