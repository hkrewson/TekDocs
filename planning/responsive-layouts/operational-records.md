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

Focused People component/client coverage passes 13 scenarios. The full frontend gate passes 116 files and 584 tests, lint, typechecking, OpenAPI drift, the production build, and unchanged bundle budgets. This is implementation evidence for the first piece, not milestone acceptance. Responsive browser and live-stack evidence will run at the grouped Organizations/People/Sites boundary as defined above. Sites and Organizations remain open; no Phase 4 route is accepted yet.
