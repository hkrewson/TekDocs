# Reversible first-document handoff implementation

October 25, 2026. Scope: #105 / #106 and proposed ADR 0115. This is an
implementation plan, not a completed guard or authorization to mutate production.

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

## Enforcement boundary

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
- Validate authority-transition/write races. The transition currently locks the
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

## Current execution limit

Docker reported only 229 MB available on October 25. The preceding live rehearsal
had already failed with ENOSPC. Cache-only cleanup approval is pending before a
new disposable database rehearsal. No runtime source or test expectation has
been changed in this planning step. Production remains untouched.
