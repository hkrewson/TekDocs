# Reversible first-document handoff implementation

October 25, 2026. Scope: #105 / #106 and proposed ADR 0115.
Unreleased implementation; verification status is recorded below. This is not authorization to mutate production.

## Existing behavior to preserve and gap to reproduce

`test_repository_authority_allows_git_edits_for_a_migrated_document` already
exercises copy, promotion, retained files, fragment-body editing and reverse
projection into a new legacy revision. Its final section permits a root body /
metadata edit, then explicitly proves rollback is blocked. That is the unsafe
edit shape this slice must prevent before Git acceptance. Preserve equivalent
native-Git metadata/search coverage when changing that migrated-document case.

Run this existing case unchanged in disposable PostgreSQL before changing the
guard; then add rejection assertions that fail on the current implementation.
Do not infer a runtime reproduction solely from source inspection.

## Planned enforcement boundary (implemented below)

- Share one snapshot-based shape validator between rollback and accepted-write
  validation, so the allowed-write promise cannot drift from reverse projection.
- Enforce in `commit_repository_files` before `git.write_commit`, under the same
  repository lock and accepted-base check as the write. An HTTP-only check leaves
  operator/import/service writes able to invalidate rollback.
- Determine migrated ownership from exact tenant, workspace, legacy document /
  block ownership and authority state. A repository authority row alone also
  describes native Git content and must not activate migration restrictions.
- Permit owned fragment Markdown changes; reject root identity/body/metadata,
  fragment metadata, moves, deletes and include/placement changes outside the
  proven reverse projection. Denials must leave Git refs, accepted/indexed
  commits and legacy revisions unchanged and provide an actionable explanation.
- Do not call `prepare_rollback_markdown_projection` directly from the locked
  writer. It reads accepted files through a second repository lock. The export
  builder can also read retained snapshots for cross-document references. Supply
  already locked snapshot data through an explicit boundary instead of acquiring
  nested locks or bypassing the repository's serialization.
- Validate authority-transition/write races. The original transition locked the
  workspace and repository rows before reading Git; the writer takes the Git
  lock before the repository row. Establish and test a consistent lock order
  before extending the shared path. No concurrency correctness is claimed yet.
- Translate the shared denial into the normal authoring API error boundary.
  Do not expose content bytes or identifiers in diagnostics.

## Required verification

1. Existing migrated-document case unchanged, then failing guard regressions.
2. Allowed owned-body edit and repeated edit/rollback, retaining revisions/files.
3. Denied root/body/title/properties, fragment metadata, move/delete and include
   changes through both HTTP authoring and low-level accepted-write paths.
4. Native Git and unrelated-workspace edits stay available; cross-tenant/client
   access still fails under the constrained runtime role.
5. Stale base, concurrent transition/write and interrupted indexing leave a
   recoverable, explicitly reported state.
6. Combined copy → promote → allowed edit → reverse projection → isolated
   encrypted recovery rehearsal, followed by the current migration release gate.

## Implementation and local evidence

- `document_reversible_writes.py` contains the snapshot-only comparison shared
  by rollback and the accepted-write guard. The writer supplies its locked Git
  reader; the guard does not acquire a second Git lock or trust an indexed head.
- Protection selects promoted documents with matching legacy owners in the exact
  tenant/Workspace and their owned blocks. Native Git files remain editable,
  including while a migrated document is present in the same repository.
- Root/fragment structural edits, moves, deletion and duplicate identities are
  rejected before Git advancement. API responses use the existing 400/detail
  boundary; there is no new API payload or database migration.
- Authority transitions pin Git before locking the repository/owner rows, using
  the writer's lock order. The regression checks writer refusal while the shared
  transition pin is held. This is a deterministic lock exclusion check, not a
  claim of exhaustive multi-process race testing.
- Historical drift remains a rollback blocker. The pre-existing corruption test
  deliberately bypasses the new guard to simulate an already-accepted old
  snapshot; normal write-rejection assertions run independently beforehand.
- The supported encrypted recovery fixture now copies, promotes, edits an owned
  fragment, rejects a root metadata change, reverses into a retained legacy
  revision, and promotes again before backup. Verification repeats reversal
  after recovery and checks the edited text.

Approved cleanup removed unused build cache and 29 unused old rehearsal images;
Docker had 6.2 GB available afterward. Containers and data volumes were preserved.
The unchanged baseline passed 28 migration/runtime-RLS tests in 86.96 seconds.

Reproduction before runtime changes: the new root-title rejection assertion
failed with `DID NOT RAISE RepositoryInputError` in disposable PostgreSQL
(1 failed in 61.35 seconds). After implementation, the expanded focused case
passed in 67.55 seconds. Logs: `/tmp/tekdocs-handoff-guard-before.log` and
`/tmp/tekdocs-handoff-guard-after.log`. Full backend Ruff and mypy passed (270
source files). Broader suite, recovery and aggregate gate results follow below.

No runtime release has been selected, published or deployed. VERSION remains at
the existing checkpoint while this implementation is reviewed; a new version
and candidate-specific release decisions are required before runtime publication.
ADR 0115 keeps the first-operator migration procedure internal, so no public Wiki
workflow is added. Templates, publication-history parity, other migration
eligibility blockers and existing historical corruption are not waived.

## Verified follow-up

- The isolated combined migration/RLS/authoring/repository/recovery selection
  passed 109 tests in 162.85 seconds. Log: `/tmp/tekdocs-handoff-full.log`.
- `make supported-recovery-rehearsal` passed with the expanded authority fixture:
  edited fragment text survived backup, network-isolated restore and rollback.
  Existing corrupt-file, historical-primary, publication, wrong-key, write-failure
  and accepted-head-mismatch refusals also passed. Log:
  `/tmp/tekdocs-handoff-recovery.log`.
- The first aggregate run passed frontend (772 tests), backend static checks,
  schema/API drift checks and the content-authoring selection (158 tests). The
  migration selection exposed an incorrect new test assumption: it expected
  the low-level Git service to enforce organization authorization, and used a
  stale base after repository initialization. Its observed failure was
  `Repository base changed`, not the asserted `unavailable`. The Git service
  relies on caller policy authorization; organization-scoped content is covered
  by the existing constrained-role suite. Removed that invalid low-level
  authorization assertion, retained sibling-workspace native authoring and all
  structural denials. No runtime behavior was relaxed to satisfy it. Log:
  `/tmp/tekdocs-handoff-release-gate.log`.
- A focused follow-up confirmed that sibling organization creation advances the
  MSP directory manifest without immediately indexing it. The transition pin
  correctly refused that lagging head. The fixture now indexes that accepted
  manifest before testing lock exclusion; the runtime readiness check remains
  intact. Log: `/tmp/tekdocs-handoff-guard-final.log`.
- **Verified:** final migration/inventory plus constrained-role suite passed all
  28 tests, including duplicate `.MD` identities, UUID edits, sibling native
  authoring and lock exclusion. Final changed-file Ruff passed. Logs:
  `/tmp/tekdocs-handoff-remaining-gates.log` and
  `/tmp/tekdocs-handoff-final-lint.log`.
- **Initial blocker (resolved below):** fresh/0.8.46 comparison could not build its historical
  renderer. Baseline commit `35e93ca` expects Chromium 152, but its current Alpine
  package source supplies Chromium 155.0.8059.84. The version guard correctly
  stopped the build before migration comparison. This is a reproduced baseline
  dependency failure, not evidence of migration success. The aggregate
  `document-migration-release-gate` stopped at this stage. The follow-up below
  repairs the rehearsal dependency selection. No browser-version check was bypassed.
- **Verified:** `make production-image-rehearsal` passed for the current source:
  non-root runtime file access, renderer/browser identity, repository persistence
  after restart, container isolation and file-backed secrets. Log:
  `/tmp/tekdocs-handoff-production-image.log`.

## Historical rehearsal repair — October 25

Scope: #105 migration-validation follow-up. Acceptance: preserve the original
0.8.46 Django schema and fixture, upgrade the retained database, compare stable
identities and fresh/upgraded import/rollback results, and retain current backend
startup plus production-image checks.

The reproduced failure is recorded in `/tmp/tekdocs-handoff-remaining-gates.log`:
the historical renderer build requested Chromium 152 and received 155. The legacy
fixture exclusively invokes Django management commands through `migrate`; it
never calls the HTTP backend, renders diagrams or publishes PDFs. Starting the
historical backend unnecessarily pulled in that renderer build.

The rehearsal now builds and executes the unchanged historical `migrate` service
with its database and SMTP readiness dependencies before creating legacy data.
It still uses the pinned 0.8.46 Git tree and original migrations. The upgraded
and fresh phases still start the current backend with renderer readiness. All
fixture assertions and comparisons are unchanged, including stale-preview denial,
idempotency, template deferral, historical Git reads and rollback audit counts.
This does not claim historical renderer or HTTP compatibility, nor does it waive
those capabilities' dedicated checks. No runtime code, schema, API or public
operator instructions change; a Wiki update is not required.

**Verified:** `make document-migration-upgrade-rehearsal` passed after this repair.
Log: `/tmp/tekdocs-handoff-upgrade-repair.log`. Shell syntax and diff checks passed.
**Verified:** `make document-migration-release-gate` completed successfully after
this repair (exit 0). It passed 772 frontend tests, 120 tooling tests, backend
Ruff/mypy (270 source files), schema/API drift checks, 158 authoring/content tests,
28 migration/runtime-isolation tests, the fresh/0.8.46 upgrade comparison, and the
production-target image rehearsal. The latter verified non-root file access,
renderer/browser identity, repository persistence across restart, container
isolation and file-backed secrets. Log: `/tmp/tekdocs-handoff-complete-gate.log`.
The earlier aggregate blocker is resolved. The supported encrypted recovery
rehearsal recorded above remains applicable: this follow-up changes only the
historical rehearsal startup, not runtime code or the recovery fixture.

These local results do not replace hosted candidate validation, security review
or release authorization.
