# Authentication and client portal workspace

This Phase 7 slice completes the signed-out setup/authentication shell and the client-facing portal at version 0.8.46. It changes presentation and navigation only; authentication policy, publication authorization, invoice authorization, and public API behavior remain unchanged.

## Result

Authentication keeps one focused panel for bootstrap, sign-in, invitation activation, MFA challenge, password recovery, completion, unavailable, loading, and failure states. The existing forms already collapse to a single edge-to-edge surface on small screens, retain accessible labels and errors, and avoid competing scroll regions. The browser acceptance matrix now includes 320, 390, 768, 1024, 1280, and 1440 CSS-pixel widths plus 200% zoom, while the dedicated invitation, MFA, and password-reset journeys continue to verify their operational states.

The client portal now opens on a focused Documents workspace. Documents and Invoices are separate URL-addressed sections, rendered as tabs on wider screens and a labeled Sections selector below 768px. Selecting a record writes `document` or `invoice` into the URL. Refresh and browser Back/Forward restore the reader or invoice detail. Notification targets use the same document URL state.

Only the active collection is requested. Lists remain bounded by their existing cursor APIs, and record details load only when selected. Loading, empty, denied, failed, unavailable-record, retained-publication, invoice-detail, notification, and sign-out states remain available without stacking both collections down one long page. Portal-specific CSS is loaded with the lazy portal bundle, reducing the root stylesheet while preserving the shared record navigation control.

## Compatibility and boundaries

- `/portal` remains valid and defaults to Documents.
- `?section=documents` and `?section=invoices` address the two collection workspaces.
- `?section=documents&document=<id>` and `?section=invoices&invoice=<id>` address record detail.
- Existing downloads, publication sanitization, review warnings, notifications, invoice billing snapshots, and sign-out behavior are unchanged.
- No backend, migration, OpenAPI, permission, or domain-data change is required.

## Evidence

- `frontend/src/portal/ClientPortal.test.tsx` covers focused collection loading, direct detail restoration, sanitization, pagination, empty/failure/unavailable states, invoice details, and downloads.
- `frontend/e2e/responsive.spec.ts` covers the required width set, 200% zoom, overflow, mobile Sections selection, direct record URLs, refresh, Back/Forward, and accessibility in the maintained mobile browser engines.
- `frontend/e2e/shell.spec.ts`, `invitation.spec.ts`, `mfa.spec.ts`, and `password-reset.spec.ts` retain cross-browser shell and authentication workflow coverage.
- The production frontend build enforces bundle budgets; the portal styles are emitted as a lazy asset.
- The local Docker frontend at `http://localhost:3200` is rebuilt for review.

Phase 7 still has one bounded implementation area: cross-cutting shell overlays and unavailable-workspace handling. Technician walkthrough and production-image/release acceptance remain Phase 8 work.
