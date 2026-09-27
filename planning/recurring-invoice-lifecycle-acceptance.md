# Recurring invoice lifecycle acceptance — 0.8.46 checkpoint

Issue #76 pre-1.0 acceptance checkpoint. Version remains `0.8.46`. The bounded
recurring-invoice workflow now covers enrollment, signed generation review,
append-only future terms, terminal schedule stop, and retained withdrawal of an
unissued generated draft.

## Operator journey

The real browser-to-Django-to-PostgreSQL workspace rehearsal now performs the
complete lifecycle through production-shaped services:

1. enroll a monthly service from a retained contract cost;
2. review and create the first due draft;
3. open the invoice, withdraw it with an explicit reason, and confirm it becomes
   read-only retained history;
4. append version 2 at the next aligned full-period boundary after reviewing the
   old and proposed totals;
5. stop future drafts with a separate retained reason;
6. refresh the application, rediscover the stopped schedule and original period,
   and reopen the withdrawn invoice through its stable record URL.

The journey uses the actual authentication, MFA, authorization, HTTP, database,
and frontend paths. The invoice collection excludes the withdrawal by default;
the schedule period remains the stable way back to the claimed historical
invoice, while the explicit Withdrawn collection filter supports direct history
browsing.

## Independent persistence checks

After the browser finishes, the isolated rehearsal inspects PostgreSQL through
the restricted application stack. It verifies:

- version 1 remains bound to the generated period and retains quantity 2 at USD
  75 with its original due days;
- version 2 retains the next aligned effective date, quantity 3 at USD 80, due
  days 45, source snapshot, approver, and exact amendment audit metadata;
- the first claim, invoice, and line remain unissued and unchanged;
- the withdrawal retains its first reason, actor, time, period, invoice, and
  value-minimized audit event;
- the terminal stop retains its reason, actor, and schedule identity.

The separate backup/restore rehearsal serializes these records into an external
manifest, restores them into clean database and media volumes, and proves forced
row isolation and database immutability. It then generates the next period under
the restored version 2 terms and proves retry idempotency.

## Verification evidence

- `make recurring-invoice-backup-rehearsal` passes for a disposable source and
  clean restore stack.
- `make test-e2e-live` passes the real Chromium, Django, and PostgreSQL journey
  plus independent retained-record assertions.
- The focused invoice browser test passes at 390 CSS pixels with keyboard focus,
  accessibility, read-only controls, and horizontal-overflow checks.
- Focused API, service, component, OpenAPI, migration-drift, frontend lint,
  typecheck, production build, and bundle-budget checks pass.

## Remaining pre-1.0 work

The recurring lifecycle implementation and its feature-specific recovery/live
acceptance are complete. The shared full release gate, commit-matched security
evidence, technician walkthrough/pilot, risk closeout, and Wiki reconciliation
remain overall pre-1.0 obligations. Replacement schedules, restart, and
automatic proration remain deliberately unsupported. Deployment, external push,
publication, tagging, and a version change are separate actions.
