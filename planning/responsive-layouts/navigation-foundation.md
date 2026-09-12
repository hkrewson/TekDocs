# Navigation and edit protection foundation (#88)

Pre-1.0, version 0.8.46. This completes a bounded dependency of the responsive Assets implementation, not the full navigation or layout phase.

## Implemented

`ApplicationRouter` supplies the React Router data router required by `useBlocker`, retaining browser navigation in the application and memory navigation for injected test paths. Router creation/disposal is owned by an effect to avoid leaking external history listeners during StrictMode setup/cleanup. Application content flows through context so changed client/auth props do not recreate the router.

Organization route registration now derives from the existing capability registry instead of a duplicate table of unused descriptions and release labels. Existing MSP paths, organization paths (including `custom_fields` and `recycle_bin`), accounting redirects, auth entry paths and portal boundaries stay intact.

The shared navigation guard has one router blocker and a registry of active editors. The hook records dirty, active and busy state plus a reset callback. It guards router links, query/section changes, programmatic navigation, Back/Forward and native unload. Local actions such as record switching, pagination, closing an editor and sign out use the same guard. It never writes replacement history entries to simulate cancellation.

- Keep editing and Escape retain entered values and cancel the pending transition.
- Discard resets active editors and performs the pending transition once.
- Untouched active editors close without an unnecessary discard prompt when another editor opens.
- In-app discard is disabled during in-flight requests; native unload prompts remain browser-controlled. A completed request can be followed by an explicit Continue when no changes remain.
- A native modal dialog makes the background inert, locks body scrolling, wraps keyboard focus, and restores focus on close. Its body is bounded to the viewport and scrolls if needed; its stylesheet loads with the dialog rather than enlarging the shell stylesheet.
- Refresh/close/external navigation use the browser-controlled beforeunload prompt. Custom prompt wording is available only for in-app transitions.

Assets integrates the guard for creation, hardware details, assignment/disposal, MAC addresses, software installation and CSV import. Record changes and pagination go through guarded actions; keyed editors cannot carry stale form state into another record. Opening another editor closes an untouched editor or asks before discarding changed values. Creation failures appear inside the editor, preserving the chosen model and name. Bulk writes and other pending mutations also prevent accidental navigation while their outcome is unresolved.

## Save/history regression

The focused regression initially reproduced the existing defect: a successful hardware update followed by a rejected history fetch left Save details visible, treating the successful write as unfinished. The write result now closes the edit and updates current state immediately; an independent history read ignores responses after cleanup and shows its own error and Retry history action. A history read does not reset edited values or retry a mutation. The existing delayed-history regression remains covered.

The first browser run also found that native dialog behavior alone did not wrap Shift+Tab directly to the last button. Explicit boundary handling now keeps keyboard focus within this two-action dialog; assertions were retained. The native-unload test uses a bounded reload wait because canceled navigations may not produce a load event, and verifies retained values immediately after dismissing the browser prompt.

The live browser flow passed initially, but the independent PostgreSQL verifier caught an empty asset tag. A focused Chromium reproduction verified that editing the tag immediately after Keep editing could submit an empty value while later fields were intact. Router blocker reset is transition-based, so the native confirmation could finish closing/restoring focus over that next edit. The provider now dismisses that specific blocker urgently while letting the router reset normally. A new request-payload assertion remains in both the focused browser test and live journey; the database assertion was not weakened.

## Verification and remaining work

See progress.md for final gate results. Focused component tests cover local close, failed saves, clean/dirty editor transitions, record changes, query changes, Back/Forward, native unload registration, busy requests, and the history regression. Browser checks cover all six planned widths at a 600px height, native focus/background behavior, accessibility checks, Back/Forward and refresh on Chromium, Firefox and WebKit. The live workspace journey now attempts to leave a hardware edit, chooses Keep editing, verifies the serial value, then saves through the real Django/PostgreSQL workflow.

Not claimed here: URL-addressable Assets records/tabs/list conditions, quick drawers, list scroll restoration, column preferences, responsive collection layouts, 200% zoom or touch acceptance across whole pages, or protection of every editor elsewhere in the app. These remain explicit pre-1.0 work. The shared guard must be integrated deliberately into each migrated workflow; adding a provider does not protect unregistered forms.

No new API, permission, domain migration, deployed container, release version or public publication is part of this slice. The production-image/live stack is isolated from existing user and demo data.
