# ADR 0046: Network search, export, and stabilization boundary

- Status: Accepted for `0.4.8`
- Date: 2026-08-11

## Context

Network records were available only through separate family pages. Operators need one fast way to locate a known address, prefix, SSID, DNS record, circuit, rack, or device without weakening the exact MSP/client Workspace boundary. They also need a portable technical snapshot for review and recovery. A generic model serializer would be unsafe: it could silently acquire contracts, costs, hardware-only details, provider observations, or future secret-shaped fields, and an in-memory export would not remain bounded.

## Decision

- One read-only search endpoint resolves the Workspace and central `networks.view` permission before applying an allowlisted cross-family query. Search text is limited to 200 characters, pages to 100 rows, ordering is stable, and responses return only stable identity, label, type, and owning UI section—not the field that matched.
- One export-only `tekdocs.networks.v1` CSV contract uses a fixed column allowlist and fixed family order. It iterates each exact-Workspace queryset in batches, escapes spreadsheet formulas/control characters, and never serializes model dictionaries.
- Because Django consumes a streaming response after request middleware has returned, the CSV iterator owns a read transaction and binds the exact Workspace through transaction-local PostgreSQL RLS for its complete lifetime. It does not inherit or rely on the request transaction.
- Export includes technical network descriptions and relationship labels needed to understand the snapshot. It excludes credential references, contract identifiers/details, costs, hardware-asset-only fields, arbitrary provider payloads, and NetBox fingerprints. NetBox identity export is limited to content type and numeric identifier.
- Search and export use the same explicit MSP-owned or organization-owned scope as the family endpoints. MSP does not mean tenant-wide aggregation. Both routes are in the authenticated permission/IDOR inventory and use private, non-cacheable responses.
- This release adds no import path, model family, outbound connector, remote credential, or synchronization authority.

## Consequences

Operators gain a useful discovery and portable-review surface without turning CSV into a second write API or expanding NetBox trust. Adding a future field or family requires deliberate search and export allowlist review. A download holds a bounded, read-only-intent database transaction while it streams; future very-large exports should move to scoped asynchronous artifacts rather than weakening the RLS lifetime. The 100-client/10,000-network-Entity PostgreSQL fixture, fixed query ceilings, streamed-response assertion, production-image upgrade, and independent restore rehearsal become recurring network certification evidence.
