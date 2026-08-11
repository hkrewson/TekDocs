# ADR 0045: NetBox identity and reconciliation boundary

- Status: Accepted for `0.4.7`
- Date: 2026-08-11

## Context

TekDocs should retain common MSP documentation without becoming a second DCIM/IPAM. NetBox already provides the deeper interface, VRF, cable, device-component, and automation model. Copying that schema would increase authorization, migration, conflict, and drift risk while producing two competing sources of truth. TekDocs still needs stable cross-system identity so an operator can link ordinary documentation to NetBox and later review observed differences safely.

NetBox's REST contract identifies an object by its Django content type (`app_label.model`) plus a positive numeric primary key. A URL is a deployment detail, not object identity. Arbitrary remote JSON is also an unsafe persistence format because it can silently expand to secrets, customer values, or provider-specific schema.

## Decision

- `NetBoxReference` belongs to one explicit Workspace and maps one active TekDocs Entity to one NetBox content type and numeric object ID. Both the local Entity and remote identity are unique among active mappings in that Workspace.
- The initial mapping allowlist is intentionally narrow: racks, hardware Assets represented as NetBox devices, MAC addresses, VLANs, prefixes, and IP addresses. Interface and VRF records are excluded from new mappings. DNS has no corresponding NetBox core object in this contract.
- Application validation, an explicit Workspace foreign key, PostgreSQL relationship guards, forced RLS, and central `networks.view`/MFA-backed `networks.edit` policy enforce the mapping boundary. MSP routes remain MSP-owned rather than cross-client aggregates.
- Reconciliation input is a bounded normalized observation containing only content type, numeric ID, and a caller-computed lowercase SHA-256 fingerprint. Preview is read-only and deterministically reports current, changed, unmatched, or missing-remote state. It stores no arbitrary provider payload and makes no external request.
- This slice stores no NetBox base URL or token. Later connection configuration must use the integration provider, secret-file/encrypted configuration, egress/SSRF, job, retry, cursor, and conflict-review contracts. Preview does not establish either system as automatically writable.
- Linking and unlinking affect only TekDocs mapping metadata. They never create, update, or delete a NetBox object, and unlinking never deletes the local TekDocs record.

## Consequences

TekDocs can retain durable links before a live connector exists without committing to NetBox's full schema. The next network slice can simplify ordinary TekDocs workflows around hardware Assets and direct lightweight address ownership while preserving existing pre-1.0 data deliberately. A future connector can discover remote records and feed normalized fingerprints into the same preview seam, but write-back requires a separately reviewed milestone.
