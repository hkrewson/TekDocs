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

## Frontend checkpoint: focused document panels

`DocumentHistoryPanel` now owns the revision list, retained-revision inspection,
loading/error treatment and paging controls. `DocumentRestructurePanel` owns the
review of blockers, warnings and proposed legacy-section boundaries.
`DocumentKeysPanel` owns binding declaration, field insertion, unresolved-key
reporting and workspace binding results. The Documentation coordinator still
performs every read and mutation and supplies the current result through typed
props.

`DocumentReusePanel` now owns the reusable-block, document-link and record-link
insertion presentation. Placement mode, audience selection, record search state
and every insertion mutation remain coordinator-owned. The existing block and
document pickers retain their bounded collection requests and error states.

`DocumentRemoteSourcePanel` owns the monitored-source form and observation
timeline. The coordinator continues to load sources, persist settings, run checks,
apply reviewed observations and enforce the shared unsaved-change guard.

`useDocumentCollectionState` now owns initialization, validation and compatible
URL persistence for document search, filters, ordering, page and library mode.
It preserves unrelated record, tab and publication parameters while the route
coordinator continues to decide when collection changes are allowed.

`useDocumentCollection` now owns bounded collection reads, direct off-page record
retrieval and cancellation of stale requests. It reports a loaded record through
an explicit callback, leaving selected-record and editor state in the coordinator.
Explicit row and publication navigation can mark their known record identity so a
collection refresh does not refetch stale detail metadata.

## Backend checkpoint: publication serializers

Retained publication, control-event, verification and client-portal projection
serializers now live in `document_publication_serializers.py`. The established
`serializers` module re-exports their existing names so view modules, portal code,
tests and third-party imports keep the same contract. This extraction changes no
fields, validation, schema component names, routes or persistence.

Managed attachment writes, attachment reads, primary-file summaries, bounded
file-register queries, file rows and file-result projections now live in
`document_file_serializers.py`. The established `serializers` module likewise
re-exports their existing names. Document serialization keeps its model imports
for relationship assembly, while file validation and response fields are
unchanged.

Template instantiation plus rollout request/result serializers now live in
`document_template_serializers.py`. Document views import that focused contract
directly, while `serializers.py` retains explicit compatibility exports. Template
category, placement-mode, revision and response validation remain unchanged.

Review-request and approval/change-request serializers now live in
`document_review_serializers.py`. Document views import them directly and the
compatibility module preserves their established names. Reviewer identity,
decision choices and note validation remain unchanged.

Monitored-source configuration and observation serializers now live in
`document_source_serializers.py` instead of being declared inside the source view
module. The views retain request handling and expose the imported serializer names
for compatibility. URL safety validation, observation diffs and response fields
remain unchanged.

Document creation and update, file-backed creation, Markdown import, bounded
collection queries, topic conversion, preflight and legacy-section restructure
contracts now live in `document_authoring_serializers.py`. Document views import
that focused contract directly. The established `serializers` module re-exports
every prior name so internal and third-party imports retain the same class
identity. Validation, schema component names, routes, permissions and persistence
remain unchanged.

These seams follow existing interaction and request boundaries. The frontend
panels keep state authority in the route coordinator, while backend request
handlers import focused contracts and the compatibility module retains public
names. No extraction introduces competing state, changes markup, or weakens the
shared unsaved-change guard.

## Remaining sequence

1. Continue splitting backend document serializers/views by the existing reuse,
   key and export domains.
2. Split Django models only after import/dependency mapping is recorded; retain
   the `core` app label, table names and compatibility imports with zero schema
   drift.

Each slice must pass type/lint/component behavior checks. URL, browser, OpenAPI,
migration, production-image and recovery gates recur when the affected boundary
requires them. The full release gate remains a final clean-candidate action rather
than a per-extraction development loop.
