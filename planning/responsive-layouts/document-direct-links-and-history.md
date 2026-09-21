# Document direct links and retained history

Phase 5 under #60, version 0.8.46.

## Scope and acceptance

Finish the remaining document navigation acceptance by making focused document tools, revision history and retained publication sections restorable from the page address. Acceptance requires refresh and direct entry, browser Back/Forward, selected revision restoration, paged history, retryable reads, protected unfinished ownership/review work, six-width browser/accessibility checks and the real browser/backend workspace journey.

## Implemented

- Focused Ownership and review, Document settings, Files, History, Keys and Export views use `document_view`. Closing a view removes its view-specific parameters while retaining the selected document and library conditions.
- Revision history uses `document_history_page`; a selected comparison uses `document_revision`. Direct entry loads the requested page and comparison, and Back/Forward traverses comparison, page and document states without bypassing the shared draft guard.
- Retained publications use `publication` and `publication_section`. Content omits the section parameter; Downloads and History retain it. The displayed section is derived from the accepted router location, so refresh and browser history cannot leave the address and viewer out of sync.
- Opening a URL-backed document tool waits for its router transition before mounting the tool. This avoids a query-only transition mounting the tool twice while preserving explicit error and Retry states.
- Moving from a URL-backed tool into insertion, sharing, relationships, remote-source or restructuring work clears stale view state. Inserting a managed file also returns to the editor without reopening Files from the old address.
- No API, model, migration, permission, dependency or version change is required.

## Verification

Component regressions cover a direct page-two revision comparison and a retained publication opened directly in History. The browser matrix covers Chromium, Firefox and WebKit at 320, 390, 768, 1024, 1280 and 1440px, including failed history reads and Retry, paging, selected revisions, refresh, Back/Forward, retained publication section history, accessibility and page overflow. Existing ownership/review browser coverage now also verifies URL retention across retry, Keep editing, reload, Discard and browser Back.

The real browser/Django/PostgreSQL journey opens a saved revision from its retained address, reloads it, returns to the document, opens a withdrawn publication in History, reloads it and confirms the retained withdrawal event. Final project, documentation, browser and live-stack results are recorded in `progress.md`.

## Remaining scope and limits

These parameters restore document workspace presentation; they do not create public or cross-workspace sharing links and do not weaken normal authorization. Invalid view and section values fall back to the document or publication default, and unavailable records keep the existing safe error behavior. Human technician acceptance remains open before Phase 5 is accepted. No external publication or deployment is implied.
