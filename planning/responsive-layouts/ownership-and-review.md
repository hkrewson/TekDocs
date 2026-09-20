# Document ownership and review

Phase 5 under #60, version 0.8.46.

## Scope and acceptance

Move the existing owner, due date, collection, tags, review request and review decision controls into a focused document workspace view. Preserve canonical Markdown and existing workspace authorization. Acceptance requires explicit loading/empty/error states, failed-write draft retention, protected navigation, keyboard focus, six-width browser coverage and a real browser/Django/PostgreSQL review lifecycle with independent database assertions.

## Implemented

- **Ownership and review** is a direct action on an opened document. The view replaces the reader while open and returns keyboard focus to its action when closed.
- Owners, eligible reviewers and governed tags load only when the view opens. A failed read blocks editing and offers a read-only retry; missing tag data never silently enables free-form tags.
- The summary shows saved owner, due date, review state, assigned reviewer, requester/time, decision time, latest note and last approval where available.
- Document selection uses the application router so native Back can preserve or explicitly discard a review draft before restoring the library. Interrupted deep-link loads remain retryable; a document is marked opened only after its load completes. Explicit selections are already loaded and cannot be reopened by a later list response that would overwrite new settings.
- Ownership, review request, decision and client-term drafts participate in application navigation protection. Failed mutations retain drafts; in-flight writes disable fields and duplicate submission and prevent discard/departure.
- Successful operations saves use the normalized server response as the new draft baseline. Review requests and decisions preserve separate unsaved ownership changes.
- Review request copy explains replacement of a pending assignment. Only the assigned authorized reviewer may decide, enforced by the existing server policy; denials remain visible with the note preserved.
- Existing governed-tag search, retained terms and explicitly enabled client-local terms remain available. No new API, model, migration, permission or dependency is introduced.

## Verification

The 47 document component tests pass. The complete Docker documentation validation gate passes with one existing skip. All 42 six-width and Back/reload Chromium/Firefox/WebKit cases pass in the repository's pinned browser container, including accessibility and overflow checks. Screenshots at 320px and 1440px were reviewed. The real browser/Django/PostgreSQL journey and independent database assertions pass for owner/due date/collection, request, changes requested, re-request, approval, reload and exact audit-event retention. Wiki validation passes for all 37 pages. `make check` passes with all 608 frontend tests in 117 files, lint/types, API/schema agreement, migration drift checks, the production build and unchanged bundle budgets. No gates are blocked. Detailed reproduction and final evidence are recorded in progress.md.

## Remaining scope and limitations

This checkpoint does not claim Phase 5 or technician acceptance. Static publication/export and managed files are next. Full document-wide draft protection and the older content-health queue/document-link picker still need assessment. The existing server uses current-document review state rather than binding approval to a frozen revision; this change does not add optimistic concurrency or alter review policy. Unsaved drafts remain in memory and browser departure prompts protect them; they are not persistent offline drafts.
