# CI remediation after the read-only preview correction

Date: 2026-10-21. Scope: restore CI for `a4918b2` while retaining the issue #105
read-only migration preview correction. Acceptance: reproduce the two failed
checks, update only affected dependencies and the demonstrated test ordering,
retain permission/dirty-draft assertions, and record exact validation limits.
The published manifest remains pinned to v0.9.9/f52b210.

## Verified failures and reproductions

- [Build 39545208620](https://github.com/hkrewson/TekDocs/actions/runs/39545208620):
  only dependency policy failed. Docker `pip-audit` reproduced nine findings in
  Certifi 2026.7.22 and Pillow 12.3.0. All hosted PostgreSQL shards, runtime/RLS,
  backend static checks, frontend checks, Chromium and live-browser regression
  passed on a4918b2; image checks were skipped. CodeQL 39545208619 passed.
- [Performance diagnostics 39545208607](https://github.com/hkrewson/TekDocs/actions/runs/39545208607):
  the prerequisite frontend suite failed at Stock's off-page deep-link test,
  which requested Edit immediately after the record title appeared. Performance
  measurement never started; absent performance artifacts are consequential.
  The unchanged focused suite passed locally (5 tests). Delaying the list's
  permission response by 200 ms reproduced the exact missing Edit failure
  (1 failed, 4 passed), before correcting the assertion synchronization.

## Changes

The Python 3.13 pip-compile refresh changes only Certifi to 2026.10.19 and Pillow
to 13.0.0 in runtime and development locks, retaining hashes and all other package
versions. These are existing transitive dependencies, not new integrations.
Reviewed [Pillow 13 release notes](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html):
Python 3.13 remains supported; TekDocs has no direct use of removed Pillow APIs.
PDF rendering through ReportLab receives focused runtime coverage below.

The Stock test now controls a pending list response. It checks that Edit is
absent before management permission arrives, resolves the authorized result,
waits for Edit, then retains the original unfinished-edit protection assertions.
No application permission logic or timeout is relaxed. Existing denied-management
coverage is retained. No schema, migration or HTTP/OpenAPI changes are needed.
No public Wiki workflow changes: this is dependency and internal test maintenance.

## Validation

- Docker original audit reproduction: nine findings in two packages.
- Docker refreshed runtime and development audits: no known vulnerabilities;
  TekDocs itself is unavailable on PyPI, as expected. `pip check` passes.
- Docker rendering/PDF tests: 29 passed, two database-dependent cases deselected.
- Docker Bandit: zero findings.
- Focused Stock suite after deterministic synchronization: 5 passed.
- Full final `make check-frontend`: passed, including 772 tests in 168.30
  seconds, API consistency, lint, types, production build and bundle budgets.
  The first run exposed a require-await lint error in the new test callback;
  explicitly awaiting the controlled response corrected it without suppression.
- Clean production dependency installation with hashes, production license policy
  and CA-store loading passed (120 CA certificates).

Local logs are `/tmp/tekdocs-ci-audit-repro.log`,
`/tmp/tekdocs-stock-delayed-repro.log`, `/tmp/tekdocs-stock-fixed.log`,
`/tmp/tekdocs-ci-python-retest.log`, `/tmp/tekdocs-ci-dev-audit.log`,
`/tmp/tekdocs-ci-production-deps.log`, `/tmp/tekdocs-ci-frontend-gate.log`,
`/tmp/tekdocs-ci-frontend-final.log` and `/tmp/tekdocs-ci-frontend-verify.log`.

## Limits and next gate

Docker storage exhaustion interrupted development-lock generation. It was rerun
using a task-specific host temporary directory, without pruning existing stacks.
The initial license command used the development environment and rejected four
development-only packages for missing declarations; this was an incorrect target
for the production license checker, not grounds to weaken its policy.

A full local `make security` image rebuild and `make test-public-beta-performance`
are not certified by these focused results. Docker storage exhaustion remains a
constraint on fresh image/stack provisioning. The corrected commit passed hosted Build (including image scans), CodeQL and
performance diagnostics as recorded below. A release candidate still needs
Extended validation and current security disposition. The maintainer authorized
the push and hosted runs; no image publication or deployment occurred.


## Hosted closeout — 2026-10-21

Verified through the GitHub run/job API: all three manually dispatched runs used
exact source `9c7e9046469cc86346c7663e2ac7ad3634fad620`, attempt 1, and concluded
success:

| Workflow | Run | Result |
| --- | --- | --- |
| Build, test, and secure | [39548663486](https://github.com/hkrewson/TekDocs/actions/runs/39548663486) | All validation jobs passed, including dependency policy, PostgreSQL shards/coverage, browser journeys, production containers, SBOMs and vulnerability scans. Publication was skipped as expected. |
| CodeQL | [39548665549](https://github.com/hkrewson/TekDocs/actions/runs/39548665549) | Both language analyses and evidence job passed. |
| Performance diagnostics | [39548667639](https://github.com/hkrewson/TekDocs/actions/runs/39548667639) | Constrained browser performance diagnostics passed. |

This closes the two CI failures on a4918b2. It does not certify Extended
validation, publication provenance, or deployment of the preview fix. The live
release manifest remains v0.9.9/f52b210; the next runtime candidate requires its
own release evidence and bounded security decisions. Artifact contents were not
independently re-audited during this status check.
