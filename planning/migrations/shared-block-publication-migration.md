# Shared-block publication migration

Bounded #105/#106 continuation after file-backed migration, authorized October
29, 2026. Commit and push directly to main after validation. No new version,
production deployment or public Wiki push is included.

Acceptance: migrate same-Workspace ordinary documents with owned fragments and
shared leaf references, both live and pinned. Preserve stable identities,
placement order, source ownership, exact pinned Git objects, signed publication
history, retained PDFs and previously supported owned files. Live edits propagate;
pinned references retain their selected content. Shared live dependency groups
must transition atomically, with explicit membership and scoped authorization.
Incomplete groups, stale/missing historical objects, foreign sources and unsafe
structural edits fail closed. Rollback projects supported Git text edits back to
their original owners, preserves pins and never changes signed artifacts.

The agreed testing boundaries follow the request: existing import/transition
operator services, publication/read/download HTTP routes, real browser workflow,
and supported recovery/upgrade verifiers. Use real PostgreSQL, Git and private
files in the existing local Compose services, with separate test databases.
Independent-stack gates run only in hosted CI. Reproduce failures before fixes.

Templates/enrollments, cross-Workspace reuse, dynamic keys/entity dependencies,
shared fragments containing files owned by another document, diagrams, client
delivery and structural editing remain excluded rather than flattened or lost.
The existing copy model permits one occurrence of each block per document;
repeated occurrences, including different pins of one block, remain explicitly
blocked as `unsupported_placement_graph`. Proof is never collapsed by UUID to
silently merge such occurrences.
Current supported bounds and file custody checks remain enforced.

Implementation must keep old signed formats verifiable without rewriting them.
A new shared-composition publication format may bind ordered live/pinned source
proof; it must have additive SQL guards, offline verification, negative tests and
normal reversible Django migration. Review and runtime evidence will be recorded
before delivery, distinguishing verified, inferred and blocked results.

## Implementation and review

The operator entry point is `transition_document_authority_group`: repeat
`--document` for each exact member, select Workspace/operator/target, review the
prepared checksum, then apply with that checksum. No authority controls were
added to the interface. Publishing, corrections, withdrawal, history and retained
downloads reuse the existing permission-checked interface and routes. The API
schema remains byte-identical at 0.9.16.

The group service locks scoped Documents and owned Blocks before discovering
live closure. All roots stage atomically on promotion. Rollback projects every
owner's Git edits before comparing composed consumers; failure of a later audit
write rolls back all revisions, authority changes and audits. v7 binds ordered
live/pinned proof and supported file custody; older signed formats are unchanged.
Migrations 0198-0200 add independent publication and legacy-writer guards, with
fixed definer search paths, revoked PUBLIC execution and no new runtime grants.

Two-axis source review used baseline `5ea7a4c`. Standards and Spec reviewers found
and subsequently cleared two P2 issues: missing root Document serialization in
the SQL authority trigger, and an upgrade fixture helper absent from 0.8.46.
Both were reproduced before fixes. The latter reproduction loaded the actual
pinned baseline publication module in the existing Docker runtime; full baseline
startup remains a hosted gate. No remaining actionable finding was reported.
No new dependency or authentication/signature algorithm was introduced.

Additional reproduced defects: a pinned legacy consumer could switch to LIVE
while its source was repository-authoritative (service and SQL now reject it),
and a v7 SQL insert could contain an inconsistent root title (now bound to indexed
title/path/digest). Negative tests retain those original boundaries. Fixture-only
corrections followed reproduced errors: ordinary PDF responses use `.content`;
withdrawal has no Workspace argument; a foreign tenant operator requires valid
staff membership and cannot resolve an installation reader; retained-history
inventory also requires source parity; idempotent history imports still require
a current preview. Assertions were not weakened to retire application failures.

## Validation boundary

Verified locally in the single existing `tekdocs` project, with separate test
records inside its PostgreSQL service:

- 21 focused shared migration cases pass on freshly migrated schema, including
  real two-connection serialization, denied operators, stale revision/file/history/
  membership previews, incomplete groups, pin-only outside consumers, exact PDF
  downloads with Git unavailable, failed rollback atomicity, command round-trip
  and reverse/reapply of 0198-0200 while retaining signed rows.
- Earlier broad regression passed 336 cases across content projection, authoring,
  migration, publication, files, runtime RLS, recovery and API contracts. Final
  source-specific regression and browser results are recorded below when complete.
- Restricted-role recovery fixture replay passed repeated verification, authority
  rollback/re-promotion, unchanged history/file hashes, missing ordinary-file and
  historical-primary detection, repair and subsequent verification.
- Frontend lint/types/API contract, 774 tests and production build/bundle limits
  passed. Backend Ruff, strict mypy (276 files), migration consistency and Bandit
  passed; Bandit reported no findings. API regeneration is byte-identical.
- Version, supply-chain pins, product boundary, Compose, UI language, responsive
  inventory/ledger and local Wiki checks pass. Tooling tests pass (121, 3 skipped).

The Wiki Documentation change is prepared in the existing dirty Wiki checkout;
unrelated maintainer edits are preserved. Wiki publication is outside this push.
Blocked locally by repository environment rules: aggregate migration release,
independent encrypted recovery, fresh/0.8.46 upgrade and production-image stacks.
Those exact hosted gates must pass before claiming their evidence. No production
inspection, deployment or live data migration was performed.

Risk disposition: this is bounded development at 0.9.16, not a new release.
Existing release-specific CSP/COEP/KaTeX acceptance is not renewed. Unsupported
shapes remain blockers; no signed artifact, source version or pin is discarded.
Inference: these focused results support the documented bounded workflow, not
completion of #105/#106 or general 1.0 acceptance.

The actual current upgrade-fixture create/identity/exercise replay passes with
legacy signed snapshots, live/pinned v7 corrections and collective rollback.
This is a logical fixture check on current schema, not a substitute for the
hosted 0.8.46 startup and fresh-versus-upgraded comparison. The stale retry
reproduction now asserts `preview_changed`, then requires `already_present` from
a newly prepared preview. The missing 0.8.46 helper fix retains signature and
all-artifact byte verification on the old side and full custody on the new side.

Real browser acceptance passed in Chromium (one journey, 24.3 seconds, no retry),
with server verification and browser artifact hygiene passed. It publishes v7,
downloads all retained file versions and the old PDF, edits both source fragments
through the real Git editor, observes live propagation and the unchanged pin,
checks the frozen first snapshot, records corrections/withdrawal, exercises denied
access and mobile layout, then verifies the three-document rollback/re-promotion
and all signed custody on the server. The value-free local reporter is
`artifacts/playwright-safe/publication-live.json` (ignored, not a publication).

A further public-authoring negative reproduced an owner-valid attachment link
being accepted into a shared LIVE block, outside the consumer's supported file
ownership boundary. The reversible-write guard now checks every current promoted
LIVE consumer in the exact scoped Workspace as well as the source owner. Pinned
consumers retain earlier bytes and are excluded. The test requires rejection
without advancing Git and successful rollback; the pinned case requires edit
acceptance and successful rollback. Both review axes cleared this correction.
The repeated-occurrence negative uses actual separate live and pinned placements
of one Block through the public import boundary, rather than duplicate test rows.

The final broader regression passed 345 cases before this additional write-guard
correction. The affected authoring/file/shared checks and final runtime results
below establish the correction's own validation boundary.

Final source checks: all 82 affected shared/file/authoring cases pass, including
the new file-link red/green and real repeated-occurrence refusal. The final
restricted-role recovery replay passes (97.68 seconds), including both fault/
repair cycles. The final real Chromium journey passes (23.9 seconds, no retry),
with server authority round-trip and retained custody verification plus artifact
hygiene passed. Ruff, strict mypy, migration consistency and Bandit pass again
with no Bandit findings. Hosted Build, CodeQL and Extended validation will bind
the committed source before hosted acceptance is recorded.

## Hosted rehearsal custody correction

Initial source `367ad68648f05a863cf05818cf87f9a17728c4b0` passed CodeQL run
`40981789373`. Extended run `40981792211`, attempt 1, passed browsers, DAST,
performance and independent encrypted recovery, but its dedicated document
upgrade job `123823345508` failed: upgraded identity verification could not read
a PDF created on 0.8.46. No aggregate upgrade acceptance is claimed for that run.
The dependent failure reporter correctly returned failure as well; both are
retained in `planning/releases/validation-failures.json`.

Diagnosis: the fixture used ephemeral `migrate` containers whose baseline and
current configurations omitted `/app/media`. Their database rows persisted while
PDF files remained in the removed container. A real existing-project Docker probe
reproduced file loss across recreation without a mount, then byte-exact retention
with the existing `tekdocs_media_data` volume attached. Only the owned synthetic
probe was written and removed; no development records were changed.

The rehearsal now applies a small Compose override to share existing `media_data`
with migration containers in baseline, upgrade and fresh phases. It adds no
service or data volume. Both baseline/current resolved configurations match the
backend media mapping; POSIX shell syntax and diff checks pass. Both review axes
cleared this harness-only correction. No signature, byte-preservation, identity,
rollback, recovery or application assertion was loosened. The dedicated extra-
stack rehearsal remains hosted-only under repository rules; corrected-source
hosted results will be recorded below.

## Verified hosted closeout — October 29, 2026

All three workflows report `completed/success` for exact source
`3495d96276ed6f94cb516565765435464476e34f`:

- [Build 40985517155](https://github.com/hkrewson/TekDocs/actions/runs/40985517155):
  full PostgreSQL matrix and combined coverage, constrained-role/RLS boundary,
  frontend gates, real migrated-publication browser journey, diagram exports,
  production-image rehearsal, SBOMs and vulnerability policy passed. Versioned
  image publication was skipped because 0.9.16 already exists; no application or
  receipt tag was created.
- [CodeQL 40985578137](https://github.com/hkrewson/TekDocs/actions/runs/40985578137):
  both language analyses and source-bound evidence delivery passed.
- [Extended 40985580577](https://github.com/hkrewson/TekDocs/actions/runs/40985580577):
  all five browser targets, performance, DAST, independent encrypted recovery,
  repository foundation, invoice restore, supported upgrades, dedicated signed
  shared-document migration, diagram-source upgrade and combined evidence passed.
  The failure reporter was skipped after success.

The corrected dedicated rehearsal explicitly reported fresh/0.8.46 acceptance.
It compares the same original Document/Block/pinned-revision identities, signed
publication signatures, manifest hashes and exact PDF hashes across the upgrade.
Both upgraded and fresh installations then copy shared documents, promote their
live group, edit the source, publish live/pinned v7 corrections and roll back
collectively. Live text updates, the original pinned text remains selected, and
original signed evidence is unchanged. Signature/artifact checks were retained;
the harness fix only persisted the media volume across migration containers.

GitHub lists unexpired source-bound upgrade artifact `12948344283`, backup/restore
artifact `12948166979` and combined upgrade/restore artifact `12948603194`, all
for `3495d96`, attempt 1. Browser and DAST evidence for the same source is also
uploaded. Original failed run `40981792211` remains recorded rather than being
relabeled as accepted. Original source `367ad68` separately passed Build
`40981767146` and CodeQL `40981789373`; its failed upgrade rehearsal is superseded
only by the corrected-source results above.

Verified: the bounded same-Workspace shared-leaf migration, preserved live/pinned
semantics, immutable signed publications/PDFs, collective rollback, SQL reverse/
reapply, and independent recovery/upgrade gates described here. Inferred: no
broader migration or 1.0 acceptance from those results. Blocked locally: aggregate
constituents requiring extra stacks under repository rules; their required hosted
counterparts are now successful. Missing pin history, repeated Block occurrences
and other unsupported shapes remain explicit blockers. No new version, production
inspection/deployment, live migration or public Wiki publication was performed.
The local Wiki draft and unrelated maintainer edits remain intact. Subsequent
closeout-only commits carry no new runtime claim.
