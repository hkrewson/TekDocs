# Older same-Workspace pins: deferred acceptance draft

Status: superseded November 2, 2026; optional future automatic-migration work,
not a 1.0 blocker. The maintainer chose a clean Git-backed start with manual
document copying/recreation. See the [current closeout plan](../1.0-closeout-plan.md).
The criteria below are retained as design context, not an active implementation
assignment or a promise of manual-copy fidelity. No existing data may be deleted.

Earlier draft decision: preserve all retained revisions of each affected source
block, including editions that no current placement pins. This is complete
retention for those source blocks, not an installation-wide history migration.

## Current boundary and intended outcome

The existing repeated-block test
`test_unrepresented_pins_stay_blocked_without_partial_consumer_copy` demonstrates
the current prerequisite: a legacy pin cannot migrate when its selected edition
has no suitable representation in accepted Git history. The exporter currently
searches historical, source-linked leaf fragments and refuses a missing match.
This source inspection is not a new runtime reproduction or implementation pass.

An otherwise supported document must become migratable when its selected legacy
revisions still exist intact, even if those editions predate repository creation.
Migration establishes verifiable Git custody for that history without inventing
old Git commits or changing the meaning of the pin.

## Proposed acceptance criteria

### 1. Preserve complete retained source-block history

Every retained immutable revision of each affected source block survives with
its original identity, revision number, authored Markdown/checksum and existing
provenance. Revision-to-Git custody is verifiable after recovery. This includes
unpinned editions and multiple revisions with identical text. Original records
are not rewritten, renumbered or assigned fabricated Git timestamps/authorship.

Git custody may begin at migration time. This contract does not prescribe an
archive layout or require reconstruction of complete pre-Git document trees.

### 2. Resolve the exact selected revision at every occurrence

Each pin remains bound to its original source block and selected revision in
the same tenant and Workspace. Two distinct revisions remain distinguishable
when their text is identical. Matching text in another block, Workspace or
tenant cannot satisfy the pin. Repeated identical pins, distinct pins of one
block, and mixed live/pinned occurrences preserve order, audience and identity.

Pins fix the authored block revision. Existing rules for resolving keys, record
references and files continue; an old pin does not become a new promise to
restore the entire Workspace as it existed on that date.

### 3. Keep live and pinned behavior separate

Later source edits update live occurrences and leave each pinned edition's
authored content unchanged. The behavior holds before handoff, under Git
authority, after rollback and after re-promotion. Support both MSP and client
Workspaces without adding cross-Workspace permissions or new reference modes.

### 4. Preserve publications, PDFs and managed files

Existing signed publication rows/manifests/signatures, retained artifact bytes,
PDFs and all managed-file versions remain unchanged and retain their authorized
access paths. A new publication freezes the correct occurrence-specific content
and truthfully identifies its retained revision and Git custody. Historical
signed formats keep their existing interpretation and validation constraints.

### 5. Require a reviewed, safe migration

Preview is read-only and reports the affected blocks, full revision inventory,
pin mappings, dependencies and blockers. Applying a plan rechecks authorization,
the reviewed source state and current repository/index state. A stale plan is
rejected. Existing source/live-consumer cohort rules remain in force.

Each approved operation is atomic: failure cannot leave a partial consumer copy
or authority handoff. A separately approved, completed history-preparation step
may remain as auditable custody; a later failure must not erase it or pretend
that the consumer migration succeeded. Repeating a completed operation safely
reuses verified custody without duplicating history or retargeting pins.

### 6. Fail closed without losing history

Missing or altered revisions, invalid provenance, inaccessible or corrupt Git
objects, stale indexes and forbidden scope are explicit blockers. Never silently
select the current version, another matching-text revision, or a database copy
as a substitute for failed Git custody. Errors must not disclose foreign data.

Resource limits are explicit. They cannot cause silent truncation or promotion
with only part of the required history retained. This contract does not require
unbounded operations; any staged/batched design must verify complete custody
before handoff.

### 7. Prove rollback and independent recovery

Rollback preserves original revision identities and pins, all signed artifacts
and file versions, and supported edits made under Git authority. Re-promotion
resolves the same selected editions. Encrypted backup and independent restore
retain the history, mapping, accepted commits, permissions and pin behavior
without depending on GitHub or another remote Git service.

### 8. Close with observable positive and negative evidence

Use normal owner and constrained runtime roles. Cover at least:

- Several pre-Git editions, including an unpinned edition and separate revision
  identities whose Markdown is identical.
- Repeated same-edition pins, different-edition pins and a live occurrence, with
  source edits proving that only the live occurrence advances.
- MSP and client same-Workspace cases, plus denied actor, cross-tenant and
  cross-Workspace lookalikes.
- Missing/tampered history, stale plans, interrupted operations and safe reapply.
- Existing/new publications, PDF and file-version downloads, rollback,
  re-promotion and exact encrypted recovery.

Run the relevant Docker/API and real browser workflows, source review, and
exact-source hosted fresh/supported-upgrade and independent recovery gates.
An unchanged historical pass does not establish this slice's implementation.

## Boundary with the other five required rows

This slice addresses missing historical custody for otherwise supported
same-Workspace source shapes. Source-owned children, consumer-owned children,
relationship mappings, removed/archived blocks and parameterized foreign bodies
remain required 1.0 work with their own acceptance contracts. Their restrictions
must remain explicit; this slice must not silently drop or reinterpret them.

No new history browser, pin-editing interface, production migration or public
Wiki publication is authorized by this acceptance draft. Existing supported
history/pin operations must be able to identify the retained editions accurately.
