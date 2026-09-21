# Managed files and PDF viewing

Phase 5 under #60, version 0.8.46.

## Scope and acceptance

Make Files a focused document workspace with primary-file history and attachment controls. Harden PDF switching, retry, rendering and keyboard focus. Acceptance includes safe denied writes, same-file retry, blocked navigation during file writes, insertion from the ordinary Files action, six-width browser/accessibility checks, the file/export stabilization gate and the real browser/backend file journey.

## Implemented

- Files replaces the reader while open. Primary versions and attachments have separate sections, explicit empty states and wrapping filenames. Closing returns focus to Files.
- Upload and replacement inputs clear after selecting a file, so a failed request can be retried with the same file. Writes disable competing file actions and block application navigation until completion. Existing backend authorization and scanning remain authoritative.
- Primary replacement preserves previous versions. Removing an attachment clears its ZIP selection and closes its matching PDF preview only after success.
- Insert here from the ordinary Files toolbar now opens a file-reference draft at the end of the document. Existing block and insertion drafts still receive the reference, and Files closes to reveal the editor.
- Each PDF URL and retry starts a fresh viewer session. Previous page, scale, text and search state cannot carry into another file. Abandoned loads and searches cannot update the new session. Page/zoom changes cancel old canvas renders before reusing the canvas.
- PDF failures provide a generic error, retry and the protected original download. Accessible text remains available after a same-page search. Escape restores focus to the originating file action; parent updates do not steal search focus.
- The packaged Nginx server explicitly serves module workers as JavaScript while retaining standard MIME mappings, asset caching and security headers. The scrollable PDF canvas is keyboard focusable.
- No API, schema, permission, dependency or version change.

## Verification

Component regressions reproduce stale PDF page/search state and invisible attachment insertion before their fixes. All 620 frontend tests in 117 files, 18 six-width file/PDF browser cases, 36 publication/export browser regressions, four isolated Nginx checks, the file/export stabilization gate and the real browser/backend/database journey pass. The 320px and 1440px screenshots were reviewed. Final lint/build and local readiness pass. Evidence and gate details are recorded in the dated progress.md checkpoint.

## Remaining scope and limits

The main primary-file preview remains available in the reader. Large PDF pages intentionally scroll within the canvas area; page-level overflow is unacceptable. Downloads retain native browser/server behavior. File-write protection does not claim full document-wide draft protection or offline recovery. Publication deep links, the older health queue/link picker, broader Phase 5 acceptance and technician review remain separate work. No external publication or deployment is implied.
