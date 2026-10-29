# File-backed publication migration (subsequent to 0.9.16)

Supported internal documents can now migrate with managed attachments, every
primary-file version and intact signed publication history. New Git publications
retain each file and a PDF in a signed v6 snapshot. Earlier signatures, manifests,
PDFs and private source files remain unchanged.

Rollback preserves supported Git text edits and files uploaded after promotion.
Missing, altered or foreign files block migration/publication; missing or foreign
file links are rejected before a reversible Git edit is accepted. Publication
limits refuse oversized sets without discarding versions. Authorized staff use
the existing publication Downloads section for exact retained file versions.

See the [acceptance and validation record](../migrations/file-backed-publication-migration.md).
This is development on 0.9.16, not a new versioned release or production migration.
Templates, unresolved dependencies and client delivery remain outside this slice.
