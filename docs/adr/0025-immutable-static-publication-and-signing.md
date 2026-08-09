# ADR 0025: Immutable STATIC publication and signing

- Status: Accepted for `0.2.7`
- Date: 2026-08-09

## Context

Live and pinned block composition preserves authoring history, but a legal, policy, or evidence record needs one retained artifact whose meaning no longer follows any mutable source. A checksum alone can detect accidental change but cannot prove that TekDocs produced the retained content with the deployment's publication key.

## Decision

STATIC is an immutable `DocumentPublication`, not a mutable state on `Document`. Publishing locks the source document long enough to resolve its ordered placement tree to exact `BlockRevision` rows. It resolves every stable entity mention to the publisher-authorized server projection and every managed attachment reference to active metadata owned by that source document. Any unresolved, foreign, archived, or malformed dependency aborts the transaction. The source remains editable after publication.

The publication stores canonical Markdown, sanitized HTML rendered from frozen projections, and a versioned manifest. The manifest includes the new publication identity, source document/workspace identity, title/category, ordered placement/revision records, resolved entity projections, referenced attachment metadata, publisher identity, and publication timestamp. Canonical JSON is UTF-8 with sorted keys and compact separators. A length-delimited snapshot payload binds the canonical Markdown, sanitized HTML, and canonical manifest without relying on ambiguous concatenation.

TekDocs computes SHA-256 over that payload, then signs the 32-byte digest using Ed25519 from the maintained `cryptography` library. The deployment supplies a URL-safe-base64 raw 32-byte private key through `TEKDOCS_PUBLICATION_SIGNING_KEY`; TekDocs derives and retains the raw public key plus its SHA-256 fingerprint with each publication. Neither the private key nor authored labels enter the database, API, audit metadata, or logs. Key-file injection and rotation operations remain assigned to `0.3.2`; retaining the public verification material allows old publications to remain verifiable after a later signing-key rotation.

Publication rows are append-only through model methods and PostgreSQL triggers. Detail views render only the stored sanitized HTML and expose stored snapshot metadata plus a fresh verification result. Markdown and manifest downloads are forced, private, and `nosniff`. PDF generation, audience/reason metadata, corrections, supersession, attachment-byte artifact retention, and publication lifecycle workflows remain `0.2.8`.

## Consequences

- A publication is a point-in-time record; it never receives subsequent source edits.
- The signature proves possession of the deployment key at publication time, not a person's legal electronic signature or an external timestamp authority.
- Referenced attachment bytes remain in managed storage and are not embedded in this release's signed payload; their immutable identifier, checksum, media type, size, and filename are signed. Retained byte packaging and PDF artifacts arrive in `0.2.8`.
- Losing the signing private key prevents new publications but does not prevent verification of retained publications because each stores its public key.
