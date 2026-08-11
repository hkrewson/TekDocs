# ADR 0026: Retained publication artifacts and lifecycle

- Status: Accepted for `0.2.8`
- Date: 2026-08-09

## Context

A signed STATIC snapshot is useful only if the bytes presented later are the bytes produced at publication time. Regenerating a PDF or following a managed-attachment reference after publication would reintroduce mutable dependencies. Policy and legal records also need a correction trail and a review signal without permitting evidence deletion or mutation.

## Decision

Every new STATIC publication uses manifest format `tekdocs-static-publication/v2`. It retains exactly one generated PDF and an independent copy of each referenced managed attachment. Each `DocumentPublicationArtifact` has its own universal entity identity, opaque storage name, media type, exact size, SHA-256 checksum, and signed manifest descriptor. The source filename is display metadata only. Artifact reads recheck both size and checksum and fail closed on missing or changed bytes.

PDF generation is server-side and deterministic for the same frozen inputs. TekDocs supplies the presentation, fixed metadata timestamp, publication identity, audience, reason, and numbered footer. Raw HTML, authored CSS, remote resources, and executable content are not part of the PDF path. The supported Markdown structures remain bounded by the server renderer.

Publication requires a bounded reason, explicit audience, and retention class. `client_visible` is permitted only for an organization-owned document and records intended audience; it does not grant portal access. Retention is either `permanent` or `review_on` with a date. A due date derives `review_due`; it never deletes, hides, or modifies evidence.

A correction creates a complete new publication and may nominate one prior publication of the same document and workspace. As amended by ADR 0049, a predecessor may have multiple attempted successors but only one approved successor; an unapproved or withdrawn correction does not permanently block a later attempt. No row is updated: current, superseded, review-due, and withdrawal state are derived from immutable publication and control records. Existing `v1` publications remain readable and verifiable, while database guards require `v2` for new inserts.

Publication and artifact rows are append-only in Django and PostgreSQL. Deferred database validation requires the stored artifact set to match the signed manifest before commit. Artifact scope, source attachment, entity type, and publication identity are database-checked and protected by forced row-level security. Storage writes occur inside the publication operation; if any later validation or database write fails, TekDocs removes all bytes written by that attempt.

## Consequences

- Retained artifacts consume managed storage independently of their editable sources; deleting or replacing a source file cannot invalidate a completed publication.
- TekDocs exposes no publication or artifact purge workflow. A future retention-policy change must be a separate, explicitly reviewed design rather than an interpretation of `review_on`.
- The application can verify stored snapshot signatures and artifact checksums, but this is not an external timestamp authority or a qualified legal electronic signature.
- Existing `v1` publications do not gain generated artifacts retroactively; their original signed contract remains intact.
