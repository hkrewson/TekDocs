# Recurring invoice lifecycle recovery

Issue #76 continuation after the operator stop workflow. Version remains
`0.8.46`. This checkpoint extends the existing recurring-invoice recovery
rehearsal. It now covers stopped schedules, effective terms amendments, and
retained draft withdrawals without changing the application schema, API,
authorization policy, invoice lifecycle, or deployment state.

## Recovery boundary

The isolated source fixture now creates two schedules for one client. The active
schedule retains the original January 31 monthly anchor, approved quantity 2 at
USD 75, immutable 10% tax version, and one generated draft. A separate cost is
enrolled at approved quantity 1 and USD 90, generates its own January draft, and
is stopped through the application service with an operator reason.

The external manifest records the exact contracts, costs, tax version,
schedules, approved terms, claims, invoices, and lines. It separately records
the stop event identifier, tenant, actor, action, contract entity, reason, and
timestamp. The manifest remains outside the PostgreSQL dump so restoration must
match an independent baseline.

After restoring into a clean stack, verification requires the stopped schedule
to remain disabled and the complete stop event to match the external record.
Period discovery must expose the retained invoice while marking every stopped
period unavailable for generation. A direct retry of the already claimed period
must return the retained draft, while an unclaimed period must fail as disabled.
Retrying the stop with a different reason must retain the original event without
creating another audit record.

The active schedule continues to prove recovery of the original calendar. Two
fresh reviews reuse its January claim, and February 28 generates one distinct
period ending March 31. Retrying that period returns the same invoice. The prior
forced-RLS, sibling-client and wrong-tenant isolation, immutable-history, runtime
role, retained provenance, unissued-draft, and Django system checks remain in the
same rehearsal.

The active schedule now also retains a second approved terms version effective
on the February 28 boundary. Its description, quantity, price, tax, due days,
source snapshot, approver, amendment audit identity, and effective date are part
of the external manifest. The January draft is withdrawn before backup. The
withdrawal identifier, first reason, actor, time, related period/invoice, and
value-minimized audit event are independently recorded.

After restore, direct database attempts to rewrite or delete the withdrawal, or
to change its retained invoice and line, must fail. Sibling and wrong-tenant
scopes must not see the withdrawal. Retrying the January generation continues
to return the same withdrawn claim without reopening it. The February 28 draft
must use the restored second terms version at quantity 3 and USD 80, proving the
effective-boundary selection survived recovery.

## Verification

**Verified:** `make recurring-invoice-backup-rehearsal` passed with disposable
source and restore stacks. The independently serialized baseline matched before
post-restore actions. The stopped schedule retained its exact audit and invoice,
refused future generation, and produced no duplicate event on retry. The active
schedule retained month-end continuation, its append-only terms amendment, the
withdrawn first claim, immutable reason and audit identity, idempotent claims,
and amended generation. Both stacks, their volumes, images, and temporary
artifacts were cleaned up.

The fixture passes the backend Ruff configuration and formatting check, Python
compilation, shell syntax from the unchanged rehearsal, and `git diff --check`.
No broad release gate was rerun because this slice changes only the dedicated
recovery fixture and its evidence.

## Remaining decisions

Replacement and restart workflows remain unsupported. Effective amendments and
retained withdrawal now follow the decisions in the lifecycle policy. Automatic
proration remains refused, and issued-invoice corrections continue through the
separate void/credit lifecycle.

Final recurring-feature risk disposition, the applicable security and pilot
evidence, the full release gate, and Wiki checkout reconciliation remain open.
No deployment, push, publication, tag, or version change is part of this
checkpoint.

The subsequent amendment, withdrawal, and correction decisions are recorded in
[the recurring invoice lifecycle policy](recurring-invoice-lifecycle-policy.md).
