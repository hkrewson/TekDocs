# Native template enrollment source review

Scope: the bounded development slice after `e6224338`, described in
[native template acceptance](../git-native-templates.md) and
[ADR 0127](../../docs/adr/0127-native-template-enrollment.md).
This records automated source review, not independent human assurance or release
approval. Combined backend validation passes 796 cases. All 15 browser/server journeys pass. Exact-source
hosted evidence follows the authorized push.

## Spec review

Independent review identified archive revocation, removed-section review, cached
discovery/graph reads and offline-source isolation gaps. Each was reproduced
through an affected public route before correction. Re-review found no remaining
source findings: exact grant validation remains mandatory, affected unavailable
content has an empty projection, and independent copies remain usable.

## Standards and security review

Independent review checked central policy, exact tenant/client ownership, RLS and
immutable revision constraints, scoped foreign reads, legacy-shadow exclusion,
Git/database compensation, publication proof, and interface draft protection.
Archive and offline-source findings were reproduced and corrected. Re-review
found no remaining actionable Standards or security findings.

SQL evidence tests reject changed selected bytes, invented revisions and an
existing sibling enrollment's borrowed grant. Offline verification succeeds with
current template/Git readers disabled. Client publication tests exercise both
primary-file and Markdown-only delivery contracts, independent approval, frozen
downloads, isolation and withdrawal. These targeted checks supplement rather
than replace the combined and hosted gates.

## Disposition

No new runtime dependency, cryptographic primitive, external connector, deployment
or existing-data transition is introduced. Historical signatures and evidence
formats remain unchanged. Existing browser-policy/dependency risk decisions are
not renewed by this development change. Arbitrary hostile SQL under a trusted
runtime role remains outside the claimed boundary (`TD-RISK-073`, approved 1.x
work); the change does not claim to resolve that broader security limitation.

The final test/diagnostic delta was re-reviewed with no findings: only fixed phase
names, status/timing and allowlisted UI booleans are retained; tests restore mocks,
browser location and migration head. An extra diagnostic API request was removed
in favor of observing the interface's own request. Browser assertions and budgets
remain unchanged.

The browser label defect was reproduced in Docker Chromium with the original
wrapped label: exact lookup found no field while partial lookup found it. The
explicit stable `useId`/`htmlFor` association passes the same reproduction and
retains the translated label, value and change handling. Narrow source re-review
found no issues; the original exact browser assertion remains in place.

The responsive follow-up removes only the mobile content-margin transition at the
existing breakpoint. Full-shell Chromium geometry reproduces immediate 523/390
overflow before the change and 390/390 after it. Desktop collapse and the mobile
sidebar transform remain unchanged. Narrow source re-review found no issues.

The read-only fixture follow-up assigns only its newly created synthetic client
through the existing account access-control service. A constrained-runtime
regression verifies denial before assignment, permitted reads afterward and
continued write denial. Safe reader diagnostics and cleanup preserve the original
failure without recording account/session payloads. Source re-review is clear;
Docker collection also verifies the corrected assignment-helper import.
