# ADR 0101: Read-only NinjaOne observation connector

- Status: accepted
- Date: 2026-09-03

## Decision

TekDocs integrates with NinjaOne as a read-only observer. NinjaOne remains authoritative for RMM operations. The adapter uses a dedicated OAuth client-credentials application with only the Monitoring scope and exposes no mutation, script, patch, policy, automation, remote-access, or control operation.

The connector observes organizations, locations, device status, computer-system inventory, operating systems, device health summaries, and installed software through bounded opaque pagination. It retains only an explicit safe projection. Fingerprints are calculated from that projection, so an excluded provider field is neither stored nor able to create a false change signal. Access tokens remain in memory; the encrypted client secret is the only credential retained by TekDocs.

## Identity and reconciliation

Provider observations are not TekDocs records. An operator must accept the NinjaOne organization mapping before a device belonging to that organization is eligible for a suggestion. Locations require a unique name or code inside that accepted organization. Hardware requires a unique serial identifier and manufacturer match. Hostnames are display context only and never identity. Software uses a device-scoped digest of name and publisher and can be suggested only after the device's organization is known.

Candidates are stored as tenant-validated suggestions, not accepted local links. Every changed, unmatched, ambiguous, or removed record remains reviewable. Acceptance creates or advances an external-identity mapping and its fingerprint without changing the local entity. A second remote identity cannot silently claim a local entity already mapped for that record type. Provider absence never archives or deletes TekDocs inventory.

## Failure behavior

Provider access uses the shared approved-egress boundary, safe error taxonomy, bounded retry and rate-limit handling, resumable cursor, idempotent observation storage, and retained dead-letter evidence. An outage leaves all local documentation and inventory unchanged. The interface identifies observed-only, suggested/review, accepted, linked, stale, and removed states without exposing raw provider responses.

The integration's data is excluded from public portals, publications, Git exports, import tasks, audit metadata, and logs except for allowlisted aggregate metrics and safe provider error codes.

## Consequences

NinjaOne can enrich an MSP's inventory review without turning TekDocs into an RMM or granting it operational authority. Matching deliberately favors false negatives over false positives; incomplete or ambiguous source data therefore requires human review. Regional NinjaOne API roots remain configurable, while endpoint paths and OAuth scope remain fixed by the adapter.
