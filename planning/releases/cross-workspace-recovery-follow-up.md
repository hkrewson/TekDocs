# Cross-Workspace recovery baseline follow-up

Scope: repair the supported-recovery failure for the current Git-backed
cross-Workspace migration slice; record the immediate 1.0 work sequence and
the maintainer's post-1.0 interface priority. Version stays 0.9.18.

## Failed source evidence

Source `b8afcca644b0dc0b9da57589da5ed66837da56f0` passed
[Build 41479545080](https://github.com/hkrewson/TekDocs/actions/runs/41479545080)
and [CodeQL 41479558453](https://github.com/hkrewson/TekDocs/actions/runs/41479558453).
[Extended 41479563043](https://github.com/hkrewson/TekDocs/actions/runs/41479563043)
passed nine jobs including DAST, five browser configurations, performance and
supported upgrades, but its supported backup/restore job 125401376862 failed
at `cross_workspace_fixture.py`'s exact recovery fingerprint comparison.
The failure-summary job also failed because of that failure. Neither is a pass.

## Reproduction and diagnosis

In the existing `tekdocs` migrate service with test database
`td_ci_cross_workspace_all`, the initial regression
`test_cross_workspace_recovery_verifies_after_later_msp_fixture_writes`
failed at the same `recovery_verify` assertion after one unrelated authored
MSP document, without backup or restore. It failed twice (17.73s and 17.94s).
Temporary category-only instrumentation confirmed that only the Git accepted
heads changed; source IDs/blobs/bytes, retained publications/PDFs/files,
authority and pins all matched. The instrumentation was removed.

The standalone fixture recorded its fingerprint during initial creation. Later
recovery fixtures legitimately advance the same MSP repository before backup.
The fingerprint deliberately includes that repository's exact accepted commit,
so the original expectation described an earlier state than the backup.
This establishes a fixture-sequencing defect; it does not prove the restore
gate complete or excuse a failed candidate.

## Correction and checks

The rehearsal now uses `recovery_record` to capture the full existing fingerprint
after final source setup, immediately before the normal backup. The verifier
and its exact commit, source, pin, authority and custody comparisons are
unchanged. No schema, API, runtime authorization or retained artifact changes
are needed.

The regression at the existing fixture-mode boundary rejects the stale initial
baseline, records and verifies the final baseline, then rejects a real source
change made after that baseline. Both focused fixture cases passed in Docker
(35.27s). The combined cross-Workspace, repository recovery, encrypted-archive
and preflight suite passed all 121 cases (280.36s). Five restore-project checks,
143 tooling cases (three optional skips), Ruff, the standard mypy gate (300
source files), shell syntax, Wiki/product contracts and changed local links
passed. A native Gitleaks scan of 1,596 Git-visible working files found no
unignored findings; only existing exact ignore mount prefixes were adapted
for the native scan, with no new exceptions.
Both independent source-review axes found no remaining actionable issues.

Full independent encrypted restore provisions separate source/restore stacks;
the single-local-project rule leaves it to corrected-source hosted CI.
Local regression evidence does not establish independent restore success.

## Corrected-source hosted recovery

Runtime source `3e27577941b1b1f7ab6f883daf6e6680f929b969` passed the full
[supported recovery job](https://github.com/hkrewson/TekDocs/actions/runs/41499026415/job/125461412208)
on attempt 1, including encrypted recovery, repository-foundation acceptance
and recurring invoice history after restore. Downloaded artifact 13170302459,
`tekdocs-security-evidence-backup-and-restore-3e27577941b1b1f7ab6f883daf6e6680f929b969-1`,
contains `backup_and_restore`, `status: passed`, the exact source commit and
immutable identifier `41499026415:1:supported-recovery`. Its source/category/run
binding was checked directly. This closes the reproduced stale-baseline recovery
failure; overall CI and the original additional CI outcomes are separate.

Build 41499000231 attempt 1 passed 24 jobs, but core-a was cancelled at the
30-minute limit and the ninth live-browser journey still showed the Git-backed
loading state at its unchanged five-second assertion. Neither outcome is a pass.
The complete unchanged local browser replay passed all nine journeys (3.3m),
server custody/authority round-trip and artifact hygiene. Original slowdown and
loading causes remain unknown. Build attempt 2 repeated both outcomes on the
same source: core-a job 125482495552 was cancelled after passing progress through
40%, while live-browser job 125482492866 repeated the ninth-case loading failure.
The original timing causes remain unconfirmed; neither attempt is a pass.

The core-a assertion replay in the existing migrate service selected the same
38 modules and passed 537 tests with three optional runtime skips in 616.50s.
This reused the separate test database without provisioning a new environment;
coverage and provisioning were not identical to the hosted job, so it does not
reproduce or explain the 30-minute cancellation.

CodeQL 41499022087 and the complete Extended 41499026415 passed this exact
runtime source. Extended includes eleven successful jobs, all five browser
configurations, DAST, performance, supported upgrades, independent
encrypted recovery and commit-bound evidence. Its failure-triage job was
correctly skipped. The failed Build outcomes remain separately recorded.

## Bounded CI validation corrections

Current CI divides the original core-a module list into two disjoint groups,
`core-a-1` and `core-a-2`. Each selects nineteen complete modules. The legacy
aggregate selector remains available. The other groups, 30-minute job limit
and 80% combined coverage threshold are unchanged. Coverage requires both new
artifacts unless the complete legacy aggregate is supplied. New selection and
missing-artifact regressions failed before implementation; all ten plan tests
then passed. Actual Docker collection found 242 and 298 cases, preserving all
540 original cases by test function and parameter-case count; generated labels
are not stable across independent collection processes.

The browser correction was reproduced at the existing HTTP/UI boundary: hold
the real successful Git reply for six seconds without replacing its body.
The original test failed at the same 5000ms article assertion, showing the
loading state while `git_document_read` remained pending. Functional acceptance
now waits for the exact Workspace/content GET to return 200 and finish, then
checks the original content. The delay and loading-state check remain in the
cross-Workspace journey as a regression.

Timing distinction: the five-second DOM check starts after network completion.
The request uses Playwright's existing response-wait budget within the unchanged
120-second test / 900-second suite budgets. Effective navigation-to-content
allowance therefore changes. This is functional synchronization, not a
five-second end-to-end latency guarantee, a performance improvement, or a
diagnosis of the original hosted slowdown. The performance gates remain
unchanged and the original timing uncertainty remains in the failure ledger.

Failure-only diagnostics now include fixed document-list, document-read and
Git-read phases. A regression first demonstrated that those requests were
absent; all eight privacy cases now pass without retaining URLs, query values,
identities, headers or content. Resource probes found expensive repeated scoped
reads, but a stronger CPU constraint also broke unrelated earlier journeys and
was rejected as the original reproduction. No authorization/query or production
application code changed. Temporary CPU settings and development services were
restored, reusing the retained database volume.

The final standard Make browser/server gate passed all nine journeys (3.2m),
including delayed delivery, signed/file/PDF custody, authority rollback and
artifact hygiene. Lint, type checking, shell syntax and 145 tooling cases
(three optional skips) passed. Both source-review axes found no actionable code
findings and required the timing distinction above. Corrected-source hosted
Build, CodeQL and Extended validation remain required after push; local results
do not establish those future runs. Workflow lint remains a hosted Prepare
gate: the normal local target creates an extra tool container and no native
actionlint executable was available under the single-project constraint.

## Immediate scope and later product direction

The earlier [1.0 closeout plan](../1.0-closeout-plan.md) ordered a finite document
contract, required migration gaps and candidate acceptance. On November 2, 2026,
the maintainer explicitly superseded that migration scope with a clean Git-backed
start and manual document copying/recreation. All six automatic-migration gaps
are deferred optional work; Git-backed workflow, isolation, recovery and final
acceptance gates remain. No existing data may be deleted. The maintainer's
[post-1.0 interface brief](../post-1.0-interface-rework.md) prioritizes concise
copy, coherent forms/actions, simpler workflows/navigation and a distinct
TekDocs identity beyond inherited ITFlow patterns. Broad redesign follows 1.0;
current usability/accessibility defects remain acceptance work.
