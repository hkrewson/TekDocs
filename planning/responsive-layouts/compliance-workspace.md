# Compliance and data-flow workspace

## Scope

Phase 6 separates the MSP and client Compliance routes into focused Frameworks,
Evidence, Risks, Review bundles and Data flows sections. The existing exact-workspace
authorization, immutable revisions, append-only decisions and provenance rules remain
authoritative.

## Acceptance

- Opening Compliance shows the framework catalog without placing every compliance
  workflow on the page at once.
- Each workflow has a stable section URL that survives reload and browser history;
  desktop links become one labeled selector below 768px.
- Framework collection failures have an in-place retry.
- Framework, control-review, evidence, risk and data-flow drafts block section and
  page navigation and support Keep editing or Discard changes.
- Evidence, risk and bundle data loads only when its section is opened. Existing
  exact-revision links, risk scoring, bundle verification and data-flow provenance
  remain intact.
- A member without the separate data-flow permission sees no data-flow content.
- Both MSP and organization routes fit 320, 390, 768, 1024, 1280 and 1440px in
  Chromium, Firefox and WebKit without horizontal page overflow or automated
  accessibility violations.

## Evidence

- Component workflows: `frontend/src/compliance/Compliance.test.tsx`
- Data-flow behavior: `frontend/src/compliance/DataFlows.test.tsx`
- Browser matrix: `frontend/e2e/compliance-layout.spec.ts`
- Provenance, keyboard and permission browser coverage: `frontend/e2e/data-flows.spec.ts`
- Real organization workspace journey: `frontend/e2e/live-workspace.spec.ts`

The focused browser run passes 30 cases across all three maintained engines. The
component suites pass 19 cases covering all five sections, navigation protection,
retry, retained failures, immutable history and permission refusal. The isolated
real-workspace browser journey passes against PostgreSQL, including the framework,
control-review and locked-bundle path. The repository-wide gate passes all 636
frontend tests in 117 files, the 37-page Wiki contract, API/schema and migration
agreement, policy checks, the production build and compressed bundle budgets
(shell 129176 <= 131072; shell style 24503 <= 24576).
