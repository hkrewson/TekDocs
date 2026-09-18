# License collection and record workspace

Issue #81; completed Licenses and the connected operational-record milestone. Version remains 0.8.46.

## Implemented contract

Licenses now uses a bounded, searchable, filterable, sortable, paginated directory. Search covers license, supplier, product, and reference values; kind and status filters narrow the collection; name and renewal date have deterministic ordering. Search, filters, ordering, page, and selected license are URL-addressed. A direct license URL retrieves an authorized record outside the current page.

A license name opens one responsive record drawer with supplier and software identity, entitlement kind and status, seat usage, renewal terms, covered installations, active assignments, and retained event history. Authorized users can create or edit the license, assign a seat to an exact person or installation, link another installation, and revoke assignments without leaving the record. Failed writes retain their values. Escape, backdrop dismissal, mobile return navigation, and post-save transitions use the shared edit guard; a successful create waits for the cleared form to leave guarded state before opening the saved record.

The list endpoint rejects undeclared parameters, caps page size, returns canonical page metadata, and applies the existing workspace and software-license permissions. List and direct-detail routes share the same scoped serialization. OpenAPI and generated TypeScript types describe the bounded query, result, and detail contracts.

## Evidence

- Focused PostgreSQL inventory coverage passes for collection search, kind and status filtering, renewal sorting, paging, rejected parameters, and the existing license lifecycle rules.
- Nine focused component and API-client tests pass for creation, exact installation selection, renewal edits, seat assignment, direct off-page restoration, guarded dismissal, exact request paths, and query encoding.
- All 21 focused browser scenarios pass in Chromium, Firefox, and WebKit at 320, 390, 768, 1024, 1280, and 1440 pixels. They cover long values, collection and drawer bounds, record facts, history, editing, heading focus, accessibility, direct retrieval, URL retention, and keyboard dismissal.
- The frontend gate passes all 594 tests across 117 files, localization enforcement, coverage, typechecking, linting, the production build, and existing compressed bundle budgets.
- The isolated real browser-to-Django-to-PostgreSQL journey passes creation, seat assignment, renewal editing, reloads, downstream workflows, and independent database verification. It also closes the completed Product and License drawers explicitly before moving to another area.

This completes Phase 4. Documents is the next substantial layout milestone in Phase 5. Existing user and demo data was preserved; no version, deployment, or Wiki publication change is part of this checkpoint.
