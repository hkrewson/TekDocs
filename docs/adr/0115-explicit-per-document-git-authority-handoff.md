# ADR 0115: Explicit per-document Git authority handoff

**Date**: 2026-10-10  
**Status**: proposed  
**Deciders**: TekDocs maintainer

## Context

A matching Git copy is not an authority switch. Legacy document routes still
own reads and writes, while review, template, key, file, and publication
records live in PostgreSQL. The repository editor correctly refuses edits to
a copied legacy document today. Switching that guard alone would permit
competing writers and could strand review history or make rollback impossible.

## Decision

Track content authority explicitly for each exact Workspace and stable
document UUID. Existing documents remain legacy-authoritative by default;
Git-only documents are repository-authoritative from creation. A copied legacy
document may be promoted only through an operator-directed,
compare-and-swap transition that verifies the accepted and indexed Git
revision, read and write parity, workflow and file custody, publication
behavior, and a restorable recovery point.

After promotion, authored content and revision history come from Git.
PostgreSQL remains authoritative for permissions, review, templates, keys,
files, publications, and audit. Existing legacy rows are retained as
historical and workflow records, never deleted or silently treated as current
authored content. Every legacy content-writing path must refuse the promoted
document; every repository-writing path must check its authority state.
Reads, search, exports, and publication must choose the same authority.

Publication-history assessment is read-only diagnostic evidence. It verifies
supported retained internal snapshots and their PDF custody independently of
today's draft, and fingerprints publication/control identities for comparison.
A verified history report alone is not publication lifecycle parity or
permission to import or promote. Eligibility additionally requires a supported
document shape and tested post-promotion publishing, controls, rollback and
recovery. The bounded extension below defines this slice; other shapes retain
their publication-history blockers.


Document API `id` remains the public entity UUID. The read-only `content_id` is
the stable document UUID used by Git roots and content-graph routes. Browser
readers and repository-editor links must use `content_id` after promotion; they
must not substitute the public entity UUID or display a legacy database copy
when Git lookup fails. A root with an empty raw body can still compose nonempty
content from its reusable fragments.

Rollback is an explicit audited transition, not a Git reset or marker toggle.
It must verify the current Git revision and project it into a new retained
legacy revision before legacy writes resume. Until that reverse projection
supports a document's shape, promotion must be refused or repository
authoring limited to the reversible shape. Failed promotion or rollback
leaves the prior authority unchanged.

Migration eligibility, promotion, rollback, and recovery instructions are
operator guidance. For the current single-operator deployment, keep them in
internal planning and runbook material; do not add end-user workflow or
public-facing migration guidance.

## Alternatives considered

- **Infer authority from an in-sync Git copy:** rejected because a copy can
  diverge and does not retire legacy writers.
- **Create synthetic legacy documents for Git-only content:** rejected because
  they obscure the true content owner and reintroduce a second body store.
- **One-way promotion with backup-only rollback:** rejected because it cannot
  provide the promised per-document reversal after new Git edits.

## Consequences

The authority boundary is inspectable and can fail closed. Existing workflow
and retained evidence survive promotion. The cost is an explicit PostgreSQL
state, centralized guards across read/write routes, a reversible projection
for supported document shapes, and fresh-install, upgrade, isolation,
publication, and independent recovery tests before activation. Unsupported
shapes remain legacy-authoritative with named blockers. Operators need a
local procedure for reviewing eligibility and recovery; end users need no new
authority-management interface.

## Preceding bounded internal publication lifecycle

The local implementation supports STATIC v5 internal/permanent snapshots of
already-promoted, single-owned-fragment documents without managed files or
unfrozen dependencies. The snapshot signs current Git source proof rather than
legacy revision IDs. A rollback exception applies only to verified v5-only
history with intact custody and controls; legacy/mixed history remains blocked.
The following [publication-history migration slice](../../planning/migrations/publication-history-migration.md)
extends this boundary to verified internal/permanent legacy history. Existing
snapshots and PDFs remain immutable, import previews bind their history
fingerprint, and authority transitions recheck it. Supported mixed legacy/v5
history may roll back and be promoted again; unsupported shapes remain blocked.
No broad migration or production handoff completion is implied. See the
[preceding lifecycle evidence](../../planning/migrations/internal-git-publication-lifecycle.md)
and the new slice's independent validation disposition.

The [publication interface follow-up](../../planning/migrations/git-publication-interface.md)
exposes this bounded internal/permanent lifecycle in Documentation. Readiness
uses the same pinned-source, review, supported-shape and custody gates as the
publisher, with the existing preflight contract. Publication rechecks all gates.
Retained history includes original and Git snapshots without rewriting either.
This does not expose authority transitions or broaden migration eligibility.

## Bounded file-backed migration

The [file-backed extension](../../planning/migrations/file-backed-publication-migration.md)
admits clean managed files and complete immutable primary-version chains within
the same single-owned-fragment internal/permanent boundary. Existing v4/v5
snapshots remain unchanged. New file-bearing snapshots use v6, binding each
retained file artifact, owner, metadata and primary-version predecessor in the
signed manifest. Offline verification uses retained bytes rather than current
live storage or authority. Database migration 0197 installs the additive guard;
reversing it prevents new v6 inserts while preserving existing signed rows.

Files retain their original Document owner across promotion and rollback. New
repository uploads for a promoted Document use that same durable link. Git body
edits may reference only that Document's verified files, including older primary
versions. Snapshot limits refuse oversized sets without truncation. Explicit
rollback can preserve a subsequently enlarged set above those limits, while
re-promotion and publication remain blocked until supported. This exception does
not waive file-byte, source-shape, authorization or signed-history verification.

## Shared live dependency groups

The [shared-block extension](../../planning/migrations/shared-block-publication-migration.md)
adds explicit bounded same-Workspace authority groups. Live owner/consumer closure
is mandatory; pinned consumers do not retain a mutable legacy writer. Previews
bind membership, accepted commit, current revisions, files and retained history.
Apply rechecks authorization and evidence under ordered Document/Block locks.
Promotion stages all group roots in one transaction; rollback projects every
owner revision before checking composed consumers. SQL guards serialize legacy
placement writers and reject split live authority, including consumers hidden by
RLS. Security-definer guards have fixed trusted search paths, no public execute
grant and no data mutations.

New v7 snapshots bind ordered live and pinned source evidence plus previously
supported owned files. Older signed formats and PDFs are never rewritten. Offline
verification uses retained signed inputs and artifacts. Migrations 0198-0200 are
reversible; reversing guards preserves existing snapshots. Structural changes,
repeated occurrences of one Block, shared foreign-owned file links and the other
existing unsupported shapes remain blocked.
