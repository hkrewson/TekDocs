# Stopped recurring schedule recovery

Issue #76 continuation after the operator stop workflow. Version remains
`0.8.46`. This checkpoint extends the existing recurring-invoice recovery
rehearsal; it does not change the application schema, API, authorization policy,
invoice lifecycle, or deployment state.

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

## Verification

**Verified:** `make recurring-invoice-backup-rehearsal` passed with disposable
source and restore stacks. The independently serialized baseline matched before
post-restore actions. The stopped schedule retained its exact audit and invoice,
refused future generation, and produced no duplicate event on retry. The active
schedule retained month-end continuation and idempotent claims. Both stacks,
their volumes, and temporary artifacts were cleaned up.

The fixture passes the backend Ruff configuration and formatting check, Python
compilation, shell syntax from the unchanged rehearsal, and `git diff --check`.
No broad release gate was rerun because this slice changes only the dedicated
recovery fixture and its evidence.

## Remaining decisions

Effective schedule amendments, replacement and any restart workflow remain
unsupported. Before adding them, define effective dates, overlap and gap
handling, treatment of permanently claimed periods, source-term reapproval, and
the relationship to invoice cancellation or credit. Partial-period charging also
remains a manual refusal rather than an automatic calculation.

Final recurring-feature risk disposition, the applicable security and pilot
evidence, the full release gate, and Wiki checkout reconciliation remain open.
No deployment, push, publication, tag, or version change is part of this
checkpoint.

The subsequent amendment, withdrawal, and correction decisions are recorded in
[the recurring invoice lifecycle policy](recurring-invoice-lifecycle-policy.md).
