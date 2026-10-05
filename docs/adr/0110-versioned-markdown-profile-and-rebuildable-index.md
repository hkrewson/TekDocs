# ADR 0110: Versioned Markdown profile and rebuildable content index

Status: Accepted

Date: 2026-10-05

## Context

ADR 0105 makes managed Git canonical for authored documents, fragments and
portable metadata while PostgreSQL remains authoritative for authorization and
operational state. The repository foundation can retain exact accepted commits,
but a file format and derived graph are required before composition or migration
can use that authority safely.

The format must remain useful outside TekDocs, reject ambiguous or excessive
input, support stable links, preserve current taxonomy/topic governance, rebuild
without hidden state, and avoid exposing one workspace through another
workspace's links or diagnostics.

## Decision

Canonical authored files use UTF-8 Markdown with strict YAML frontmatter under
schema `tekdocs.content/v1`. Required fields are a UUID `id`, `kind` of
`document` or `fragment`, and a bounded `title`. Optional portable metadata is
limited to scalar/list properties, taxonomy stable keys, and the current
structured-topic type/version for documents. Unknown fields, duplicate keys,
aliases, excessive nesting and unsupported values fail the whole commit.

Prose may link to another content UUID with
`[[uuid]]`, `[[uuid#fragment]]`, or `[[uuid#fragment|label]]`. Parsing uses the
CommonMark token stream, so code spans and fenced code do not create graph
edges. Link count, frontmatter bytes/shape, properties and repository file count
are bounded. A target resolves only when that UUID exists in the same accepted
repository snapshot; otherwise it remains an unresolved finding.

PostgreSQL stores a disposable exact-workspace projection: content nodes,
portable properties, outgoing links and backlinks, topic/unresolved findings,
the indexed commit, and accepted/rejected index attempts. All organization
projection tables use forced row-level security. API reads additionally use the
central `documents.view` policy; rebuilds use `documents.edit`.

A successful rebuild replaces the entire repository projection in one database
transaction and records a deterministic digest. An invalid accepted commit
records sorted, value-minimized diagnostics and leaves the prior projection and
indexed commit unchanged. Incremental indexing is deliberately a commit-level
no-op when the accepted and indexed commits match; per-file optimization may be
added later without changing the result.

## Consequences

Git now carries portable identity and metadata as well as Markdown revision
history. PostgreSQL can be deleted and deterministically rebuilt for this
projection without becoming the content authority. Authorization remains in
PostgreSQL and raw Git access remains operator-equivalent custody.

This checkpoint does not migrate existing database documents, provide managed
file authoring, transclude fragments, bind operational entities, or freeze
publication dependencies. Those remain ordered `0.9.3` through `0.9.7` work.
Because composition is absent, ordinary links cannot create rendering cycles;
the next slice must add a separate bounded acyclic inclusion contract rather
than treating backlinks as transclusion instructions.

## Rejected alternatives

- Database-only content would not provide portable Git history or recovery.
- Path-based links would make renames rewrite identity and weaken portability.
- A shared cross-workspace graph would make authorization errors and backlink
  disclosure too easy.
- Partially accepting valid files from an invalid commit would create a graph
  that never existed at one accepted Git revision.
- Rendering directly from raw repositories would bypass policy and RLS.
