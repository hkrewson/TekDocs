# Retained publication viewer and editable exports

Phase 5 under #60, version 0.8.46.

## Scope and acceptance

Separate reading, retained downloads and lifecycle history into focused publication sections. Make editable exports a focused document view with explicit file selection. Preserve existing immutable publication, export and authorization contracts. Acceptance includes retryable reads, late-response cancellation, lifecycle decision draft retention, keyboard focus, long filenames, six-width browser checks, real-stack publication/download behavior and the file/export stabilization gate.

## Implemented

- The retained viewer has Content, Downloads and History sections. Status, intended audience, verification status and lifecycle actions remain visible. History contains reason, retention, audience availability and append-only lifecycle events. Downloads contains retained formats, extra retained files, and signature/digest details.
- Approval and withdrawal drafts remain intact across sections and keep their existing navigation guard. Corrections preserve their fixed audience and return focus to the correction action when cancelled. Existing backend policies remain authoritative.
- Failed reads show a safe error and retry action. Closing a pending read invalidates it so a late response cannot reopen the viewer. Heading focus follows load/retry, and close restores focus to the publication row.
- Editable exports replace the reader while open and return focus to Export on close. Markdown, HTML, PDF, DOCX and ZIP preserve their existing links and format semantics.
- Primary file versions and attachments are individually selected for ZIP inclusion, with no default selection. The selection count is visible; choices survive closing/reopening exports. Successfully removing an attachment also removes its ZIP selection. Failed removals leave selections intact.
- Empty file lists are explicit. Long filenames and fingerprints wrap within the page, and export controls retain usable targets on narrow screens.
- The viewer and editable export components are separated from the main document workspace. No new API, migration, permission, dependency or version is required.

## Verification

All 54 document component tests and all 36 six-width Chromium/Firefox/WebKit cases pass, including accessibility, focus, denied actions and removed-file selection. The 320px and 1440px viewer/export screenshots were reviewed. The complete file/export stabilization gate passes with one existing backend skip and all 615 frontend tests in 117 files. The real browser/Django/PostgreSQL journey passes publication approval/withdrawal, retained history/PDF, editable Markdown/ZIP and independent database assertions. Component regressions reproduce late reads reopening a closed viewer and removed files remaining in ZIP URLs before the fixes. Final `make check` passes lint/types, API/schema agreement, migration drift, all 615 tests, production build and unchanged bundle budgets. Evidence is recorded in the dated progress.md checkpoint.

## Remaining scope and limits

Managed-file/PDF workflow migration and broader Phase 5 acceptance remained open at this checkpoint. Publication section deep links and history were completed later in [document-direct-links-and-history.md](document-direct-links-and-history.md). Native downloads retain the existing browser/server error behavior; this checkpoint does not introduce a background download manager. Document-wide draft protection, the health queue/link picker and technician acceptance were tracked as separate work. No external publication or deployment is implied.
