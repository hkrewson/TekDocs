# ADR 0044: Network circuits, contracts, handoffs, and lifecycle dates

- Status: Accepted for the deferred `0.4.4` scope, delivered in chronological build `0.4.6`
- Date: 2026-08-11

## Context

An MSP needs circuit identity, provider and agreement provenance, demarcation placement, and renewal/disconnect awareness without turning the Network page into a financial report or a credential store. Because `0.4.5` was completed before the deferred `0.4.4` slice, the repository must also preserve monotonic application versions.

## Decision

- `NetworkCircuit` and `NetworkCircuitHandoff` are addressable records owned by one exact MSP or organization Workspace. The central `networks.view` and MFA-backed `networks.edit` permissions, permission inventory, database scope binding, and forced RLS protect every route.
- A circuit uses one active same-tenant organization classified as vendor, manufacturer, or partner. It may link one active commercial contract only when contract Workspace and provider match the circuit. New selections exclude archived providers, while retained provider identity remains available as provenance. A linked contract cannot be archived.
- A circuit stores a provider-scoped service identifier, type, lifecycle status, directional bandwidth, installation/service/review/disconnect dates, and bounded non-secret description. The provider/service identifier pair is unique within one Workspace.
- A handoff records A or Z side, media, connector, provider reference, and optional exact-Workspace site, location, device, and interface placement. Location requires its site, interface requires its device, device placement cannot contradict the selected site, and one interface can terminate at most one handoff.
- Review and planned-disconnect dates are projected with derived overdue/today/upcoming state. Contract renewal notice, renewal, and end projections require `assets.view`. Circuit responses never project `ContractCost` or another financial field.
- These are deterministic reminder inputs only. Email, in-app delivery, recurrence, acknowledgements, and preferences belong to the later transactional notification subsystem.
- Strict serializers reject unknown and password-shaped fields. Service identifiers and provider references stay out of audit metadata and broad Entity labels. Application validation is backed by PostgreSQL relationship triggers, uniqueness constraints, advisory locks, and forced RLS.
- The deferred scope ships as application version `0.4.6`; future network slices move forward rather than downgrading the already shipped `0.4.5` version.

## Consequences

Operators can document provider circuits and exact demarcations in MSP and client contexts, see permission-aware upcoming lifecycle dates, and retain contract provenance without leaking costs or storing access secrets. Active monitoring, provider API verification, invoice processing, automated notifications, diagrams, NetBox reconciliation, recycle-bin support, and final scale certification remain later work.
