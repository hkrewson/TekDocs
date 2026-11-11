# Git-native monitored-source configuration

Bounded clean-start 1.0 configuration slice following native template enrollment
at `191f7c2e`. Version remains 0.9.19 development. This slice does not migrate
legacy settings, inspect production, deploy, publish, or change existing documents.

## Acceptance

- A newly authored Git-only document can save a public HTTPS monitored source
  without creating a legacy `Document` row.
- Settings and immutable observations remain SQL workflow state. Scheduled/manual
  checks keep the existing pinned-address, redirect, timeout, type and size controls.
- Review binds the exact settings, observation, accepted Git commit and source
  blob. Apply uses the coordinated authoring writer and updates the applied pointer
  only after the indexed Git result is verified.
- A missing baseline or local edit blocks replacement. Stale review, foreign
  Workspace, denied edit, unavailable index and owner-shape changes fail without
  partial Git or SQL updates.
- A changed unapplied observation blocks new repository publication evidence.
  Existing signed publications, PDFs, files and legacy monitored sources are not
  rewritten.
- Migration 0223 retains either one legacy document owner or one exact
  repository/content owner, guards immutable ownership in PostgreSQL and refuses
  rollback while native monitored settings exist.

## Reproduction and implementation

The maintained Docker regression first returned HTTP 404 for a Git-only document
at `/content-graph/authoring/<content-id>/remote-source`. The existing route and
model required a legacy `Document`. The correction extends the retained source
record with an exclusive native owner, adds permission-inventoried repository
routes, reuses observation fetching/review and applies directly to the native
document through managed authoring. The repository editor reuses the protected
Web source panel and keeps unfinished settings inside the navigation guard.

## Candidate acceptance evidence

- **Locally verified:** the production frontend build (including TypeScript and
  bundle policy), focused Ruff, Django checks, shell syntax, and both independent
  source-review axes. The review correction binds every source setting directly,
  treats older applied changes as history rather than permanent publication
  blockers, and protects every unfinished setting in the navigation guard.
- **Candidate harness prepared:** the combined clean-start browser journey now
  authors a Git-only document, configures its Web source through the visible UI,
  reloads the retained settings, and verifies server-side that no legacy Document
  exists. Migration-executor tests prove empty-schema upgrade and populated-schema
  rollback refusal. The supported-upgrade rehearsal exercises the native fixture
  on both upgraded and fresh schemas, and independent encrypted recovery compares
  the exact SQL observation/settings state with the managed Git commit and blob.
- **Hosted confirmation required:** exact-source Build must pass the live browser,
  database shards, production-container and final validation jobs; Extended must
  pass supported upgrade and independent recovery; CodeQL must complete. The
  retained development database role cannot create the isolated test database,
  so the focused database cases are intentionally left to those hosted gates.

No production deployment or existing-data transition is part of this acceptance
slice.
