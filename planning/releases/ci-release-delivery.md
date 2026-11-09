# Single-push release delivery

## Scope and acceptance criteria

Requested October 22, 2026 after v0.9.11 published successfully but its updater
receipt was omitted until the operator reported the failure. The reproduced
failure and correction are in `0.9.11-production-guidance.md`.

A new version pushed to `main` must complete validation, tests, builds, scans,
publication, signed-image verification, application tagging and durable receipt
delivery in one workflow. No second source commit, manual tag push, receipt
writing, or operator reminder is part of the normal release path. Production
deployment remains separate. This slice changes delivery tooling, not application
behavior, database schema or API contracts.

The [branch and production state](branch-and-production-state.md) defines why
`main`, immutable release tags and the deployed production pointer are distinct.

## Release path

1. Prepare validates version agreement and supply-chain/workflow contracts.
   PRs, scheduled assurance and manual validation runs cannot publish. Ordinary
   main pushes run the light code lane. A main push whose `VERSION`
   already belongs to an earlier tagged commit validates without republishing;
   advance version metadata when preparing the next release. A retry of the
   original tagged SHA may finish delivery, but cannot overwrite different images.
2. The version-bump push promotes Build to full assurance: existing Build tests, PostgreSQL coverage, authorization, Chromium, diagram,
   production-image and Mailpit persistence checks run. The existing CodeQL and
   extended browser/performance/DAST/upgrade/recovery workflows are reusable,
   required release dependencies in the same run. The weekly Build schedule runs
   the same assurance scope without publication.
3. Build creates and scans the four images once and transfers those images to
   publication. Publication has no rebuild step. All required jobs must succeed.
4. Publication pushes commit-addressed images and signs provenance and SBOMs.
   The finalizer verifies each registry digest and all eight attestations against
   the exact source SHA, `refs/heads/main`, the Build workflow and hosted runners.
   Existing conflicting version aliases fail; registry/authentication failures
   are not treated as an absent alias. Version aliases are then published and
   checked against the verified digests.
5. CI requires a reviewed two-line message at
   `planning/releases/tag-messages/vVERSION.txt`: one concise summary followed by
   an explicit `Breaking changes:` disposition. It creates an annotated
   application tag from that committed text. CI generates the five-line receipt
   and a separate receipt commit whose sole
   parent is the application SHA and whose only change is that receipt. One
   atomic Git push creates `vVERSION` and `receipts/vVERSION`. Neither tag is
   force-updated. The source branch is untouched. Matching retries retain the
   original receipt commit; mismatches fail.
6. The run retains the receipt, verification outputs and release summary as an
   artifact. Git receipt tags persist independently of artifact expiry. Image
   evidence artifacts remain available for broader security review; green CI does
   not fabricate source-review findings or human risk acceptance.

## Operator release catalog

Future application tags are annotated from reviewed, repository-owned release
metadata. The annotation is deliberately short and factual: one summary line,
followed by `Breaking changes: none` or a concise operator action. Version
validation rejects a missing, malformed or unbounded message before release
work begins. The finalizer creates the tag object only after image and attestation
verification and delivers it atomically with the existing receipt tag.

Historical lightweight application tags remain valid and immutable. The updater
peels annotated tags to the application commit but never trusts annotation text
for receipt, image, ancestry or migration decisions. v0.9.19 remains a historical
lightweight tag because this catalog contract was added after that release; it is
not rewritten.

The Build workflow no longer triggers on tag pushes. GitHub also documents that
pushes made with its workflow token do not recursively start workflows:
[workflow triggering](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

Publication across GHCR and Git is not a distributed transaction. A failed run
can leave commit images or some aliases in GHCR; it must remain failed. The
application and receipt Git refs are delivered together only after image checks.
Retry failed jobs using the retained tested images. Do not overwrite an existing
version with rebuilt images; use a new version if their digests differ. Repository
rules must allow the publication job's workflow token to create these two tag
names. Rules are never bypassed automatically.

## Updater handoff

Install this updated tooling once. For future releases:

```bash
scripts/update-production.sh --check
scripts/update-production.sh --latest
scripts/update-production.sh --release vMAJOR.MINOR.PATCH
```

`--check` is read-only. `--latest` selects the newest stable application tag only
when the matching receipt tag also exists, then subjects that release to the same
receipt and image verification as an explicit `--release`. Use the explicit form
when an operator needs to pin or roll forward to a particular published version.
The updater prefers a historical checked-in
receipt when present. Otherwise it fetches the companion tag into `FETCH_HEAD`,
checks the receipt schema, sole parent and sole changed path, and loads its four
immutable images. This fetch changes neither branch nor working tree and needs
no GitHub CLI on production. Existing application-tag, revision, digest,
forward-upgrade, backup and running-container checks still apply. Trust is the
configured Git origin, as with historical checked-in receipts; the receipt Git
tag is not itself a cryptographic attestation.

Missing, malformed or inconsistent receipts stop before backup/migration.
A detached tooling checkout works with `--release`; upstream mode remains an
explicit legacy alternative. Never invent a receipt or disable verification.

## Authorization

An explicit authorization to push a versioned release to `main` covers this
pipeline's image publication, application/receipt tags and evidence delivery.
Do not ask again for those automatic stages of the same release. Required source
review and known-risk decisions belong before the release push. CI verifies
machine-checkable gates; it cannot invent an operator's risk acceptance or a
production deployment decision. A feature-branch push alone authorizes validation.

## Verification and limits

Verified locally: focused delivery/updater tests, real Git atomic delivery and
matching retry against a disposable local remote, and Docker-hosted actionlint.
The tests cover failed attestations, alias conflicts, registry errors, wrong
receipt parent, missing receipts, PR publication rejection and historical
three-image compatibility. `make test-release-delivery` passed 25 checks. The broader
`make test-automated-security-review-gate` passed 114 checks (3 optional live
checks skipped). Supply-chain pins, shell syntax and Wiki page/link checks passed.
No repository rulesets were returned by the read-only rules API; this does not
prove workflow-token permissions at publication time.
Registry and attestation calls in the finalizer tests are simulated; the existing
v0.9.11 real registry verification does not prove this new hosted pipeline ran.
Hosted execution and repository tag permissions must confirm the first new-version
main release. No production deployment or new image publication is claimed.

The public Wiki update is drafted separately; publishing it requires its existing
explicit authorization. The v0.9.11 full security/status record remains separate
outstanding work and is not marked complete by this delivery change.

## October 23 scanner follow-up

PR 111's CodeQL result flagged the updater fixture's directory-path variable
as clear-text secret storage and the Mailpit startup poll's empty exception
handler. Reproduction instantiated the fixture and confirmed `.env` contains
only an empty-directory path while generated recovery-key bytes remain in their
separate temporary file. The variable now describes the directory rather than
calling the path itself a secret. An isolated execution of the unchanged
readiness function with failing HTTP requests confirmed exactly 60 attempts
followed by RuntimeError. Comments now explain that intentional bounded retry.
No assertion, retry limit, scanner rule or alert was disabled. Local CodeQL CLI
is unavailable; hosted CodeQL must confirm these source clarifications.

## First hosted completion — 0.9.12

Build 40055908733 completed all required release jobs at b45a543 and delivered
four images, eight attestation verifications, v0.9.12 and receipts/v0.9.12.
See `0.9.12-operational-closeout.md`. This supersedes the pending first-hosted-run
limitation above. Production deployment remains separate.
