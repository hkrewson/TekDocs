# Invoice settings workspace

## Scope

Phase 6 migrates the MSP invoice settings route from one competing long form to
three focused, URL-addressed sections: business details, invoice defaults and
invoice numbering. Existing invoice readiness, permission, MFA and recent
authentication rules remain authoritative.

## Acceptance

- Opening `/invoices` shows business details and one settings section at a time.
- Each section has a stable URL, survives reload and browser history, and moves
  focus to its first field after navigation.
- Desktop section links become one labeled section selector below 768px.
- Unsaved settings block section and page navigation, support Keep editing and
  Discard changes, and retain failed saves for correction.
- A failed settings read has an in-place retry. Saving after expired recent
  authentication retains the draft and uses the existing password confirmation.
- Readiness issues remain visible in every section, while successful saves replace
  the dirty baseline returned by the server.
- The workspace fits 320, 390, 768, 1024, 1280 and 1440px in Chromium, Firefox
  and WebKit with no horizontal page overflow or automated accessibility violations.

## Evidence

- Component behavior: `frontend/src/accounting/InvoiceSettings.test.tsx`
- Browser matrix: `frontend/e2e/invoice-settings-layout.spec.ts`
- API and recent-auth behavior: `frontend/src/accounting/api.test.ts` and the
  existing invoice backend target

The browser matrix passes 21 cases across the three maintained engines. The
component suite covers focused rendering, direct sections, navigation protection,
retry, retained failed saves and recent-authentication confirmation. The
repository-wide gate passes all 632 frontend tests in 117 files, schema and
migration agreement, policy checks, the Wiki contract and production bundle
budgets.
