# NetBox provider-failure repair

Date: 2026-11-15

Status: implemented and locally verified

## Scope

Repair the post-1.0 NetBox synchronization path without expanding the supported
Networks product boundary. The provider remains read-only during ordinary sync,
credentials remain encrypted, and TekDocs continues to enforce exact Workspace
and routing-namespace ownership.

The reproduced failure had three local causes after a valid provider response:

- automatic linking resolved an open reconciliation record without its required
  resolver identity;
- a nested NetBox prefix raised TekDocs' overlap rule and rolled back the entire
  provider page;
- automatic device projection attempted to create supplier catalog records while
  the worker remained bound to the client Workspace.

## Acceptance

- A repeated NetBox observation can close its prior open conflict with the sync
  actor, resolution time and immutable evidence intact.
- A non-overlapping prefix still creates and links a CIDR automatically.
- A nested or otherwise overlapping prefix remains an unmatched review item and
  does not prevent independent prefixes or devices from synchronizing.
- A new NetBox device can create its manufacturer catalog records in that
  supplier's exact Workspace, restore the worker's client scope, then create the
  client asset and device.
- PostgreSQL runtime-role coverage exercises the catalog scope transition.
- Provider errors remain sanitized; no credential or provider payload enters a
  job, log, test artifact or user-visible error.

## Unreleased notes

NetBox synchronization no longer reports a generic `provider_failure` for valid
responses that encounter an existing reconciliation item, nested prefix or new
device catalog model. Overlapping prefixes remain reviewable because TekDocs does
not become a full IPAM or weaken its non-overlapping routing-table invariant.

Version remains 1.0.0. This repair does not authorize publication, deployment or
production data changes.

## Verification

- The three PostgreSQL regressions failed before the implementation and pass after
  it, including the constrained runtime-role catalog transition.
- The broader integration, integration-stabilization, error-boundary and network-
  addressing suites pass in the existing database service.
- Ruff, focused mypy, Wiki validation and diff hygiene pass.
- A real local sync using the retained encrypted credential completed both pages:
  seven prefix observations and 39 device observations. The connection finished
  healthy, recorded a successful sync and cleared its error code.
- The adapted integration gate reached one unrelated, reproducible failure in
  `test_native_key_evidence_blocks_schema_rollback_without_changing_custody`.
  That test intentionally reverses the schema to core migration 0219, then its
  current fingerprint helper queries `core_repositorytemplateenrollment`, which
  is introduced by migration 0221. The same failure reproduces when run alone;
  it does not exercise the NetBox implementation or changed tests.

Six nested prefixes remain open for review as intended. A separate retained backlog
of 1,270 IP-address and six VLAN review items predates the corrected five-view
network boundary. This repair does not delete that history; any cleanup requires a
separate report-first migration and operator disposition.
