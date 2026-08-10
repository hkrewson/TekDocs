# ADR 0028: Reusable-documentation certification boundary

- Status: Accepted for `0.3.0`
- Date: 2026-08-09

## Decision

TekDocs `0.3.0` certifies the reusable Markdown documentation and immutable STATIC-publication foundation implemented in `0.2.1` through `0.2.9`. It does not add or reinterpret a document model, migration, route, dependency, Markdown extension, editor feature, or publication format. ADRs 0019 and 0021–0027 remain the behavioral and security contract.

The dedicated `make test-documentation-certification` gate runs against PostgreSQL and composes the complete document/publication service and API corpus, malicious Markdown/rendering cases, the authenticated-route and IDOR matrix, raw non-owner forced-RLS checks, and the authorization-aware reference dataset with 2,500 immutable revisions. It is a required dependency of `make release-gate`; it does not replace the browser matrix, real-stack journey, security scans, production-image and clean-install rehearsals, general upgrade rehearsal, or documentation-specific upgrade and database/media recovery rehearsals.

The certification applies to one MSP per installation. It proves the implemented Markdown, reuse, attachment, and STATIC-publication contracts at the alpha reference scale. It does not claim the final 250,000-revision/concurrent-user capacity target, representative low-powered-device performance, hosted multi-MSP control-plane isolation, supported encrypted backup/key-loss tooling, attachment malware quarantine, a public GitHub Wiki, an external timestamp authority, or a qualified legal electronic signature.

## Consequences

- `0.3.0` is a release boundary, not another documentation feature slice.
- Future changes to the documentation data model, dialect, authorization, rendering, files, or publication format must extend the dedicated certification composition and update the governing ADRs.
- Credential-reference and inventory work may begin at `0.3.1` without treating customer credential values as part of the certified documentation trust boundary.
- Local certification evidence may be recorded, but hosted checks, tags, images, attestations, Wiki publication, and deployments require separate authorization.
