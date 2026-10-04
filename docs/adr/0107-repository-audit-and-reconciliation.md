# ADR 0107: Repository audit attribution and accepted-head reconciliation

Status: Accepted

Date: 2026-10-03

## Context

Managed Git records content history, but its author fields are service-generated
text and cannot prove which authenticated TekDocs principal performed or
approved an action. A crash, manual repository change or damaged object can also
leave the Git branch different from PostgreSQL's accepted commit.

## Decision

PostgreSQL remains authoritative for the accepted repository head. TekDocs
stores an immutable, database-guarded mapping from each attributed commit to an
append-only audit event containing the authenticated actor, action and request
correlation. Git commits retain the fixed TekDocs Repository Service identity;
Git author text is never treated as approval evidence.

Reconciliation classifies each repository as matched, missing, advanced,
mismatched, corrupt or unavailable. Ordinary writes require a matched head and
fail closed on every other state. Reads address the accepted commit directly and
remain available when that commit is intact, even if the branch has advanced or
diverged.

Diagnosis only records bounded health. It never advances PostgreSQL to an
unaccepted Git commit. The explicit repair operation may restore the Git branch
to the verified accepted commit, or delete an unaccepted branch when no commit
has yet been accepted. It cannot repair a missing accepted object.

Readiness exposes only a coarse repository status. Authorized system
diagnostics expose aggregate counts, reconciliation states, the last check time
and fixed repair guidance; they expose no repository paths, identifiers or
content.

## Consequences

- Git history provides revision mechanics, while TekDocs audit records provide
  authenticated attribution.
- Crash-window and manual-advance states pause writes without sacrificing a
  usable last-known-good read.
- Operators must explicitly choose repair-to-accepted; TekDocs never silently
  accepts the newest reachable Git commit.
- Repository health can affect readiness without disclosing custody layout or
  authored values.
- A remote Git service remains optional and cannot replace accepted-head state,
  audit evidence or supported backup.
