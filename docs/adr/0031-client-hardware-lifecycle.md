# ADR 0031: Client hardware current state and lifecycle ledger

- Status: Accepted for `0.3.5`
- Date: 2026-08-10

## Decision

Each client asset whose retained catalog product is hardware receives exactly one `ClientHardwareAsset` current-state profile. The profile owns normalized serial and asset-tag identifiers, bounded acquisition and warranty metadata, an explicit lifecycle state, current person/site/location assignment, and terminal disposal metadata. Software assets do not receive this profile.

Every material mutation locks the asset and current profile in one transaction, validates exact client scope, updates the profile, and appends a `ClientAssetLifecycleEvent`. Events retain typed state and assignment identities but deliberately omit free-text references and reasons. Django and PostgreSQL reject event update/delete; PostgreSQL also rejects profile deletion, scope forgery, unnormalized identifiers, invalid assignments, and changes after disposal.

## Consequences

- Current inventory reads stay direct and indexable without reconstructing state from a long event stream.
- History is evidence of application-observed transitions, not a user-editable activity note.
- Disposal is terminal in ordinary workflows and clears current custody. A future correction workflow requires a separate reviewed decision rather than rewriting history.
- Acquisition references, warranty references, and disposal reasons remain in the current profile but out of audit metadata and lifecycle events.
- Costs, contracts, software entitlements, generic asset relationships, and bulk/file processing remain later slices.
