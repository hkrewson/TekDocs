# ADR 0116: Enrolled template library Git custody

**Date**: 2026-10-30

**Status**: accepted for the bounded development slice

**Deciders**: TekDocs maintainer

## Context

Versioned MSP templates can enroll client Documents with independent copies,
LIVE sections and pinned sections. Moving only the client or only its mutable
source can split authority. Treating every borrowed section as a copy would lose
the user's selected update behavior. Templates also retain immutable definitions,
managed files, signed publications and PDFs that cannot be rewritten to fit Git.

## Decision

Extend ADR 0115 through an explicitly listed source-and-client cohort. Each
Workspace requires central edit/MFA authorization. Preview binds accepted/indexed
Git heads, original owners, enrollment identity and maps, applied definitions,
retained file/publication custody and local content. Ordered repository leases
precede SQL owner locks; promotion and rollback change the whole LIVE dependency
closure atomically. Deferred SQL guards include consumers hidden by RLS.

Use paired `library_workspace` and `library_revision` include metadata only for
an actual approved MSP library source enrolled by this client Document. The
adapter and SQL projection validate the retained parent placement, selected
Block, mode, audience, applied revision and source Workspace. Ordinary includes
keep their same-Workspace meaning. Foreign sections contribute their selected
body only; source-owned descendants are separate enrollment placements. Foreign
file, key and entity dependencies remain unsupported. Missing Git custody has no
database-body fallback, including when a client's own commit has not changed.

Retain immutable historical template manifests and exact selected BlockRevision
bodies at service-owned `template-snapshots/<revision>/...` paths. Non-Markdown
snapshot suffixes prevent duplicate current ContentNode identities. Git edits
rebuild the derived immutable workflow cache from verified accepted source bytes;
PostgreSQL continues to own definitions, enrollment, permissions and audit.

Template rollout, creation and detach are narrow reviewed operations. Creation
binds the current source definition and file selection; apply binds client commit,
composition, applied and available template versions. A private operation lease
permits exactly the resulting protected Git graph. SQL checks its final index
against retained placements and enrollment. Local copied edits become conflicts;
they are not overwritten. Detach retains the selected live or pinned body and
adds an immutable audit proof binding its source commit/revision/hash to the new
client-owned initial revision. Copied primary files retain an ordered version
chain under new file identities.

Git and SQL writes share a coordinator through the outer request/operator
transaction. Refs follow SQL savepoints and final accepted pointers. Only a
validated attempted write authorizes compensation; reads and rejected writes
cannot repair preexisting drift. Created file cleanup follows the durable SQL
outcome, including later savepoint/constraint failure and post-commit callback
failure. Cleanup attempts every independent file and logs a value-free recovery
failure if storage prevents removal.

New v8 internal/permanent publications bind either approved foreign library
sources or an immutable MSP source-template certificate, alongside owned-file
proof. Earlier signed formats and PDFs stay unchanged. Verification uses retained
signed inputs and artifacts independently of live Git. Existing client-portal
write policy remains unchanged.

Rollback verifies actual current Git and complete retained SQL template history.
It can return to legacy when newly derived template snapshots have not yet been
copied into Git; a new promotion still requires those snapshots. Operational
backup includes PostgreSQL, all accepted repositories and private media together.
A single-Workspace editable source ZIP is not a cross-Workspace recovery set and
must fail rather than omit library dependencies.

## Consequences and limits

This is an enrollment-specific exception, not general cross-Workspace reuse.
Arbitrary structural authoring, repeated Block occurrences, keys/entity-dependent
template sections and client publication delivery remain outside the slice.
Independent copies can retain lineage without reading a subsequently private
source; no broader source visibility or foreign writes are granted.

The [slice record](../../planning/migrations/template-enrollment-migration.md)
owns validation and outstanding acceptance. Local tests do not substitute for
fresh/0.8.46 upgrade, independent encrypted recovery or exact-source hosted CI.
The published application remains 0.9.16; this decision does not authorize a
release, production deployment or public Wiki push.
