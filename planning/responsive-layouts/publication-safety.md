# Publication draft and preflight safety

Phase 5 under #60, version 0.8.46.

## Scope and acceptance

Protect publication and lifecycle decision drafts, make preflight retries safe, and verify the existing editable export choices. Acceptance covers late audience-check responses, failed reads and writes, cancel and browser Back, in-flight input protection, keyboard focus, six viewport widths and retained publication/export behavior against the real Docker stack. This is a bounded safety checkpoint within the broader publication/export migration.

## Implemented

- Publication setup replaces the reader or retained publication while open. Initial focus moves to its heading; cancellation returns focus to the originating action.
- Publication reason, audience, retention and review date participate in the shared unsaved-change guard. Approval and withdrawal reasons are protected when cancelling, navigating away or switching decisions/corrections.
- A monotonically increasing request identity prevents an older preflight success or error from replacing the latest audience check. Closing a draft invalidates outstanding checks; reopening starts a fresh check.
- Failed and blocked preflights offer a retry without clearing input. Publish remains disabled during checks and for blockers, a missing reason or an absent required review date.
- Publication and decision mutations freeze input and prevent duplicate submission while pending. Failed writes preserve drafts and expose the existing safe server-denial message.
- Editable Markdown, HTML, PDF, DOCX and selected-file ZIP links keep their existing contract. Retained publication downloads, signatures, audience projections, approval, withdrawal and correction semantics remain unchanged.
- No API, database schema, authorization policy, dependency or version change is required. Server-side publication validation remains authoritative; the browser preflight does not reserve a document revision.

## Verification

The full `make check` passes with 612 frontend tests in 117 files, including 51 document component tests, plus lint/types, API/schema agreement, migration drift, production build and bundle budgets. All 18 six-width Chromium/Firefox/WebKit cases pass in the pinned Docker browser runner, with accessibility, overflow, Back and focus checks; 320px and 1440px screenshots were reviewed. The real browser/Django/PostgreSQL journey passes publication draft recovery, independent approval, withdrawal, retained PDF and editable Markdown/ZIP checks, with independent database assertions. The complete `make test-publication-control` gate passes, including backend checks with one existing skip and its required frontend rerun. The maintained Wiki passes all 37 pages. See the dated checkpoint in progress.md for gate completion and reproduction evidence.

## Remaining scope

The broader publication viewer/export layout, managed-file/PDF workflow migration, full document-wide draft protection and technician acceptance remain open. Drafts are held in memory, not persisted offline. This checkpoint does not complete Phase 5 or authorize external publication or deployment.
