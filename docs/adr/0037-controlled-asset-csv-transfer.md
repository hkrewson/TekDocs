# ADR 0037: controlled asset CSV transfer

- Status: Accepted for `0.3.11`

## Decision

TekDocs owns a versioned, exact-header asset CSV contract beginning with `tekdocs.assets.v1`. It is a bounded operational transfer format, not a database dump or a generic spreadsheet mapper. The first contract includes stable asset/model identity, display name, hardware identity/acquisition/warranty state, and software installation state. It deliberately excludes assignments, disposal, licenses, costs, contracts, attachments, credential references, secrets, and internal provenance payloads.

Import requires an `assets.edit`-authorized server dry run and a second apply request. A short-lived Django-signed preview token binds the exact file digest, resolved Workspace UUID, and normalized action digest. Apply reparses and revalidates the file inside one transaction; a changed file, workspace, catalog state, or expired token requires a new preview. New rows carry an operator-stable `import_key`; UUIDv5 under the Workspace identity makes retry target the same Entity. Existing rows use `asset_id`. Imports may update mutable fields but never change retained supplier/model provenance.

Files are UTF-8 CSV with an exact header, at most 1 MiB, 500 rows, and 500 characters per cell. Unknown, duplicate, reordered, or extra columns; malformed CSV; null bytes; invalid UUIDs/dates/enums; cross-workspace IDs; duplicate identifiers; and unavailable models fail closed. Export uses `assets.view`, resolves one exact Workspace, emits only the contract allowlist, and prefixes spreadsheet-formula-shaped cells. Template export contains headers only.

## Consequences

The canonical format is predictable, testable, and secret-safe, but it is intentionally less convenient than accepting arbitrary spreadsheets. Vendor-specific columns and mappings require a later named adapter/profile boundary and sanitized samples; they do not weaken the canonical parser. A preview is advisory until apply, so apply repeats every authorization and validation decision and remains atomic.
