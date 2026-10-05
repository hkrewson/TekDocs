# ADR 0111: File-backed reusable fragment composition

Status: Accepted

Date: 2026-10-05

## Context

The `0.9.2` content profile identifies documents and fragments and indexes
ordinary links. Legacy document placements also provide ordered nested reuse,
live and pinned revisions, independent copies and audience controls. Ordinary
Markdown links and incoming backlinks cannot decide what appears inline.

## Decision

`tekdocs.content/v1` frontmatter may contain an ordered `includes` list. Every
entry has a fragment UUID, `live` or `pinned` mode, and one of `shared`,
`msp_internal`, or `client_visible` audiences. Pinned entries include the exact
retained Git commit object ID. Fragment files reside under the reserved
`fragments/` directory. A live include uses the accepted commit of its
containing snapshot; a live child nested inside a pinned fragment uses that
pinned snapshot. Targets must be fragments in the same repository.

An independent copy is a new fragment UUID and optional `derived_from` UUID
and exact commit. It does not follow later source changes. Documents may carry
ordered `template_sources` references to exact content IDs and Git commits.
The index records their pinned and current digests and a current, changed or
missing preview. PostgreSQL remains authoritative for template enrollment and
rollout decisions.

The index resolves all accepted content into `all`, `msp_internal`, and
`client_visible` compositions. A nested include cannot widen or change a
restricted parent's audience. Expansion is bounded by depth, node count,
source count and bytes. Cycles, unavailable pins, ambiguous identities and
invalid provenance reject the entire accepted commit; the previous graph
remains readable. Derived include/template rows use exact-workspace forced RLS
and relational scope triggers. The raw graph API remains an MSP staff authoring
surface; client portal readers use retained approved publication routes.

## Consequences

Documents own their ordered outgoing inclusion list. Backlinks describe reuse
and never control rendering. A rollback is a new commit with restored Markdown;
its exact-source digest changes when live includes resolve through the new
commit even when rendered text is identical. Source manifests retain that
distinction for later publication freezing and conflict review.

The database-backed editor and publication system still use their existing
storage in this checkpoint. Managed Git writing, migration and publication
parity remain later work.
