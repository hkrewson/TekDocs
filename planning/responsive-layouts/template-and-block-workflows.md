# Template and reusable-content workflows

Phase 5 under #60 and the responsive-layout plan, version 0.8.46.

## Implemented

- Client Documentation separates Documents from Templates from your MSP. Library search and 25-item pages run against the complete authorized shared MSP template set. Library/query/page state can be restored from the URL.
- Choosing a template opens a focused draft with a title, per-section content previews and copy/live/pinned choices. The shared navigation guard protects the draft; denied or uncertain writes retain choices and never retry automatically.
- Reusable blocks load only when insertion is opened. Search and 20-item pages cover the complete authorized library; destination-owned blocks are excluded before counting/paging. Loading, empty, error, read retry and content-preview states are explicit.
- Template update review identifies added, changed and removed sections, displays server conflict explanations and prevents conflicted application. New sections have explicit copy/live/pinned choices. Successful application reloads the selected document; failures retain review choices. Changed choices participate in navigation protection.
- Restricted-role template application locks only the client enrollment row. It does not try to lock the readable shared MSP source or immutable revision; copy/live/pinned runtime tests cover the fix and stale enrollment rejection.
- Reuse review explicitly warns when the server's audience report is truncated.
- Library query parameters are strictly validated, limits are capped, ordering includes stable identity ties, and overshot pages clamp to the last page. Existing workspace authorization and mutation rules remain authoritative. No model or migration changes.
- The document API client now loads with the documentation/files/integrations routes, keeping the eager shell within its existing JavaScript budget. New styling stays in the Documentation route.

## Verification

Verified: `make check` passes with 601 frontend tests in 117 files, lint/types,
API/schema agreement, migration drift checks, the production build and unchanged
bundle budgets. All 18 six-width Chromium/Firefox/WebKit library cases pass,
including accessibility, overflow, draft protection and error recovery. The complete
Docker `make test-documentation-validation` gate passes with one existing skip.
`make test-e2e-live` passes the real browser/Django/PostgreSQL journey and independent
database assertions for template creation, live/pinned insertion, update application,
reload retention and audit history. The rebuilt local instance is ready at
localhost:3200, version 0.8.46. Wiki validation passes for all 37 pages.

No validation gates are blocked. Broader technician acceptance is unverified;
automated coverage does not imply completion of the remaining Phase 5 scope.
Detailed reproduction and final evidence paths are recorded in progress.md.

## Remaining scope

Broader Phase 5 ownership/reviews, publication/export and managed-file work remain open, as do technician acceptance, full document-wide draft protection and the existing document-link picker (which still uses the loaded document page). The server's existing rollout concurrency contract remains unchanged: application rechecks conflicts and the enrollment revision, but does not freeze the source template revision to the preview. This checkpoint does not claim Phase 5 or pre-1.0 acceptance.
