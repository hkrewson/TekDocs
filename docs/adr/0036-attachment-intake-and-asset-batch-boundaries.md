# ADR 0036: Attachment intake and asset batch boundaries

- Status: Accepted for `0.3.10`

## Context

Managed attachments were private, bounded, signature-checked, and forced to download, but bytes entered managed storage before any replaceable scanning boundary existed. Inventory also had stable addressable assets without an asset-focused relationship workflow or a safe bounded batch mutation contract.

## Decision

Attachment intake uses two provider-neutral interfaces: an opaque storage provider and a content scanner. Bytes first receive a randomized quarantine key that contains no authored filename. The scanner receives bounded bytes plus the server-derived media type. Only a clean result may promote those exact checksum-verified bytes to an opaque managed key and create a `DocumentAttachment`. A rejection, scanner exception, integrity mismatch, promotion failure, or database failure deletes quarantine and managed remnants and creates no downloadable attachment.

The built-in scanner is deliberately conservative. It detects executable/polyglot signatures and the standard antivirus test marker, rejects active PDF features, validates complete image containers, rejects text control bytes, and inspects ZIP central-directory metadata without extraction. ZIP limits cover member count, total expanded size, compression ratio, encryption, symbolic links, traversal, and nested archives. It is not represented as equivalent to a maintained signature engine; deployments may replace it through the scanner interface without changing document records or routes.

Every managed attachment records its storage-provider ID, clean status, scanner engine, and scan time. Downloads, template copies, and STATIC publication reads require clean status, use the configured provider, and recheck size plus SHA-256 before returning bytes. Existing attachments migrate as clean under the earlier strict-validation contract.

Asset relationships remain normal `EntityLink` rows. Asset search adds the `client_asset` type, while workspace visibility limits candidates to MSP-owned assets in MSP context or exact-client assets in client context. The asset workflow offers `related_to`, `depends_on`, and `references`; the existing relationship view/create/archive permissions and MFA requirements remain authoritative.

Bulk asset mutation accepts 1–100 unique stable asset Entity IDs, resolves and locks the complete exact-workspace set before changing anything, and runs in one transaction. `set_hardware_state` permits non-disposal states and appends the normal lifecycle/audit evidence for each changed asset. `archive` soft-archives the asset and Entity, refuses software with active license coverage/seats, and enters the normal recoverable recycle-bin flow. Any invalid, stale, sibling, mixed-type, or dependency-blocked selection rolls back the whole request.

## Consequences

- Quarantined bytes never have an application download route or canonical Markdown identity.
- External object storage and stronger scanners can replace adapters, but provider migration, asynchronous retry administration, and a scanner-operations surface remain stabilization/deployment work.
- Bulk disposal is intentionally excluded because each disposal requires specific date, method, reason, and terminal-state review.
- CSV transfer remains `0.3.11`; it must call these same asset services rather than bypassing batch limits or relationship policy.
