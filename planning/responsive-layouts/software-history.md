# Software asset audit history — pre-1.0, 0.8.46

Scope: #79/#86 under #77. Replace the software History placeholder with a bounded view of real recorded audit events. This is an Assets completion slice, not closure of Assets, Phase 1/2, or release acceptance.

## Presentation and recorded-data boundary

History reads only when the software record's History section mounts. It displays action, actor (or System), and occurrence time, newest first. Creation from catalog and installation updates have translated labels; other recorded actions retain a readable version of their stored action identifier. Nothing is inferred from current installation values.

The software update service retains an `asset.software.updated` event with empty metadata; asset creation records `asset.created_from_catalog`. Neither provides historical installation-field snapshots for a before/after comparison. The view explains that limitation and never invents a lifecycle chronology or exposes arbitrary audit metadata. Hardware continues using its existing domain lifecycle history.

The list uses 25 events per request and ordinary page scrolling. Completed Next/Previous reads focus the History heading and bring it into view, giving keyboard users a visible starting point in the new page. Next/Previous controls preserve `record`, `section`, active collection conditions, and transient list-return navigation state. `history_page` is URL-addressed so refresh and Back/Forward retain the selected history page. Switching sections of the same record retains it; leaving the record or opening another record clears it. Invalid nonpositive/noninteger history page values fall back to page 1.

Pending reads hide the previous page. Unmounts, page changes, and record/workspace changes cancel requests; late responses cannot replace the current record/page. Denied reads have a permission explanation. Other failures show a retry; neither failure is presented as empty history. Reads retry only after the explicit action. An empty successful result has its own explanation.

## Additive API change and permissions

Existing activity GET endpoints accept optional `entity_id` (UUID). It is applied after the current tenant/workspace boundary, before counting, pagination and action summaries. A record outside that boundary returns no events, counts, or action names. Invalid identifiers, including an explicitly blank value, are rejected. A direct query-serializer rehearsal reproduced DRF dropping a blank optional UUID as though it were an omitted HTML form field. The new filter preserves explicitly supplied values for UUID validation; only actual omission retains workspace-wide activity. No `entity_id` retains the existing workspace-wide behavior and default page size of 50.

The browser operations client accepts optional `entity_id` and `page_size`; existing callers retain their defaults. OpenAPI now explicitly documents the supported activity query parameters and generated types are aligned. No route, operation ID, model, migration, ownership/RLS classification or recovery format changes.

Activity remains protected by `activity.view`; `assets.view` does not grant audit access. The software record remains viewable when its History read is denied. The backend remains authoritative on every read. Actor identity and event fields use the existing activity response; metadata is not returned. There are no mutations in this slice.

## Durable verification

- `test_document_operations.py`: bounded exact-record results, stable repeat reads, second page, preserved legacy response, metadata exclusion, malformed identifier rejection and constrained runtime-role reads. Exact-workspace and foreign-tenant filter assertions and read-only-member denial remain covered.
- `SoftwareHistory.test.tsx`: selected-record query, bounded page size, preserved URL/list state, canceled page reads, stale-response rejection, explicit denied/failed retry and empty-state distinction.
- `operations/api.test.ts`: exact route/query encoding, explicit page size, abort forwarding and legacy defaults.
- `asset-layout.spec.ts`: all six maintained widths across three browser engines, deferred history reads, 31 synthetic events, long actors, accessibility scan, paging, refresh, Back and no horizontal page overflow.
- `live-workspace.spec.ts`: real software installation update followed by History, actual creation/update events and refresh; the wider journey and independent PostgreSQL fixture assertions remain intact.

Final gate results are recorded in progress.md. Synthetic fixtures remain isolated; existing user/demo data is preserved.

## Remaining scope

Contracts/Networks reuse and layout migration, expanded permission-transition/stale/conflict route coverage, technician/native zoom/screen-reader/mobile-keyboard walkthroughs and production/recovery/release gates remain open. Audit history is not a field-level versioning feature. No deployment, push, version change or Wiki publication is included.
