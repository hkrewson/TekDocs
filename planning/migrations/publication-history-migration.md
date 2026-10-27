# Publication-bearing ordinary document migration

October 27, 2026. Bounded #105/#106 follow-up. The maintainer authorized
implementation that preserves signed publications/PDFs and verifies rollback
and recovery. The maintainer subsequently authorized the direct main commit/push
and hosted validation recorded below. No production data or authority changed;
no new release or deployment occurred.

## Acceptance boundary

An active ordinary document with one live, owned fragment and verified internal,
permanent STATIC history may use the existing preview/copy/promotion commands.
Every retained snapshot must pass the existing trusted-signature, metadata,
control-history, ownership and PDF-custody assessment. Older snapshot text need
not equal the current draft. Retained rows, signatures, manifests, artifact IDs,
file locations and PDF bytes are never rewritten to enable migration.

The initial boundary excludes templates/enrollments, other retention modes,
client-visible history, current managed files, key bindings, borrowed placements,
entity dependencies, unfrozen references and diagrams. Existing repository,
composition, workflow/review, file-custody and reversible-shape gates still apply.
A failed assessment keeps `publication_parity_required` or
`legacy_publication_history_present`; a diagnostic `verified` state alone does
not clear the other shape or authority gates.

## Import and authority contract

A shared history eligibility check is consumed by inventory, import preparation,
coexistence status and Git publication. The plan checksum additionally binds the
retained-history fingerprint. A changed control event or snapshot invalidates an
old plan, including the previously copied/idempotent path. A fresh history check
after a new Git copy reports source changes rather than claiming successful
import if the history changed during execution. Copying does not transfer authority.

History-bearing copy, copy cleanup, promotion and rollback require an active,
exact-tenant actor granted `documents.edit` through the existing policy service,
including its MFA-enrollment requirement and exact-client access rules.
Authority transitions also require the supplied reader context to match that
actor and owner Workspace. This is an operator command boundary, not a new public
write endpoint or an interactive MFA challenge. Source preview remains read-only;
preparing a plan no longer writes repository reconciliation markers.

Promotion/rollback run under the established Git/repository/document lock order.
Rollback projects only supported body changes into a new retained legacy revision.
A second history assessment must match the initial fingerprint before the
transaction commits. The transition audit records that fingerprint. Valid
legacy/v5 mixed history may be promoted again after a verified rollback.

## Publication lifecycle

The ordinary publication service can append a v5 Git snapshot superseding a
verified legacy internal snapshot of the same document and Workspace. It checks
the complete supported history and retained custody before publishing. Existing
approval and withdrawal controls remain authoritative; supersession never
updates the older signed record. After rollback, ordinary legacy publishing can
append a successor to a retained v5 snapshot.

Restricted-role testing reproduced a prior immutable-row locking defect: the
snapshot was visible to SELECT, hidden by SELECT FOR UPDATE, and independently
verified as published with intact custody. Both Git and legacy predecessor
lookups now read the immutable row without requesting UPDATE visibility.
Document/composition locks and existing approval advisory locks, competing-
successor checks and append-only SQL guards remain in force. No UPDATE grant,
new schema, cryptographic format or signing key is introduced.

## Recovery and operator use

The supported recovery fixture creates a legacy signed snapshot, changes the
draft, copies/promotes it, edits Git and creates a v5 successor. Its source run
emits the verified history fingerprint alongside the existing source/bundle
checksums. The shell rehearsal validates and passes this fingerprint into the
independent restored installation. Restore verification requires the same history,
known old/new text, original signatures and PDF custody, then rolls back and
rechecks the fingerprint. Repeating verification exercises re-promotion followed
by rollback without changing the retained history or Git head.

Use the existing `preview_document_migration` and `import_document_migration`
commands with a fresh plan; then preview `transition_document_authority` and
apply only its reviewed, eligible transition. Reverse authority with the same
command targeting `legacy`. Copy cleanup is distinct from authority rollback
and never removes retained publication rows or PDFs. Keep these procedures
internal per ADR 0115. A released implementation, fresh production preview,
backup, reviewed plan and separate production authorization precede any live copy
or authority change. Production remains on 0.9.15.

## Validation disposition

Verification results will be recorded after the combined Docker gate and source
checks finish. The full `document-migration-release-gate`, supported encrypted
recovery, supported upgrade matrix and production-image rehearsals create
separate Compose environments. Under the single-local-project rule these remain
hosted gates for this new source; no new local stack or data volume is authorized.
Earlier successful runs at `bef8c90` verify the preceding v5-only lifecycle, not
this new legacy-history migration implementation.

No new public API field or schema migration is needed. API contracts/schema drift
checks must confirm that. The frontend publication controls remain a later slice.
No public Wiki workflow is added; existing maintainer-owned Wiki edits are preserved.
No new risk exception or acceptance is implied by passing local tests.

## Local verification — October 27, 2026

Verified: **285 Docker tests passed** in one serial, fresh-test-database run.
The selection combines the Make authoring and migration-inventory gates with
publication/read-failure and ordinary document regressions, plus a replay of the
actual recovery fixture's create and repeated verify modes. The new 17-case
migration module covers legacy-to-Git supersession, unchanged old signature/PDF,
copy cleanup, authority rollback/re-promotion, stale plan refusal for new and
existing copies, damaged custody at each gate, active-actor/MFA denial,
foreign-tenant and wrong-client denial, reader/operator identity mismatch,
unsupported retention, and the restricted runtime-role lifecycle including
legacy publication after rollback. The preceding 13 assessment cases remain.
Log: `/tmp/tekdocs-history-broad-gate.log`.

The initial broad production-profile run had 281 passes and four failures:
one missing test import introduced while separating migration tests from the
assessment module (corrected), and three pre-existing real-cache dependencies
unable to resolve the already-restarting local Valkey service. That service and
its retained data were left untouched. The successful final run uses the
repository's standard test settings (isolated cache/email, real PostgreSQL and
private Git/media paths), not relaxed assertions or another local service.
Real-cache integration therefore remains a hosted verification requirement.

Both predecessor-locking failures were reproduced with the restricted role
before their fixes. Normal SELECT saw a published snapshot with verified custody;
SELECT FOR UPDATE could not see it. The runtime regression now verifies Git
supersession of a legacy snapshot, rollback, legacy supersession of the v5
snapshot, and re-promotion. No private row-update privilege was granted.

Backend Ruff passed; mypy found no issues in 272 source files. Django reported
no migration-state changes. OpenAPI validation had zero errors and the same four
existing operation-ID warnings; generated schema bytes match `backend/openapi.yml`
exactly. No frontend contract regeneration is necessary. All 120 tooling tests
passed (three optional skips), including shard discovery and Wiki/link contracts.
Shell/fixture syntax, version consistency (still 0.9.15) and diff checks passed.

At the local verification checkpoint (superseded by the hosted results below),
verified: signed-history/PDF preservation, supported source handoff, rollback,
repeatable recovery-fixture verification, and runtime authorization.
At that checkpoint, inferred but not yet verified: this new source will pass the full independent encrypted
archive/restore path. Blocked pending authorized source push and hosted execution:
complete recovery, supported upgrades, production-image and aggregate release
validation for this slice. Prior green runs do not attest to these new changes.
At that local checkpoint no production mutation, release, branch, PR, commit
or push had occurred. The maintainer subsequently authorized committing and
pushing this slice directly to main and running hosted validation. Production
migration/deployment remains separately authorized work.


## Hosted closeout — October 27, 2026

Validated application source: `aa2cd4338be6d54219196f975e1c49b3deca77ed`.

- [Build, test, and secure 40460675424](https://github.com/hkrewson/TekDocs/actions/runs/40460675424)
  passed: frontend/static/dependency policy, every PostgreSQL group, restricted
  runtime/RLS tests, combined coverage, browser journeys, diagram exports,
  production containers, SBOMs and vulnerability scanning. Release-only CodeQL,
  embedded release-Extended and image-publication stages were skipped because
  0.9.15 was already published; the standalone Extended run below was requested.
- [Extended validation 40460698493](https://github.com/hkrewson/TekDocs/actions/runs/40460698493)
  passed: independent encrypted backup/restore, repository-foundation acceptance,
  recurring-invoice history after restore, supported upgrades, diagram-source
  upgrade/restore evidence, all browser engines, performance and DAST.

The recovery job verifies this slice's source-emitted history fingerprint in
an independently restored installation, both legacy and Git snapshot text and
signed PDF custody, rollback, and unchanged retained history afterward. Hosted
real-cache integration passed; the unavailable local cache was not repaired or
replaced to obtain that result.

Verified: the new history migration/lifecycle and encrypted recovery at the named
source, with the local and hosted evidence above. The full aggregate
`make document-migration-release-gate` was not invoked as one command, and its
standalone historical document-migration upgrade rehearsal was not run by these
workflows. Its authoring/inventory selections ran locally in the existing project;
current supported upgrade/recovery and production-image gates ran in CI. Complete
aggregate release acceptance remains a future candidate gate; these results do
not declare 1.0 or authorize a production migration.

Remaining scope: unsupported files/templates/client-visible history and retention
modes, interface integration, versioned release review and separately authorized
production preview/backup/handoff. No new risk exception was accepted. Later
instruction-file tracking and evidence commits contain no application changes and
do not relabel these runs as validation of a different runtime source.
