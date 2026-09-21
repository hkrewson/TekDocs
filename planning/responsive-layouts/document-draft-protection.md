# Document-wide draft protection

Phase 5 under #60, version 0.8.46.

## Scope and acceptance

Protect unfinished document work across the focused workspace. The boundary includes new documents, document settings, inline block edits, new sections, shared-edit impact review and monitored web-source settings. Acceptance requires Keep editing and Discard changes behavior for local actions and browser Back, safe writes that cannot be abandoned while pending, preserved denied-write drafts, keyboard focus, six-width browser/accessibility checks and the real browser/backend document journey.

## Implemented

- New-document title, Markdown, category, starter type, template visibility and selected primary file participate in one draft boundary. Switching document source or closing a changed draft asks before clearing it.
- Existing document title, Markdown and settings compare with the selected saved record. Toolbar changes, template actions, section conversion, web-source settings, client listings, related records and archive actions use the shared navigation boundary.
- Inline block edits and new-section drafts prompt before Cancel, Escape, audience-preview changes or another insertion. Keep editing leaves the editor and its content intact; Discard clears the draft and restores its saved baseline.
- Shared edits remain protected while their audience impact is reviewed. Monitored web-source URL, format, schedule and interval compare with the last saved source; server-normalized values become the new baseline after save.
- A document save in progress disables departure until the request has a known result. Successful saves release the guard; failed saves retain the entered values. Existing publication, ownership/review, template-rollout and file-operation guards remain independent and share the same accessible dialog.
- No API, schema, permission, dependency, visual-system or version change is required.

## Verification

Component regressions reproduce unguarded new-document departure and settings-to-Files switching before the fix. All 58 focused component tests pass, including inline drafts and a pending settings save, and the full project gate passes all 623 frontend tests in 117 files.

The Docker browser matrix passes 72 cases across Chromium, Firefox and WebKit at 320, 390, 768, 1024, 1280 and 1440px. Eighteen new draft-protection cases cover settings, inline content, new sections, web-source changes, browser Back, keyboard focus, accessibility and page overflow; 54 existing publication, export and managed-file cases remain green. The real browser/backend/PostgreSQL journey confirms Keep editing and Discard changes against a saved document. Detailed commands, artifacts and logs are recorded in the dated progress checkpoint.

## Remaining scope and limits

Protection is in memory and lasts for the current loaded workspace. It does not add offline recovery, cross-device drafts or background autosave. Saved remote observations, publication decisions, ownership/review forms, template rollout and file mutations retain their existing specialized behavior. The older health queue/link picker, remaining direct-link/history acceptance and technician review remain separate Phase 5 work. No external publication or deployment is implied.
