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

## Immediate scope and later product direction

The [1.0 closeout plan](../1.0-closeout-plan.md) makes the remaining three
recommendations immediate work: freeze the finite document contract, complete
its required gaps, and finish candidate acceptance. Full completion of the
six currently recorded valid migration shapes remains an option; no silent
deferral is authorized by the plan. The maintainer's
[post-1.0 interface brief](../post-1.0-interface-rework.md) prioritizes concise
copy, coherent forms/actions, simpler workflows/navigation and a distinct
TekDocs identity beyond inherited ITFlow patterns. Broad redesign follows 1.0;
current usability/accessibility defects remain acceptance work.
