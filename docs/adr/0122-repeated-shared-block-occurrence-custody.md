# ADR 0122: Repeated shared-block occurrence custody

Status: accepted for the maintainer-authorized #105/#106 development slice.
Baseline: published 0.9.18. [Acceptance and evidence](../../planning/migrations/repeated-shared-block-migration.md).

## Decision

A reusable Block identity identifies content ownership, not a particular use of
that content. Migration retains each shared-leaf placement's identity, ordinal
path, audience, resolution mode, selected revision and exact represented Git pin.
The index stores one node per content identity and one ordered include per use.
Two pins of one Block never share a UUID-keyed pin slot. Root/owned source files
remain current, while pin loaders resolve the selected commit independently.

Prior pin selection uses the exact parent's include ordinal. Copy fingerprints
bind occurrence-specific descriptors; parity checks compare each occurrence at
its path. Atomic live dependency groups and body-only rollback remain unchanged.
Missing represented accepted history is rejected rather than inferred. A repeated
owned Block with potentially different child structure remains unsupported.

New repeated-source publications use a v12 envelope whose signed occurrence_format
names the unchanged v7-v11 content or diagram certificate. Python verification and
normal reversible Django migration 0213 normalize a validation-only view. Original
bytes are signed/stored unchanged, including both envelope discriminators when a
diagram layer is present. Only raw v12 permits repeated source identities; ordered
paths remain unique, and the SQL guard binds all occurrences to the selected exact
indexed composition. Existing file, audience, key, template and diagram proofs
still apply. Historical v1-v11 formats keep their old constraints and verification.

No new API route, database column, dependency, signature algorithm, authorization
boundary or automatic production migration is introduced. Preview command output
adds per-occurrence identity/path/mode/audience fields. New envelopes are validated
through the existing publication, correction, withdrawal, history and download
routes; signed PDFs and managed-file versions remain retained independently of Git.

## Validation

Guarded-import and SQL-publication red/green reproductions are retained in the
slice notes. Positive/negative Docker tests cover distinct pins, repeated live
references, nested reference positions, audience separation, stale previews,
rollback failure atomicity, reversible SQL guards, retained downloads and recovery.
Browser and hosted fresh/0.8.46/independent-restore evidence must match final source.
General cross-Workspace reuse and arbitrary owned structural authoring remain
outside this decision.
