# Release operations: current status first

For release status, evidence closeout, CI failure triage or operator acceptance,
start here. Historical review narratives are supporting evidence, not the live
work queue. `.github/release-candidate.json` names the application candidate;
the checkout's HEAD may be a later evidence/tooling commit.

## 0.9.9 preparation

The next candidate enables published Wiki guides and corrects initial keyboard
focus in overlays. See [0.9.9 candidate](0.9.9-candidate.md) for scope and current
validation. The pinned manifest below still identifies released 0.9.8; its green
status does not validate 0.9.9. New commit-bound runs and fresh security decisions
are required before replacing that evidence record.

## Released 0.9.8 access-fix candidate

Start with [0.9.8 operational closeout](0.9.8-operational-closeout.md) for the
current 05abb13 hosted results, later rehearsal fixes, accepted header risks and
remaining publication decisions. [Access candidate validation](0.9.8-access-candidate-validation.md)
retains the earlier access/compression and browser chronology.
The pinned manifest now names 05abb13, published as v0.9.8. All three image aliases
and signed provenance/SBOMs were verified; see the publication security closeout.
The operator completed production deployment and reported successful document/asset
smoke checks; see [production closeout](0.9.8-production-update.md). The reviewed Wiki is now published and its public pages verified; see
[Wiki review and publication](0.9.8-wiki-review.md). Application Wiki-link enablement
and authority handoff remain separate decisions.

## Status and evidence

1. Run `make release-status`. This performs read-only GitHub checks for the three
   pinned runs, checks their repository/workflow/commit and successful conclusion,
   validates the security record and expiry dates, and hashes local source reports.
   Hosted run identifiers must match the run attempt and evidence category.
   Production-image digests are compared with the exact run/attempt's downloaded
   evidence artifact; a missing, expired or mismatched artifact blocks verification.
   Offline `python3 scripts/release_status.py` deliberately reports hosted checks
   unverified and returns nonzero. An unavailable API is not a cached pass.
2. Read `blockers` and `remaining_release_actions` separately. Zero verification
   blockers does not mean tagged, deployed, or independently audited. Operator
   acceptance records the decision, not individual unperformed manual tests.
3. Freeze the tested application SHA. Record evidence in a later documentation
   commit without relabeling it as evidence for HEAD. Tag the tested SHA only
   after explicit approval. Runtime changes require a new candidate and fresh
   complete validation; documentation alone does not manufacture a new tested SHA.

The historical `.github/automated-security-review.json` remains a template. Use
the manifest's `security_record`, not that placeholder, for the current candidate.
The existing strict validator and ten-category assembler remain authoritative
for record structure. The status verifier adds reference checks; it does not
prove the reviewer was correct or independently authenticate every hosted artifact.
Production-image evidence is downloaded for identity comparison. A dependency scan
retained from an earlier partial-run attempt additionally requires its exact-source
successful job and original artifact bytes. Other hosted categories verify
run/attempt/category identity, not artifact bytes.
Review dispositions and broader artifact provenance
remain review work, not assertions inferred from green workflow execution.

## Local release-gate composition

`make release-gate` runs current-destination validation, including the supported
minor-version upgrade matrix, file/diagram upgrade, supported encrypted recovery,
repository-foundation acceptance and recurring-invoice restore. Existing current
feature rehearsals, security, browser, production-image and clean-install checks
remain part of the aggregate.

Seven historical checkpoint targets remain available separately, with their
original destination guards. They are excluded from the current aggregate:

| Historical target prefix | Required destination |
| --- | --- |
| `client-portal` | 0.5.2 |
| `outbox` | 0.5.4 |
| `notification` | 0.5.7 |
| `publication-control` | 0.5.1 |
| `key-publication` | 0.9.0 |
| `placement-audience` | 0.9.0 |
| `monitoring` | 0.7.13 |

Each is still invoked as `make <prefix>-upgrade-rehearsal` at its appropriate
historical checkout. Their precise historical fixtures are not claimed as current
migration coverage. Current support is defined by the retained supported matrix
and current feature rehearsals, plus PostgreSQL migration and isolation tests.
The aggregate's command-plan regression rejects reintroducing these incompatible
targets and requires the current upgrade/recovery boundaries.

A passing command plan proves composition, not runtime success. Record actual
Docker gate outcomes separately. Publication attestations and security-risk
acceptance remain independent release requirements.

## Failed validation

Run `python3 scripts/ci_status.py --run-id RUN_ID` for a compact read-only summary.
Fetch logs only for named failed jobs. Extended validation adds a failure-summary
job assigning follow-up to the maintainer for manual and scheduled failures,
including browser and diagram evidence generation/upload failures.

Track each failed run/job in `validation-failures.json` with `run_id`, `job`,
`owner`, `reproduction`, `cause` (explicitly `unknown` until established),
`next_action`, then `fix_commit` and `retest_run`. A tracked failure remains a
failure. Reproduce with the smallest existing gate before editing; retain useful
unfinished runs, run focused retests, then complete final candidate validation.
The workflow summary is not an issue notification service or a substitute for
the maintainer attending to scheduled failures.

Both recovery rehearsals call the same Linux bind-mount/free-space preflight
before provisioning. It tests an unrelated service UID reading one read-only
synthetic key beneath a private host directory, plus a 2 GiB minimum of Docker
filesystem space. This catches basic custody/capacity failures; it does not
estimate the full rehearsal's peak space or prune anything.

## Wiki publication

See [Wiki publication contract](wiki-publication.md) for the current draft,
validation and approval workflow. Local page/link validation does not publish the
Wiki or enable application links.

## Operator acceptance

Prepare a new disposable installation, using unused loopback ports:

```sh
python3 scripts/operator_acceptance.py prepare --directory artifacts/acceptance-next --port 3308 --mail-port 8108
python3 scripts/operator_acceptance.py check --directory artifacts/acceptance-next
```

Preparation builds current clean runtime source, creates a randomly named Compose
project and new volumes, and refuses an existing destination. It never chooses
the production or ordinary local project and never deletes existing data.
Backend networks are internal-only, frontend/Mailpit ports are loopback-only,
and workers/scheduler stay stopped. Local fixture actors use synthetic data;
owner MFA enrollment stays a normal human step. This is source-build acceptance,
not verification of registry-published images or real provider integrations.

Application and Compose overrides from the invoking shell are discarded. The
resolved project, ports, backend networks and named volumes are checked before
any service starts; Docker connection settings remain available to its CLI.

Setup and the read-only application verifier are separate. A successful check
generates `walkthrough.md` beside a private `access.txt`; never commit or upload
the acceptance directory. Readiness checks must pass immediately before handing
the guide to the operator. Failures leave the stack for diagnosis, not marked
ready; private command diagnostics must not be pasted into CI or chat. Check
does not reseed or repair application data. Changes made by the operator may
require engineering to revise the fixed-count fixture expectations.
Publication readiness invokes the current client portal read handlers and policy
checks for the fixture client, PDF, attachments and both retained primary-file
versions. Historical preparation response codes are not reused as readiness.
This does not exercise browser authentication/MFA; those remain human steps.

To rerun the opt-in live regression probes against a prepared disposable project:

```sh
TEKDOCS_ACCEPTANCE_TEST_DIRECTORY=artifacts/acceptance-next python3 -m unittest scripts/tests/test_acceptance_live.py -v
```

These simulate unavailable publication state/storage in-process without changing
the database or deleting files, then check that normal readiness still succeeds.

Use the named records and exact controls in that guide. Missing fixture,
environment, account or route is engineering work. Phone access, screen-reader
sessions, imported-provider provenance and outages require separate preparation.
Reviewers should reject a handoff whose guide has not been exercised against the
named environment. Record Pass/Fail/Blocked/Not run separately from the operator's
release decision. Keep credentials out of all acceptance records.

These process improvements are follow-up tooling, not new 0.9.8 acceptance gates.
