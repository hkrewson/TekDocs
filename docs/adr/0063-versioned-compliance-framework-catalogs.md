# ADR 0063: Versioned compliance framework catalogs

Date: 2026-08-12

Status: Accepted for `0.7.1`

## Context

Framework names and control identifiers are long-lived references, while the wording, guidance, ordering, and upstream framework version change over time. Updating a control row in place would rewrite the meaning of prior reviews and evidence. Copying an entire catalog for every release would preserve content but lose stable control identity and make later applicability or evidence reuse ambiguous.

## Decision

- A framework and each control receive a stable Entity-backed UUID in one explicit MSP or organization Workspace.
- A control edit creates an immutable `ComplianceControlRevision`; unchanged controls reuse their existing exact revision.
- A catalog version creates an immutable `ComplianceCatalogRevision` and ordered entries that pin exact control revisions. The framework's mutable current pointer is only a convenience projection and never changes an older snapshot.
- Canonical SHA-256 digests cover control content and the ordered catalog manifest. PostgreSQL constraints, scope-edge triggers, append-only triggers, forced Workspace RLS, central `compliance.view`/`compliance.edit` policy, and negative IDOR tests backstop the service boundary.
- Canonical control description and guidance fields accept Markdown text but are not stored or rendered as executable HTML. This slice does not add evidence, applicability, owners, status, review, risk, or certification claims.

## Consequences

Later assignments and evidence can point to a stable control while retaining the exact revision evaluated. Publishing a new catalog version is intentionally a full ordered snapshot, so omission is explicit rather than inferred from a partial update. Framework and control deletion is not exposed; retirement semantics require a later reviewed lifecycle design. A database and host administrator remains trusted and can alter storage outside the application/runtime-role boundary.
