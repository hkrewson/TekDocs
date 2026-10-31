# ADR 0117: Addressed Git publication custody

**Date**: 2026-10-31

**Status**: accepted for the bounded development slice; hosted validation pending

**Deciders**: TekDocs maintainer

## Context

Documents with portable field bindings and typed entity links need live current
values while their signed publications retain the values originally published.
Git custody cannot replace retained signatures, PDFs or managed-file history.

## Decision

Extend the bounded internal/permanent migration path to exact-Workspace field
keys and typed entity mentions. Existing prepare/apply/handoff operations retain
binding identity and the authored expressions. Content-key substitution and
foreign record dependencies remain unsupported. The existing central policy,
MFA and tenant/Workspace boundaries apply to readiness and publication creation.

Reuse the permission-aware field freezer and entity-card resolver used by Git
repository evidence. Lock bindings and referenced records while preparing the
snapshot. Bind the indexed root's portable binding map to active SQL bindings;
missing, archived, denied, foreign or mismatched inputs block publication.
Promoted binding configuration stays read-only until rollback because changing
it without a matching protected Git-root operation would split authority. The
Keys panel reports expressions from current Git, with loading and retry states.

STATIC v9 retains authored Markdown, its Git source proof, portable bindings,
the frozen field projection and records, entity cards, and existing file/shared/
template dependency certificates. Canonical Markdown and HTML/PDF contain the
frozen values. Offline verification reconstructs the projection with the existing
parser and verifies the signature and retained artifacts without live records.
The additive SQL guard validates scope, binding identity, source/index parity
and frozen evidence shape; it does not implement Markdown parsing. Earlier
formats and retained bytes remain unchanged. Reverse migration reinstates the
previous guard without rewriting existing v9 evidence.

Manifest-only synchronization preserves a previously current content index in
the same coordinated transaction. It does not silently index a preexisting stale
repository. Creating another client must not invalidate an existing MSP reader.

## Consequences

Later record edits affect live readers and later publications. They cannot alter
retained snapshots. Rollback restores current raw Git expressions and the same
binding identities, versioned files and immutable evidence. Recovery requires
PostgreSQL, accepted Git repositories and private media together; hosted upgrade
and encrypted recovery use the same synthetic fixture as browser acceptance.
Client delivery, content keys, diagrams and general structural authoring remain
separate work. This slice makes no release or production migration claim.
