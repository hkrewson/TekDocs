# Operational records milestone

Issue #81; Phase 4 of the pre-1.0 responsive layout work. Version remains 0.8.46.

## Delivery boundary

Organizations, People, and Sites form the first operational-records milestone. The milestone replaces their competing modal/card/table interactions with the accepted collection and full record drawer pattern. Work is reviewed as complete user journeys rather than isolated button or spacing changes.

The first implementation piece is People because its collection API is already bounded, searchable, filterable, sortable, and paginated. A person name opens the complete record in the shared responsive drawer; creation and editing stay in that workspace; direct links restore the selected record; missing or denied records have explicit states; dirty edits protect dismissal; archive retains confirmation. The old page-level edit overlay is removed.

Sites follows with a bounded collection and one site drawer containing its location hierarchy and management actions. Organizations then adopts the same administration workspace while retaining its existing link into the client workspace. Completion requires the three areas to share responsive behavior, URL state, loading/empty/error states, keyboard focus, mobile return navigation, and permission-preserving mutations.

## Acceptance

- Focused component/client coverage during implementation.
- Responsive browser coverage for the grouped milestone at 320, 390, 768, 1024, 1280, and 1440 pixels, including keyboard dismissal, dirty edits, Back/Forward, long values, and accessibility scans.
- One full project gate and one real browser-to-Django-to-PostgreSQL journey after Organizations, People, and Sites are integrated.
- Existing user/demo data remains untouched. No version, deployment, or Wiki publication change is part of this milestone.

## Current state

Accepted on 2026-09-17. People uses the shared responsive record drawer: the identity opens a complete overview, creation and editing remain in the drawer, URL state restores off-page records through the existing scoped detail endpoint, failed writes retain entries, dirty dismissal is guarded, and archive confirmation remains explicit. The old page-level person editor is removed.

Sites now uses the same collection and record workspace. The server collection is bounded, searchable, sortable, and paginated; unknown query parameters are rejected. Site names open a complete overview with address and contact details, the nested location hierarchy, site and location custom fields, and guarded create, edit, and archive actions. Search, sort, page, and selected-site state survive refresh through the URL, including direct links to records outside the current page. Archiving a parent location removes its complete branch from the open workspace, matching the server cascade.

Organizations now follows the same contract. Its bounded server collection supports search, classification filtering, deterministic ordering, pagination, and direct detail retrieval. Names open a complete administration drawer with classification, legal, contact, website, access, custom-field, create, edit, archive, and client-workspace actions. Query and selected-record state survive refresh and browser history; failed and dirty edits retain their values.

The grouped browser suite passes all 21 Organizations/People/Sites scenarios across Chromium, Firefox, and WebKit at 320, 390, 768, 1024, 1280, and 1440 pixels. It covers long values, page bounds, accessibility, browser history, keyboard dismissal, and dirty-change protection. The project checks pass backend lint and typing, migration and OpenAPI agreement, all 587 frontend tests across 116 files, coverage, the production build, and unchanged compressed bundle budgets. The full real browser-to-Django-to-PostgreSQL journey passes with persisted organization, person, site, location, and custom-field assertions. Existing user/demo data remains untouched. The next substantial Phase 4 milestone groups vendor catalog, products, licenses, and stock workflows.

Stock is the first completed piece of that next milestone. Its server collection is bounded, searchable, sortable, and paginated, while direct scoped retrieval restores off-page records. Item names open a complete drawer with purchasing provenance, exact pricing, current quantity, movement history, and guarded create, edit, adjustment, and archive actions. The focused responsive matrix passes all six widths in all three maintained engines. See [stock-workspace.md](stock-workspace.md). Vendor catalog, products, and licenses remain before grouped live-stack acceptance.
