# Release operations: current status first

For release status, evidence closeout, CI failure triage or operator acceptance,
start here. Historical review narratives are supporting evidence, not the live
work queue. `.github/release-candidate.json` still names the historical 0.9.12
security/status packet. The latest exact-source publication record below names
the later release; the checkout's HEAD may be an evidence/tooling commit.

## Future release delivery

The [single-push delivery contract](ci-release-delivery.md) makes image verification,
application tagging and durable updater receipt delivery part of CI for new
versions on main. It replaces the manual tag/receipt handoff for future releases.
Existing release records below remain historical evidence.

## Published 0.9.16: bounded internal Git publication

The [0.9.16 publication closeout](0.9.16-operational-closeout.md) records successful
[Build 40637961760](https://github.com/hkrewson/TekDocs/actions/runs/40637961760)
at `0ebb981`, four images, eight attestation verifications and both application
and receipt tags. It retains the bootstrap correction and unchanged timeout
retry. The [candidate packet](0.9.16-candidate.md) contains release notes and the
maintainer's risk decision; the [source review](0.9.16-source-review.md) is separate.
Production remains on 0.9.15; Wiki publication and live migration remain separate.

The [publication interface slice](../migrations/git-publication-interface.md)
connects supported promoted documents to internal publishing, corrections,
withdrawal, retained history and PDF downloads. It adds Git-aware readiness and
browser coverage without changing the version or production authority.

The subsequent [publication-history migration slice](../migrations/publication-history-migration.md)
adds guarded import/promotion of intact internal history, legacy-to-Git
supersession and mixed-history rollback/re-promotion. Source `aa2cd43` passed [main CI](https://github.com/hkrewson/TekDocs/actions/runs/40460675424)
and [Extended validation](https://github.com/hkrewson/TekDocs/actions/runs/40460698493),
including independent encrypted recovery and supported upgrades. The linked
closeout distinguishes those results from aggregate release acceptance.
These earlier slice records precede the aggregate 0.9.16 publication above;
they do not claim a live migration.

The [CI follow-up](2026-10-26-publication-ci-follow-up.md) repairs synthetic-owner
MFA setup in recovery and resource-sensitive network property generation.
Original failed runs remain recorded; this is subsequent validation work.

The [internal publication lifecycle](../migrations/internal-git-publication-lifecycle.md)
adds signed current-Git snapshots and verified-v5-only rollback for an
already-promoted simple document. That preceding implementation kept legacy publication-history import/promotion
blocked; its hosted checks passed at `bef8c90`. The subsequent extension above
has its own validation boundary. The bounded work is now included in 0.9.16;
neither record establishes a production deployment.

## Publication-history diagnostic included in 0.9.16

The [read-only publication-history assessment](../migrations/publication-bearing-document-assessment.md)
adds value-minimized evidence to the existing staff migration-status route.
The diagnostic itself does not clear import/promotion blockers or implement
post-promotion publication parity. The subsequent slices and 0.9.16 release
above have their own evidence; no production migration is claimed.

## Prepared 0.9.15

The [0.9.15 candidate](0.9.15-candidate.md) packages the promoted-document reader
identity correction from `13c05fc`. The maintainer authorized preparation,
commit and a direct main release push. Candidate risk disposition and
preparation checks are recorded in the packet; publication must complete the
full single-push release pipeline. The pinned 0.9.12 manifest remains historical.

## Published 0.9.14; reader correction pending

PR #141 merged as `cc6a4c075eb0ffc69b1178c71046ad686314e6aa`.
[Build 40256015056](https://github.com/hkrewson/TekDocs/actions/runs/40256015056)
passed release CodeQL, extended validation and publication; application and
receipt tags were delivered. The [candidate packet](0.9.14-candidate.md) retains
the preparation context and subsequent production report.

The operator reported mostly successful production checks, but opening a
promoted guide from Documentation failed. The
[promoted-reader identity correction](../migrations/promoted-document-reader-identity.md)
is subsequent development, not part of the published images. Production
verification of that correction remains pending. The pinned manifest still
records historical 0.9.12 and must not be treated as later-candidate evidence.

## Published 0.9.13

[Build 40221980804](https://github.com/hkrewson/TekDocs/actions/runs/40221980804)
completed the required release jobs at `352abdc`, including CodeQL, extended
validation, production-image scans and publication. GitHub has both `v0.9.13`
and `receipts/v0.9.13`; see the [publication closeout](0.9.13-operational-closeout.md).
The [production follow-up](0.9.13-production-smoke-closeout.md) records the
operator's successful update and its evidence limits. The original
[candidate packet](0.9.13-candidate.md) retains its pre-publication review context.
The pinned 0.9.12 manifest is historical; no complete 0.9.13 security/status
manifest is claimed by this reconciliation.

## Published 0.9.12

The pinned manifest now identifies `b45a543`, published as v0.9.12 by
[Build 40055908733](https://github.com/hkrewson/TekDocs/actions/runs/40055908733).
All four images, eight signed provenance/SBOM verifications, application and
receipt tags were delivered by that single run. See
[publication closeout and update commands](0.9.12-operational-closeout.md).
The operator reported production document/asset checks on October 25; supplied
SVG and PDF exports also passed inspection. See the
[production follow-up](0.9.12-production-smoke-closeout.md) for evidence limits. The historical 0.9.11 and 0.9.9
records below do not describe the current release.

## Historical 0.9.11 publication

[Security maintenance](0.9.11-candidate.md) updates Node and rebuilds Mailpit
with a fixed Go toolchain. v0.9.10 was tagged but its Mailpit scan failed and
publication was skipped. The v0.9.11 publication succeeded; all four image
aliases and eight signed provenance/SBOM checks passed. The reviewed receipt and
[production update commands](0.9.11-production-guidance.md) are available.
Its standalone full publication-record assembly was superseded by the current
0.9.12 record. Retained 0.9.11 evidence remains historical.

## Published 0.9.9

The historical 0.9.9 candidate was f52b210. All three image
aliases and signed provenance/SBOMs were verified; all security and diagram
categories assembled. See [publication closeout](0.9.9-publication-security-closeout.md),
[operational validation](0.9.9-operational-closeout.md), and the
[accepted security decision packet](0.9.9-security-decision-packet.md).
Production deployment remains an operator action; use the
[update instructions](0.9.9-production-update.md).

The following 0.9.8 records describe the preceding production release and its
historical manifest; they do not replace the current 0.9.9 manifest.

## Released 0.9.8 access-fix candidate

Start with [0.9.8 operational closeout](0.9.8-operational-closeout.md) for the
current 05abb13 hosted results, later rehearsal fixes, accepted header risks and
remaining publication decisions. [Access candidate validation](0.9.8-access-candidate-validation.md)
retains the earlier access/compression and browser chronology.
The historical 0.9.8 candidate was 05abb13. All three image aliases
and signed provenance/SBOMs were verified; see the publication security closeout.
The operator completed production deployment and reported successful document/asset
smoke checks; see [production closeout](0.9.8-production-update.md). The reviewed Wiki is now published and its public pages verified; see
[Wiki review and publication](0.9.8-wiki-review.md). Application Wiki-link enablement
and authority handoff remain separate decisions.

## Status and evidence

1. Run `make release-status`. This performs read-only GitHub checks for the
   pinned workflow identities, checks their repository/workflow/commit and successful conclusion,
   validates the security record and expiry dates, and hashes local source reports.
   Hosted run identifiers must match the run attempt and evidence category.
   Production-image digests are compared with the exact run/attempt's downloaded
   evidence artifact; a missing, expired or mismatched artifact blocks verification.
   For single-push releases, all three identities name the same main-push run;
   successful CodeQL, extended and publication jobs are required explicitly.
   Offline `python3 scripts/release_status.py` deliberately reports hosted checks
   unverified and returns nonzero. An unavailable API is not a cached pass.
2. Read `blockers` and `remaining_release_actions` separately. Zero verification
   blockers does not mean tagged, deployed, or independently audited. Operator
   acceptance records the decision, not individual unperformed manual tests.
3. Freeze the tested application SHA. Record evidence in a later documentation
   commit without relabeling it as evidence for HEAD. For the current pipeline, authorize the versioned main push; CI tags its
   successfully tested SHA and delivers the receipt. Historical manual tagging
   is not the normal release path. Runtime changes require a new candidate and fresh
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
