# ADR 0121: Client-published document Git custody

**Status:** accepted for the bounded #105/#106 implementation

**Decider:** TekDocs maintainer

## Context

Existing client publications are signed PostgreSQL workflow records with retained
PDF/file artifacts. Client URLs, approvals, corrections, withdrawals and inbox
targets identify those records independently of current authored content. Moving
authored content to Git must neither replace those identities nor grant access.
The maintainer explicitly included MSP-only and client-only section profiles.

## Decision

Extend the existing reviewed migration and explicit authority handoff to supported,
verified client-visible history, retaining the existing reversible ownership and
approved template-library boundaries. Preserve permanent and review-on-date
retention, stable identities, append-only signatures and controls, every file
version and original artifact bytes. Unsupported or damaged history stays blocked;
no historical PDF is reconstructed to make a record eligible.

Keep the existing DocumentPublication portal routes and workflow. Do not translate
old records into the separate RepositoryStaticPublication delivery protocol.
Promotion, rollback and re-promotion do not approve, deliver, reopen or withdraw a
publication. A new client Git snapshot remains pending until a different user
passes the existing central approval policy. Approving a correction supersedes
its same-audience predecessor; withdrawal does not reopen that predecessor.

Preserve each section's original profile and nested narrowing. The primary section
remains shared. Copy the complete authoring graph, but pin each new snapshot to its
own accepted/indexed audience composition. Validate all cached audience variants
against accepted Git before using the complete composition for review checks.

The signed Git source descriptor has an optional `audience_filtered: true` marker
for client or mixed-profile snapshots. Selected source records retain original
ordinal paths, including gaps left by excluded sections. Historical unmarked
certificates retain their contiguous-path checks. Source paths remain sorted,
unique, bounded and rooted; insertion binds them to the selected indexed manifest.
No excluded section identity, body, ordinary-file descriptor or unused key binding
is added to the client's signed projection. The accepted root's opaque Git/blob
hashes still attest the complete authored source.

Filtered snapshots retain only referenced ordinary files and every primary-file
version. The Markdown parser selects references; database guards independently
retain exact owner, scope, metadata, artifact, size/count and primary-chain checks.
Unfiltered snapshots retain their existing complete-file requirement. Filtered key
maps contain exactly the bindings used by frozen records, including nested content
key dependencies. Both accepted frontmatter and live owner bindings must attest
those targets. Existing field/entity audience policy runs before freezing; client
record visibility is also checked by the insertion guard.

Django migration 0212 installs these audience-bound guards over the existing
v5-v11 certificates and diagram validation view. Existing signed objects are never
rewritten. No new schema initialization, dependency, publication format, endpoint,
portal permission or client delivery authorization is introduced.

## Validation and consequences

Use real operator/publication/portal interfaces, runtime-role allow/deny and exact
client/tenant isolation checks, a staff/independent-approver/client browser journey,
and before/after byte/signature/control comparisons. Verify body-edit rollback and
re-promotion. Fresh/0.8.46 upgrade and independent encrypted recovery include active,
pending, withdrawn and internal records, mixed profiles, field keys and native-file
versions. An active companion proves restored positive client access while the
corrected document remains withdrawn.

Local validation reuses existing services and a generated database. Independent
upgrade/restore environments run in hosted CI. This is development after 0.9.17;
release preparation, production migration/deployment, Wiki publication, general
cross-Workspace reuse and aggregate 1.0 acceptance remain separate. Existing risk
exceptions are neither renewed nor expanded by this decision.
