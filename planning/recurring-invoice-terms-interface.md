# Recurring terms operator workflow — 0.8.46 checkpoint

Issue #76 pre-1.0 implementation checkpoint. Version remains `0.8.46`. This
slice makes the signed recurring-terms amendment API usable from the Recurring
invoices surface without changing the schedule calendar or prior financial
history.

## Delivered workflow

- An enabled schedule exposes **Change future terms** beside the terminal stop
  action. Stopped schedules remain history-only.
- The form begins from the newest retained terms version and refreshes the
  current source cost and eligible tax choices before review.
- The operator chooses an aligned future billing-period start and may change the
  client description, quantity, unit price, due days, and tax. Currency remains
  fixed and the interface explains that schedule dates cannot change here.
- Review shows the current and proposed terms side by side, including exact
  period totals. A source-change notice makes approval of a refreshed source
  snapshot explicit.
- Apply uses only the short-lived signed preview token. An expired review must be
  regenerated. An uncertain failed apply retains the token so the idempotent API
  can be retried safely.
- Successful apply appends the returned version to the selected schedule,
  refreshes the collection, clears generation state, and displays the newest
  terms. Every prior version remains available in retained terms history.

The amendment form temporarily replaces period discovery and generation for the
selected schedule. This prevents an operator from mixing a terms amendment with
an outstanding generation review. Existing responsive record-form and detail
list patterns keep the workflow usable without adding another nested scrolling
surface.

## Navigation and failure behavior

The form participates in the shared dirty-form guard. Cancel, route changes,
browser navigation, and other guarded exits offer Keep editing or Discard
changes. Validation, permission, conflict, network, and uncertain apply failures
leave entered values in place. Source-refresh failure is retryable. Editing any
field invalidates an earlier preview.

## Verification evidence

- Component coverage proves source review, amendment preview, exact proposed
  totals, apply, schedule refresh, and retained version history.
- Dirty cancel coverage proves both Keep editing and Discard changes behavior.
- Type checking and focused lint pass for the new client and component.
- The maintained frontend gate passes: 120 test files and 675 tests, including
  the existing recurring enrollment, generation, stop, navigation, responsive,
  and accessibility-adjacent component coverage.

## Next lifecycle slice

The retained withdrawal data, service, and API boundary is complete in
[recurring-invoice-draft-withdrawal.md](recurring-invoice-draft-withdrawal.md).
Add its focused invoice-screen confirmation and retained-history presentation,
then extend recovery and live browser acceptance across both amendments and
withdrawals.

Deployment, external push, Wiki publication, and a version change remain outside
this checkpoint.
