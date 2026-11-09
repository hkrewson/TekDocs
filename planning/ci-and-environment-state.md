# CI lanes and environment state

Status: adopted development and release contract, November 4, 2026.

## Git state authority

`main` is the development authority. It contains reviewed work that is expected
to pass the light code lane on every push and the full weekly assurance workflow,
but it may be ahead of
the release installed in production. Feature work uses short-lived branches and
pull requests; superseded pull-request validation may be cancelled.

Production has no mutable Git branch. Its source identity is the immutable
application tag `vX.Y.Z`, companion receipt tag `receipts/vX.Y.Z`, reviewed image
digests and the matching `TEKDOCS_DEPLOYED_COMMIT` recorded only after the updater
verifies readiness. The operator tooling checkout may remain on an older commit
and is not evidence of the running application version.

A frozen candidate is a `main` commit whose `VERSION` does not yet have a
conflicting application tag. Its trusted push runs full integration, CodeQL and
extended validation before CI may publish images and atomically deliver the
application and receipt tags. Deployment of that release remains a separate,
explicitly authorized production operation.

## Validation lanes

| Lane | Trigger | Required work |
| --- | --- | --- |
| Documentation policy | A change only to Markdown, `docs/` or `planning/` | Version, workflow policy, Wiki/product contracts and other non-runtime repository checks. No database, browser or production-image jobs. |
| Code validation | A code/configuration pull request or ordinary push to `main` | Policy, backend static/API checks, frontend tests/build and dependency/license/secret review. Superseded pull-request runs are cancelled; main runs are not. |
| Full assurance | Weekly Build schedule or manual Build run | Code checks plus runtime/RLS, PostgreSQL shards and coverage, Chromium, live browser journeys, diagram exports, production-image scans, CodeQL, browser matrix, DAST, performance, supported upgrades and independent recovery. |
| Release acceptance | An unpublished version on trusted `main` | Full assurance plus verified image publication, attestations and atomic application/receipt tags. |

Manual CodeQL or Extended runs are for investigation of a specific failure.
Routine weekly and release assurance call them from Build so all evidence remains
bound to one exact source commit. Failed jobs are diagnosed before a bounded
rerun; unrelated passing workflows are not restarted by habit.

Every Build lane ends in the stable `Validation passed` check. It accepts only
the intentional skips for the selected lane and fails on a failed, cancelled or
unexpectedly skipped required job. Protect `main` with this check rather than a
lane-specific job name.

The weekly Build runs full assurance even when the source commit is unchanged so
updated CodeQL queries, browser engines and vulnerability intelligence are not
missed. Reusable CodeQL and Extended workflows no longer have independent
schedules; manual and release-called executions always run their complete scope.

## Automated security disposition

CodeQL findings are alerts, not dependency pull requests. Automation may label,
prioritize and block a release on them, but it must not dismiss or accept risk.
A false-positive or accepted-risk disposition requires a documented maintainer
decision.

Dependabot may propose grouped updates. Initially, every dependency pull request
requires maintainer review; passing checks are necessary but not approval. After
`main` has required checks and the merge policy has operated reliably, a narrow
auto-merge class may be considered for development-only patch updates. Runtime
dependencies, container bases, GitHub Actions, authentication, cryptography,
database drivers, browser/rendering stacks, major updates and security fixes
remain review-required. High urgency changes priority, not the acceptance bar.

## Promotion rules

1. Develop on a short-lived branch and use pull-request validation for feedback.
2. Merge one coherent slice to `main`; the non-cancelable light code run is the
   immediate development result, and weekly assurance supplies the broad runtime result.
3. Keep `VERSION` on the current published checkpoint during ordinary
   development. Change it only when intentionally freezing the next candidate.
4. Treat release and receipt tags as immutable. Never force-update them or use a
   branch name as a substitute for receipt/image verification.
5. Update production only through the reviewed release selector. Confirm the
   deployed commit and image labels rather than using `git describe` on the
   operator tooling checkout.
