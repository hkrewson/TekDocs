# Native publication lifecycle interface

Scope: next bounded 1.0 daily-work slice, after discovery/export at `b7160267`.
The maintainer explicitly included staff-only native publication on November 2.
No legacy Document row, automatic migration, primary-file controls, configuration
work, production operation or retained-data change is included.

Acceptance: a new Git-only document completes publication, correction,
withdrawal, retained history/PDF and exact-client delivery through the interface.
Staff-only publishing uses a guarded append-only decision over existing signed
evidence; it never enters the client package/delivery chain. Client publication
reuses the independent review/package/authorization/release/delivery gates.
Unsaved drafts, denied/stale/unavailable states, correction lineage, withdrawn
downloads, foreign/sibling/portal denials and corrupt retained bytes require tests.
Current-source retention must compare the user's loaded commit under the Git lock.

Reproductions, before implementation, in the existing Docker project:

- `RepositoryContentPanel.test.tsx` native client control case failed: no Publish
  document button (1.08 seconds).
- `test_native_internal_publication_has_no_legacy_document` retained evidence
  successfully, then received 404 rather than 201 for staff publication.

Run the strongest relevant adapted Make gates using existing services and
separate test databases. No parallel local stack or retained development database
mutation is authorized. Source reviews, API/schema checks, browser/server custody
and Wiki changes remain required; hosted upgrade/recovery applies to final source.


## Development behavior

Version remains 0.9.18 development. Staff publish/correct/withdraw decisions use
signed retained evidence plus new append-only event records (migration 0219).
They never grant client access. Client publication uses the existing independent
review, package, authorization, release and explicit delivery chain. The editor
protects unsaved content, preserves decision reasons after denial, and requires
an explicit retry after password confirmation. Workflow responses are checked
against the selected evidence and retained revision. Refresh clears replacement
confirmation so a changed active predecessor must be confirmed again.

The retained-PDF action is shared across these paths, while review PDFs remain
clearly separate. Client withdrawal/supersession revokes portal availability;
staff can still verify and download historical PDFs. No legacy Document is
created for a native publication. Primary-file controls and configuration remain
outside this slice.

## Validation record

Verified in the single existing Docker project, using generated test databases:

- The adapted `make test-content-authoring` module set passed 170 cases.
- New-route inventory/denial checks passed 13 cases.
- Staff lifecycle, empty-schema reversal/reapplication, populated-schema rollback
  refusal, recovery fingerprint and concurrent-correction checks passed five
  cases. Expanded MSP/client-Workspace sibling/portal/RLS checks passed two cases.
- Final serial frontend lint, all 817 unit/component tests, coverage thresholds,
  types and production bundle budgets passed after the refresh-confirmation fix.
  Coverage reports 78.19% statements, 73.63% branches, 72.65% functions and 85.04%
  lines. The regression first reproduced a checked replacement after predecessor
  A changed to B; it now requires explicit confirmation of B without losing the
  reason. No timeout or source assertion was weakened.
- The complete `make test-publication-browser-live` gate passed all twelve
  journeys without retries (3.9 minutes), followed by server custody, retained
  bytes, authority round-trip and artifact-hygiene verification. This includes
  newly created staff and client documents alongside the older preservation
  journeys.
- 160 tooling tests completed with three optional skips; Wiki validation passed.
- Both review axes reported zero findings, including the final correction-target
  and fixture-order deltas. Schema generation has zero errors and four existing
  operation-ID warnings. Generated frontend types include the new API contract.

The hosted encrypted-recovery fixture now creates native staff publication
history before repository snapshot baselines, then compares its restored signed
records, append-only events and PDF fingerprint. Its local head-independence
regression passed. Do not run the hosted isolated recovery stack locally: it
provisions separate services/volumes, outside the approved development setup.
Exact-source hosted upgrade and independent restore remain required after push.

### Unsuccessful local attempts retained

1. The first browser run invalidated its generated approver session by setting a
   password after session creation. The session probe confirmed invalidation.
2. The next run completed the new client lifecycle but exposed duplicate retained
   PDF controls. The duplicate product control was removed; assertions/selectors
   were not loosened. An older migrated save also failed while its Git write was
   still pending after 10.379 seconds amid background test work. Its latency
   cause remains unconfirmed; the unchanged case passed serially afterward.
3. All twelve browser journeys then passed serially in four minutes, with zero
   retries. Server custody correctly failed because that test password had been
   changed after the older fixture's member/password baseline. Password setup is
   now supplied during initial seeding, before both baseline and sessions. All
   existing preservation assertions remain unchanged. The final full browser/server
   gate passed with that corrected ordering (twelve cases, zero retries).

A navigation-prompt component check and an unrelated App help-route unit check
also each had a timing failure under overlapping validation. The unchanged
focused navigation replay and serial 817-case frontend gate passed; no timeout
or assertion was relaxed and no causal application fix is claimed for those
original timings. Candidate-relevant hosted completion remains mandatory.

No production access, deployment, document copying, retained-data mutation or
release/tag publication occurred. A read-only check confirmed migration 0219
has not been applied to the retained development database. Wiki changes remain
a local draft. Pre-existing planning edits remain outside the implementation.

## Hosted delivery follow-up

Initial source `20907c7f1b75f7c89e3bf2c56fd88681a84d8ae4` was pushed directly to
main. Build 41583571943 reproduced seven Ruff findings in the route file: one
import-order violation and six overlong new declarations. The earlier focused
local lint had omitted this file. Full Docker Ruff reproduced the same failure.
The correction sorts imports and wraps declarations without changing routes,
views, names or order; normalized Python syntax trees confirm this equivalence.
Full-repository Docker Ruff, mypy across 302 files and migration checks pass;
OpenAPI regeneration matches the tracked schema (zero errors, four existing
warnings). Both review axes report zero findings on this formatting-only delta.
Exact-source hosted runtime, upgrade and recovery must confirm the follow-up.

Initial hosted Build 41583571943 completed with all twenty PostgreSQL groups
passed and 89% combined coverage. Its live publication job stopped before browser
execution because readiness exceeded the unchanged 240-second controller budget;
the sanitized server report named the failure marker assertion at line 326.
The cause of that startup delay remains unresolved. An unchanged final-source
local replay became ready in 91.36 seconds, then passed all twelve browser cases
without retries and server custody/retained-byte/authority verification. No
readiness limit, selector, timeout or preservation assertion was weakened.
Initial Extended 41583578573 passed its browser matrix, performance, DAST and
independent recovery; recovery logs explicitly confirmed native staff lineage,
signatures and PDFs restored exactly. Its still-running upgrade job was cancelled
as superseded so final-source Extended could proceed, not recorded as a pass.

Build 41584099808 on formatting-corrected source `b8da6a49` passed source,
frontend, policy and nineteen PostgreSQL groups. Core-a-3 stopped before test
execution because the upstream Go proxy returned an HTTP/2 INTERNAL_ERROR while
fetching Mailpit's pinned SQLite dependency; no application fix is attributed to
retrying that transport failure. Its first live-workspace attempt failed at the
shared repository attachment assertion before publication acceptance: initial
repository listing and scanned upload were independently pending, so the broad
single-status query found both loading messages.

The exact multiple-status failure was reproduced locally with controlled pending
listing and upload promises before changing the journey. A positive component
regression verifies concurrent states, the unsaved attachment link while listing
remains pending, and the original single-status expectation after listing settles.
The shared browser journey now waits for the existing list-ready control and
verifies the exact attachment POST returns 201 before the original status/link
checks. It retains selectors, timeouts, retries and all saved/unsaved assertions.
This is test synchronization, not an upload performance improvement.

Final Docker frontend lint, 818 tests, coverage, types and production bundle
budgets passed. The complete twelve-journey browser/server gate then passed in
four minutes with zero retries, retained-byte/authority verification and artifact
hygiene. Both review axes reported zero findings on the final two-file delta.
The isolated full live-workspace stack remains hosted-only under the single-project
local rule; the shared repository helper ran through the existing-project gate.
