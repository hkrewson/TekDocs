# Document health queue and link picker

Phase 5 under #60, version 0.8.46.

## Scope and acceptance

Finish the older content-health queue and document-link picker without changing document placement semantics. Acceptance requires server-backed filtering and paging across the complete authorized document collection, URL-restorable health mode, accurate counts and facets, exclusion of the open destination document, retryable search, keyboard-accessible controls, six-width browser/accessibility checks and the real browser/backend document journey.

## Implemented

- Content health requests the bounded server search with the `attention` health filter, which returns every non-current document before pagination. Counts, Next/Previous behavior and the empty state now describe the actual attention queue rather than a client-side subset of the loaded page.
- Health mode is retained in `doc_library=health`; entering or leaving it returns to page one. A selected concrete health state still uses the existing filter menu, and health facets remain available across the other active filters.
- The document search contract accepts `attention` and an optional destination exclusion. Both MSP and client-workspace search parameters are documented in OpenAPI and generated frontend types.
- **Existing content** now includes a dedicated document picker with debounced search, 20-item pages, retry and empty states. It searches the full authorized workspace, excludes the open document on the server and preserves live/pinned plus audience choices when inserting.
- The compact Content health action has an explicit accessible name when its visible label is hidden at narrow widths. Document-list tags use the readable muted text token after browser accessibility checks exposed insufficient contrast.
- No model, migration, permission, dependency or version change is required.

## Verification

Focused regressions reproduce the old page-local health filtering and page-local document select before the fix. Component coverage checks complete queue counts, document search, paging, destination exclusion and insertion. Backend coverage checks attention filtering, cross-filter health facets, bounded pagination, exclusion and unknown-parameter rejection.

The Docker browser matrix covers Chromium, Firefox and WebKit at 320, 390, 768, 1024, 1280 and 1440px, including retry, URL state, accessibility and page overflow. All 18 new cases and 54 publication, export, managed-file and draft-protection regressions pass. The complete project gate passes all 625 frontend tests in 117 files, the documentation validation gate passes with one existing skip and the real browser/Django/PostgreSQL workspace journey passes in 3.3 minutes.

## Remaining scope and limits

Health remains derived from the existing ownership, review and due-date contract; this checkpoint does not change review policy or add a persisted queue. Document links retain existing live/pinned resolution and audience behavior. Direct-link/history acceptance is recorded separately in [document-direct-links-and-history.md](document-direct-links-and-history.md); technician review remains open for Phase 5. No external publication or deployment is implied.
