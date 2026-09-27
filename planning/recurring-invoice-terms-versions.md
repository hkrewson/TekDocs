# Effective recurring invoice terms — 0.8.46 checkpoint

Issue #76 pre-1.0 implementation checkpoint. The application version remains
`0.8.46`. This slice establishes the retained data and service boundary for
future recurring sell-term changes. The later signed API and operator workflow
are now complete and linked below.

## Delivered boundary

- Each approved terms row has an `effective_from` billing-period start.
- Existing version-one rows are backfilled from their schedule anchor during
  migration, without changing schedule, claim, invoice, or line identities.
- Later versions are append-only, use consecutive version numbers, advance in
  effective-date order, and cannot begin on a claimed period or replace one.
- The schedule, source cost, currency, anchor, interval, and end remain fixed.
  Description, quantity, unit price, due days, and an effective immutable tax
  version may change for a later complete period.
- Amendment rechecks the current source snapshot and expected latest terms under
  locks. It rejects stopped schedules, stale source or terms, backdated dates,
  partial or unaligned boundaries, currency changes, and boundaries at or before
  a retained claim.
- Generation selects and locks the newest terms effective for the requested
  period. The resulting permanent claim references that exact terms row.
- A preview may cover only one approved terms version. A selection crossing a
  version boundary is refused so the existing signed preview remains internally
  consistent; the operator must review each side separately until the amendment
  API introduces an explicit boundary comparison.
- Schedule detail responses now include each terms version's effective date.
  OpenAPI and the generated browser type record this additive field.

## Database enforcement

PostgreSQL enforces exact tenant and organization scope, source currency, actor
membership, source digest shape, schedule enabled state, consecutive versions,
unique schedule/version and schedule/effective-date pairs, anchored full-period
starts, tax scope and effective dates, and the claimed-period boundary. Existing
retention triggers continue to reject terms updates and deletes. Row-level
security classification is unchanged because this migration adds a field and
constraints to an already forced-RLS model.

The insertion guard locks the schedule before examining the version chain. The
application follows the established contract, cost, schedule, and terms lock
order. Concurrent generation and amendment therefore commit either the prior
reviewed terms or the new reviewed terms as a unit; line values cannot mix
versions.

## Compatibility and recovery

The schedule detail change is additive. Existing enrollment, preview/apply,
generation, retry, stop, and recovery paths retain their routes and request
formats. Legacy version-one schedules continue generating from their anchor
after upgrade. A reversible migration restores the prior version-one constraint
when the database contains only the compatible initial version; supported
rollback policy still governs whether a populated newer schema may be rolled
back.

The stopped-schedule backup rehearsal from
[recurring-invoice-stop-recovery.md](recurring-invoice-stop-recovery.md) remains
authoritative for retained stop and claim recovery. The final recurring-invoice
acceptance slice must extend that fixture with multiple terms versions before
the lifecycle work is closed.

## Verification evidence

- Migration state matches the Django model and the upgrade round trip backfills
  an existing version-one row from a January 31 anchor.
- Direct database inserts prove skipped and unaligned versions fail below the
  service layer.
- Service tests cover future amendment, stale/claimed/backdated/partial/stopped
  rejection, exact old/new generation values, idempotent prior claims, and a
  concurrent amendment/generation race.
- API tests cover additive effective dates and refusal of one signed preview
  spanning two approved versions.
- The focused recurring-invoice backend suite, OpenAPI generation/check,
  frontend typecheck, and recurring-invoice component tests are the required
  gates for this checkpoint.

## Remaining lifecycle slices

1. Add retained recurring-draft withdrawal and its edit/issue restrictions.
2. Extend recovery, live browser, responsive/accessibility, and final release
   acceptance across amendments and withdrawals.

The authenticated signed preview/apply API is complete and recorded in
[recurring-invoice-terms-api.md](recurring-invoice-terms-api.md).
The operator workflow is complete and recorded in
[recurring-invoice-terms-interface.md](recurring-invoice-terms-interface.md).

Deployment, external push, Wiki publication, and a version change are outside
this checkpoint.
