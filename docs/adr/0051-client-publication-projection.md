# ADR 0051: Fail-closed client publication projection

- Status: Accepted for `0.5.3`
- Date: 2026-08-11

## Context

An approved client-visible STATIC publication is immutable evidence, but its stored HTML and entity cards were resolved under the publisher's MSP permissions. Approval of the document does not authorize every referenced record. An MSP-owned document listed in a client workspace is likewise a staff navigation convenience, not a client access grant.

## Decision

- Portal queries derive one organization from membership and return only exact-organization, client-visible publications with an approval, no withdrawal, and no approved successor.
- New approval fails unless every retained entity reference belongs to that organization and is explicitly `client_visible`.
- The portal repeats the reference check. An unsafe historical snapshot remains immutable MSP evidence but is absent from portal list, detail, and artifact routes.
- Portal HTML comes from the retained server-sanitized snapshot and passes through the browser sanitizer again. Artifacts are forced attachment downloads with private/no-store and nosniff headers.
- `DocumentationListingReference` does not grant portal access. MSP-owned reference documents need a future explicit immutable per-client projection with its own approval.

## Consequences

The portal is a narrow distribution projection, not another view of the documentation database. Some historical documents may require a safe correction before clients can see them; this is preferable to silently exposing reference-card data.
