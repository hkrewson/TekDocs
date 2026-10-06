# ADR 0112: Operational entity context in file-backed content

Status: Accepted

Date: 2026-10-05

## Context

TekDocs documents need to describe a particular operational record without
copying its mutable name or serial number into a relationship. An asset also
needs discoverable setup, enrollment, maintenance and repair guidance. The
canonical document is a Git-backed Markdown file, while operational records
and authorization remain in PostgreSQL.

## Decision

`tekdocs.content/v1` accepts bounded `entity_links` frontmatter entries with a
stable entity UUID and a relationship: `setup`, `enrollment`, `maintenance`,
`troubleshooting`, `repair_event`, or `mention`. Narrative Markdown links may
use `tekdocs://entity/<uuid>`; links in code examples are not relationships.
No operational display name, serial number or authorization grant is stored in
the portable link. The accepted-commit index derives typed and narrative
links, including links in included fragments. These are rebuildable
PostgreSQL rows, not a second content authority.

Staff collection and detail reads use the exact workspace's indexed graph.
The detail response resolves visible entity context and replaces narrative
link labels at rendering time. An inaccessible or unresolved target supplies
no entity context. Asset documentation backlinks distinguish exact-device,
model and product-class matches; incoming links never cause inline inclusion.
The shared entity route supports other operational entity types with exact
matches. Search and health filters query the accepted index. Client portal
users cannot use raw repository read routes.

## Consequences

This slice adds read paths but does not move the legacy editor or publication
workflow to Git. Its asset panel reads the accepted repository projection; it
does not perform source edits. A schema upgrade clears each indexed-head marker
and rebuilds links from the accepted commit, leaving canonical files intact.
Cross-repository aggregation, remote Git synchronization, managed authoring,
legacy migration and publication parity retain their later roadmap owners.
