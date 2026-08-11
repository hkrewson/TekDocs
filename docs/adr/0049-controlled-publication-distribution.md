# ADR 0049: Controlled publication distribution

- Status: Accepted for `0.5.1`
- Date: 2026-08-11

## Context

An immutable signed STATIC snapshot is retained evidence, but retention alone does not answer whether that snapshot is currently approved for an audience. Treating `client_visible` as immediate portal authority would let one publisher both create and distribute client-facing material. Mutating the signed publication to record approval, withdrawal, or correction would invalidate its evidence contract.

## Decision

- `DocumentPublication` and its signed artifacts remain immutable. Distribution decisions are separate append-only `DocumentPublicationControlEvent` rows with an actor, bounded reason, action, and timestamp.
- Every publication receives a `submitted` event. `msp_internal` snapshots receive an automatic `approved` event from the publisher. `client_visible` snapshots remain `pending_approval` until a different user with `documents.approve` records approval. Approval and withdrawal require recent MFA through the central policy service.
- `documents.publish`, `documents.approve`, and `documents.withdraw` are distinct permissions and may be assigned at tenant, exact-organization, or collection scope. Scope, client assignment mode, and MSP-private constraints continue to compose with those grants.
- Lifecycle state is derived from the ledger: `pending_approval`, `published`, `review_due`, `withdrawn`, or `superseded`. Withdrawal removes audience availability but never deletes or rewrites the snapshot, manifest, PDF, attachments, or prior decisions.
- MSP staff with source-workspace access retain the evidence projection for every state. The future client portal projection is available only when a client-visible publication is approved, not withdrawn, and not superseded.
- A correction must retain the predecessor's document, Workspace, and audience. Creating the correction does not supersede the predecessor; approval does. At most one approved successor may supersede a publication. A withdrawn or unapproved attempt does not permanently prevent a later correction.
- PostgreSQL advisory locks serialize decisions for a publication and its predecessor. Database triggers independently enforce event order, separation of duties, one approved successor, scope agreement, and append-only behavior. Forced RLS protects the ledger and preserves only the already-reviewed narrow supplier-publication projection.
- Existing publications are backfilled as submitted and approved at their original publication time so an upgrade does not silently withdraw material that was already treated as available.

## Consequences

The application can now distinguish immutable evidence from current distribution authority without changing signed content. A later portal may consume the explicit projection instead of interpreting audience labels itself. Rejection as a separate terminal event, quorum approval, scheduled publication, and client acknowledgement are not part of `0.5.1`; adding any of them requires a new ledger decision and policy review.
