# Recurring invoice lifecycle policy

Issue #76 decision checkpoint. Version remains `0.8.46`. This document defines
the safe boundary for amendments, stopped schedules, partial periods, and invoice
corrections before another recurring-invoice mutation is implemented.

## Decisions

### Stopping is terminal

A stopped schedule cannot restart. Its source identity, anchor, interval,
approved terms, claims, generated drafts, stop actor, reason, and time remain
retained. A later commercial agreement is enrolled as a new source cost and a
new schedule after the operator reviews the prior schedule and outstanding
invoices. The product must not present this as reopening the old calendar.

This keeps the existing one-schedule-per-cost rule meaningful and avoids an
enable toggle generating periods under terms that were previously declared
finished. Calendar replacement and source-cost replacement are outside the
bounded 1.0 workflow; they require explicit lineage and overlap rules before
they can be supported as one operation.

### Amend only future full-period sell terms

An enabled schedule may receive an append-only approved-terms version. The
effective date must be an anchored full-period start, must follow every claimed
period, and cannot precede the current business date. It may change description,
quantity, unit price, immutable tax version, and due days. Currency, source cost,
anchor, interval, and schedule end remain fixed.

The operator must refresh and approve the current source snapshot even when only
the sell price changes. The new version retains that digest and snapshot. Period
generation chooses the latest terms version effective on or before the period
start and stores that exact version in the permanent claim. A preview shows old
and new totals at the boundary. Apply rechecks the schedule, source, prior terms,
claims, and preview identity under locks; a stale or newly claimed boundary is
rejected.

Terms versions form a gap-free projection: version one is effective at the
schedule anchor, and each later version remains effective until the next version.
There is no mutable end date on a terms row and no deletion or rewrite. Only one
version may begin on a given schedule/date.

### Partial periods remain manual

Recurring generation continues to refuse shortened or mid-period intervals. An
amendment begins on the next complete anchored period. Any agreed mid-period
difference is entered as a separately reviewed ordinary draft line; TekDocs does
not calculate proration. The operator-facing review must explain that the manual
line is outside recurring generation and does not consume a recurring claim.

### Claims never reopen

Stopping, amending, withdrawing a draft, voiding an issued invoice, or recording
a credit never releases a `RecurringInvoicePeriod`. The same schedule and period
can never generate another invoice. This remains true after retry, upgrade, and
restore.

An unissued recurring draft needs a retained **Withdraw draft** disposition
before recurring invoicing is represented as complete. The disposition is an
append-only, one-per-claim record with actor, reason, and time. It does not delete
the invoice, line, or claim. A withdrawn recurring draft cannot be edited or
issued, remains visible as retained history, and is excluded from ordinary
actionable-draft counts. Repeating the request returns the same disposition and
does not replace its first reason.

Issued invoices keep the existing append-only invoice lifecycle. A not-yet-
delivered issued invoice may be voided under the existing privileged policy; a
delivered or otherwise incorrect invoice is corrected by an explicit credit
reference. Neither action alters the recurring claim or automatically changes
future schedule terms.

## Required implementation slices

1. **Effective terms schema and guards.** Remove the version-one-only constraint;
   add an aligned `effective_from` date; enforce unique version/date ordering,
   exact scope, actor, source digest, immutable rows, and forced RLS. Upgrade
   existing version-one rows with the schedule anchor without changing claims.
2. **Amendment service and API.** Add source review, boundary preview, and atomic
   apply with central invoice/cost permissions and MFA. Reject stopped schedules,
   claimed/backdated/partial boundaries, currency or calendar changes, stale
   source/terms, cross-client identifiers, and uncertain overrides.
3. **Generation selection.** Select and lock the effective terms version for each
   period, bind it into the signed preview, and retain it in the claim. Prove
   concurrent amendment/generation results in either the old or new reviewed
   version, never mixed terms.
4. **Retained draft withdrawal.** Add the append-only one-per-claim disposition,
   database guards, issue/edit refusal, derived display state, confirmation,
   idempotent retry, and value-minimized audit event.
5. **Operator workflow.** Show the current and proposed sell terms, effective
   period, affected future periods, source changes, and retained prior versions.
   Stopped schedules expose history and invoice links without restart controls.
6. **Acceptance.** Cover allow/deny, tenant/client isolation, stale previews,
   source drift, tax effective dates, exact-money totals, concurrent generation,
   claimed boundaries, partial-period refusal, withdrawn drafts, void/credit
   independence, upgrade, backup/restore, live browser, responsive/accessibility,
   and risk documentation.

## Explicitly unsupported

- restarting a stopped schedule;
- changing a schedule's source cost, currency, anchor, interval, or end date;
- automatic proration, credit, void, issue, delivery, or background generation;
- replacing one schedule with another through an inferred source relationship;
- releasing a period claim after any cancellation or correction.

These exclusions preserve the current append-only financial boundary. They may
be reconsidered only with an explicit lineage and correction design rather than
an enable toggle or mutable schedule fields.
