# Git-native monitored-source configuration

Bounded clean-start 1.0 configuration slice following native template enrollment
at `191f7c2e`. Version remains 0.9.18 development. This slice does not migrate
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

## Current evidence

- **Verified:** fresh-database focused native configuration/apply/local-edit and
  publication-blocker tests; existing monitored-source migration and remote-egress
  cohorts; route permission inventory; frontend repository panel tests; frontend
  type checking; focused Ruff and mypy; generated OpenAPI with zero errors.
- **Inferred pending broader gates:** full backend/frontend coverage, live browser
  check against the bounded test HTTP source, supported upgrade, rollback refusal,
  independent encrypted recovery and production-image validation.
- **Blocked locally:** the retained development Valkey AOF is corrupt, so the full
  normal Compose project cannot become healthy until the cache/queue AOF is repaired
  or replaced with operator approval. Backend tests were run in the existing
  backend/database services without creating another Compose project or volume.

Exact-source hosted Build, CodeQL and Extended evidence, source review and the
combined clean-start journey remain required before this slice or aggregate 1.0
acceptance is closed.
