# ADR 0096: Versioned documentation maps and retained baselines

- Status: accepted
- Date: 2026-09-01

## Decision

TekDocs models an operational manual as a first-class map with append-only metadata revisions and entries. A mutable map points at one current revision. Editors use optimistic concurrency. Baselines retain portable deterministic ZIP bytes rather than rebuilding an old export on demand.

Live documents intentionally resolve when a baseline is created; exact document revisions and STATIC publications remain pinned. The manifest records which behavior was chosen and the exact dependency digest. Subordinate maps are expanded recursively while preserving their revision identity.

Client-visible maps are a publication boundary. They may reference only approved current client publications and approved client maps. Portal delivery rechecks current approval, map revision, archive state, and every dependency before listing or downloading a retained baseline.

## Consequences

This supports operating manuals, disaster-recovery plans, onboarding sets, compliance binders, and client handoffs without duplicating source documents. It also creates additional retained data: revisions, entries, baseline artifacts, and audit events are deliberately immutable and must be included in backup, restore, storage-capacity, and retention planning.

DITA informs hierarchy, reuse, key resolution, and audience validation, but TekDocs does not expose DITA XML as its authoring or import contract for this release.
