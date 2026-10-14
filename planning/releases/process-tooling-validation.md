# Release process tooling validation — October 14, 2026

These are follow-up engineering checks, not new 0.9.8 acceptance requirements.
The frozen application candidate remains `da198027dbfce44f926ffafd518387a84e587431`.
The operator's acceptance decision is unchanged; unperformed manual checks remain
unverified.

## Verified locally

- All 76 script tests passed, including altered/missing evidence, mismatched
  workflow identity, offline status, unsafe acceptance state, failure ownership,
  generated loopback bindings, shared file storage and network isolation.
- Ruff, pinned Actionlint, whitespace checks and a redacted Gitleaks scan of the
  affected tooling/evidence directories passed.
- Read-only online release status verified all three pinned hosted runs and the
  local security-report hashes with no verification blockers. This does not
  independently authenticate downloaded hosted artifact contents.
- The shared Linux recovery preflight passed using an unrelated service UID.
- A disposable source-build acceptance installation on loopback port 3310 passed
  technical checks for three synthetic workspaces, 30-record collections,
  Git-only documents, retained files/checksums, restricted accounts and prepared
  publication evidence. No production or existing local installation was seeded.
- Stopping only that installation's frontend invalidated readiness. Restarting
  it and rerunning the read-only check restored readiness without reseeding.

## Defects found while validating the preparation tool

The first trials exposed an incorrect frontend host binding and missing shared
file-storage mounts in the fixture container. These were corrected, with
regression checks added. The readiness checker also incorrectly rejected the
renderer's fully disabled network; it now accepts the Docker null network while
continuing to reject ordinary external bridge access.

Two incomplete disposable projects were stopped; their private diagnostics and
volumes remain recoverable. The successful project's private walkthrough and
credentials remain under ignored `artifacts/acceptance-tooling-final/`. Do not
commit or upload these files. Recheck readiness before any future operator use.

## Boundaries

No application runtime changes, tag, deployment, Wiki publication, scanner alert
dismissal or authority handoff were performed. The new hosted failure-summary
job was linted, not exercised by deliberately failing a hosted run. Existing
security exceptions retain their recorded scope and deadlines. Full recovery
rehearsals were not rerun for this additive preflight change.

## Review follow-up — October 14

The four review findings have focused regressions and corrections:

- The inherited-environment regression failed before the correction. Child
  processes now use a controlled environment, and resolved Compose configuration
  is validated before startup or seeding. Conflicting exported port/password/profile
  values no longer override disposable settings. Negative tests reject exposed
  ports, external backend networks and foreign named volumes.
- Three malformed hosted evidence identifiers previously returned no blockers.
  They now fail verification for incorrect run, attempt or category. Production
  image digest identifiers are compared against the exact run/attempt's retained
  evidence artifact, with mismatched or expired artifacts rejected. The actual
  pinned candidate still passes online verification.
- The prior verifier accepted a simulated withdrawn publication. Current checks
  invoke the read-only portal handlers for the fixture client and verify current
  PDF/attachment/primary-version downloads. Live probes reject withdrawn state
  and unavailable storage using in-process mocks; they do not withdraw real
  records, delete files, create login sessions or alter production.
- Failure-summary dependencies now cover all other Extended validation jobs,
  including both evidence-only jobs. The regression failed on the prior dependency
  list and passes on the corrected list. No hosted failure was deliberately induced.

All 85 script tests passed with the optional live probes enabled against the
prepared disposable installation. Ruff, pinned Actionlint, whitespace checks and
the redacted scoped secret scan passed. No operator acceptance was repeated or
inferred from these engineering checks. These changes remain local and uncommitted.

A fresh preparation at `artifacts/acceptance-review-fixes/` completed successfully
on loopback port 3312 while conflicting shell port/password/profile values were
exported. The complete 85-test suite then passed again against this fresh stack,
including the live negative probes and final normal readiness check. Its private
credentials and walkthrough remain ignored; no additional operator review is required.
