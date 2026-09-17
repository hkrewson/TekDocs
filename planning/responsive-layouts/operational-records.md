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

In progress. The grouped audit is complete. People now uses the shared responsive record drawer: the identity opens a complete overview, creation and editing remain in the drawer, URL state restores off-page records through the existing scoped detail endpoint, failed writes retain entries, dirty dismissal is guarded, and archive confirmation remains explicit. The old page-level person editor is removed.

Sites now uses the same collection and record workspace. The server collection is bounded, searchable, sortable, and paginated; unknown query parameters are rejected. Site names open a complete overview with address and contact details, the nested location hierarchy, site and location custom fields, and guarded create, edit, and archive actions. Search, sort, page, and selected-site state survive refresh through the URL, including direct links to records outside the current page. Archiving a parent location removes its complete branch from the open workspace, matching the server cascade.

Focused Sites component/client, PostgreSQL API, and collection query-budget coverage passes. The full project gate passes backend lint and typing, migration and OpenAPI agreement, 585 frontend tests across 116 files, coverage, the production build, and unchanged compressed bundle budgets. This is implementation evidence for the first two pieces, not milestone acceptance. Responsive browser and live-stack evidence will run at the grouped Organizations/People/Sites boundary as defined above. Organizations remains open; no Phase 4 route is accepted yet.
