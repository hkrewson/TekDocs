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
