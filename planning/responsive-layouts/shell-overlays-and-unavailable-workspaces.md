# Shell overlays and unavailable workspaces

This Phase 7 slice applies one interaction contract to the application shell. It
does not change workspace authorization, sign-out behavior, domain data, or the
0.8.46 version.

## Implemented behavior

- The workspace selector, contextual help, notification inbox, and account menu
  share one shell overlay coordinator. Opening one makes the other triggers
  temporarily unavailable, preventing stacked panels and ambiguous focus.
- Dialog-style shell panels keep keyboard focus within the open panel. Escape and
  explicit close actions restore focus to the trigger. Outside clicks retain each
  panel's existing dismissal and dirty-form behavior.
- Small-screen navigation locks background scrolling, focuses its close action,
  traps keyboard focus inside the sidebar, and restores focus to the menu trigger
  after backdrop, close-button, or Escape dismissal. Selecting a destination still
  sends focus to the newly rendered main content.
- The workspace selector keeps bounded server search and capability-aware routing,
  while all of its interface copy now comes from the localization catalog.
- A failed organization-workspace read has an in-place Retry action. Retry keeps
  the direct route, returns the shell to an explicit loading state, and issues one
  fresh read. It never retries automatically and retains the existing value-free
  403/404 handling.

The mobile navigation remains the containing surface for the workspace selector.
It therefore does not claim the global shell-overlay slot; the backdrop and focus
boundary make the top bar unavailable while it is open, while the selector remains
usable inside the sidebar.

## Verification contract

Component coverage checks one-at-a-time overlay behavior, focus wrapping,
translated workspace controls, safe failures, and explicit workspace retry.
Browser coverage checks the same contract in Chromium, Firefox, and WebKit, plus
the required responsive widths in the maintained mobile projects. The responsive
journey checks background scroll lock, Escape dismissal, focus restoration, and
horizontal overflow. Existing shell coverage continues to verify sign out,
permission-aware account links, workspace route preservation, denial
non-disclosure, and accessibility.

This closes the implementation portion of Phase 7. Technician walkthroughs and
the broad production/release gates remain Phase 8 work.
