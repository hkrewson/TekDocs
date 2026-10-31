# ADR 0118: Content-key Git publication custody

**Date**: 2026-10-31

**Status**: accepted for the bounded development slice; local validation complete; exact-source hosted validation pending

**Deciders**: TekDocs maintainer

## Context

ADR 0117 migrated scalar keys and entity cards. The maintainer subsequently
included content keys, which substitute reusable block bodies and can contain
further content and field keys. Reading retained SQL revisions after promotion
would split authority and could publish different text from the Git reader.

## Decision

Extend the existing internal/permanent migration operations to exact-Workspace
content-key graphs. Keep the existing current-revision semantics of content keys;
they do not acquire an invented pin mode. Ordinary pinned placements retain
their existing selected revisions. Substitution uses the selected block body,
as the legacy resolver does, rather than its owner's entire document.

Migration previews bind selected SQL revision identities and checksums. Copy the
source documents before their consumers, then hand off their complete live group
atomically. Active block bindings are conservatively live edges even when unused
in the current body. Include those edges in group fingerprints and rollback.
Database closure and binding-writer guards serialize source transitions against
late consumers; Python checks are not the only enforcement.

The reader and publication freezer use current indexed, accepted Git fragment
bytes after central Entity authorization. Retained SQL supplies stable identities
and configuration, never replacement block text. Missing/stale source projections
produce explicit unavailable markers or block publication. Bindings remain
read-only under repository authority. Resolve nested keys as the consuming
document, preserving its permissions, file ownership and expansion limits.
The content-walk budget does not replace the existing ordinary composition
budget for source documents that perform no content substitution.
Current editable exports use the same Git inputs. Portable document v4 identifies
Git content-key resolution records; legacy and field-only v3 exports retain their
existing contract. Deterministic export timestamps include the selected Git
commit's retained creation time instead of pretending a SQL revision was resolved.

STATIC v10 retains authored Markdown and existing composition/file certificates,
plus signed content-resolution records containing the exact Git source, blob,
commit, repository, Workspace and fragment identity. Git content records have
null SQL revision identifiers; their proof names Git custody instead. Offline
verification hashes the retained source as a Git blob, parses its identity,
reconstructs the bounded substitution and checks binding, dependency-chain and
frozen-output agreement. It does not consult current SQL block text or Git.
The additive SQL guard checks scope, bindings, selected index/source identity and
evidence shape. It does not duplicate Markdown parsing or signature verification.
Earlier v1-v9 contracts and signed bytes remain unchanged.
The older repository-evidence format still refuses content snapshots at its
existing pre-insertion rendering gate; this decision adds no evidence format there.

Reversible Git writes validate keys and file ownership for content-key owners
and live consumers, including nested accepted source bodies. Reject edits that
would make their retained binding graph unprojectable on rollback. Preserve
ordinary field-key-only draft behavior outside this graph.

## Consequences

Git edits affect live consumers and future publications; earlier signed output,
PDFs and file versions remain immutable. Rollback projects all owners together
before checking consumers. Hosted recovery must compare actual signed/media/Git
bytes and bindings after independent encrypted restore; a local fingerprint
check alone is not independent recovery evidence.

No general cross-Workspace content-key reuse, client delivery, diagrams, release
publication or production migration is included. No runtime dependency is added
and no existing risk allowance is renewed. Source review and complete exact-source
validation must precede completion of this development slice.
