# ADR 0114: Stable managed-file content ownership

**Date**: 2026-10-09
**Status**: accepted
**Deciders**: TekDocs maintainer

## Context

Canonical Git documents can be created without a legacy `Document` row, but
`DocumentAttachment` currently requires that row. Repository rendering and
publication preflight therefore cannot use a file owned by a Git-only document.
PostgreSQL remains authoritative for files, scanning, permissions, publication
evidence and recovery; the rebuildable content index cannot own canonical file
records.

## Decision

Extend the existing managed-attachment record with an exact Workspace and
stable content UUID owner. Backfill legacy rows from their document, preserve
their existing document link and public file identity, then permit a null
legacy-document link only for repository-native ownership after database,
authorization and recovery guards are ready. A Git content node is validated
at the accepted-and-indexed revision when a file operation occurs, but is not
a foreign-key parent of retained file custody. The existing scanner, private
storage and publication-evidence identity remain in use.

## Alternatives considered

### Separate repository attachment table

- **Pros**: Leaves legacy attachment rows and triggers unchanged.
- **Cons**: Duplicates file custody, link resolution and publication evidence;
  the retained evidence currently references `DocumentAttachment` directly.
- **Why not**: Two attachment authorities would make handoff and recovery harder
  to prove without improving the canonical Markdown boundary.

### Synthetic legacy document for each Git-only document

- **Pros**: Reuses current upload and download routes immediately.
- **Cons**: Creates an apparent legacy body owner, risks incomplete entries in
  legacy document views, and obscures which store owns authored content.
- **Why not**: A compatibility row is not a safe substitute for explicit file
  ownership and a gated authority transition.

## Consequences

### Positive

- Existing attachment UUIDs, storage keys and retained publication references
  survive the ownership expansion.
- Git-only documents can eventually own managed bytes without relying on a
  derived index row or a synthetic legacy body.

### Negative

- Database triggers, RLS, upload/download services, rendering, exports,
  publication evidence and backup verification must all understand the new
  owner form before repository-native file upload is enabled.
- The schema must expand and backfill before the legacy foreign key can become
  optional; old deployments cannot skip the upgrade sequence.

### Risks

- A mismatched Workspace or content UUID could cross client boundaries.
  Database guards and application policy must enforce both, with sibling and
  cross-tenant denial tests.
- Git and PostgreSQL cannot commit atomically. Missing or unindexed content,
  failed uploads and retained-file corruption must fail closed without
  manufacturing an accepted Git revision or silently switching authority.

Repository document read/write authority and legacy-write retirement remain
blocked until file, review, template, key, publication and recovery parity
pass the explicit 0.9.7 handoff gates.
