# Phase 8 responsive workspace recovery acceptance

Checkpoint date: 2026-09-25. Version: 0.8.46. This record covers backup,
clean restore, and supported-source upgrade acceptance for the ten broad workspace
routes. The final release-candidate gate remains open.

## Passed recovery boundaries

- **Assets and Contracts:** the inventory rehearsal created hardware and software
  assets, lifecycle details, licensing, a contract with cost data, a credential
  reference, CSV-imported inventory, and managed attachment bytes. PostgreSQL and
  media were backed up separately, restored into clean volumes, and verified through
  scoped queries under the retained owner identity.
- **Networks:** the network rehearsal retained rack/device bindings, interfaces,
  IP and MAC assignments, VLANs/subnets, wireless, DNS, circuit/handoff data,
  NetBox identity, search/export behavior, and exact organization ownership through
  a clean database and media restore.
- **Documentation and Files:** the documentation rehearsal retained revision and
  placement history, primary-file versions, attachments, signed publication state,
  PDF output, diagram SVG/PNG artifacts, and a regenerable export after restore.

The final runs of `make inventory-backup-rehearsal`,
`make network-backup-rehearsal`, and `make documentation-backup-rehearsal` passed
against isolated disposable stacks. Existing user and demo data were untouched.

## Passed upgrade boundaries

- **Assets and Contracts:** retained 0.3.12 inventory, licensing, contract,
  credential-reference, imported-record, and managed-file data migrated to 0.8.46
  and passed scoped verification, system checks, and migration-drift checks.
- **Networks:** retained 0.4.9 network inventory, addressing, endpoint, wireless,
  DNS, circuit, reconciliation, search/export, and ownership state migrated to
  0.8.46 and passed the same current-system checks.
- **Documentation and Files:** retained 0.2.8 document identity, revision history,
  attachment bytes, signed publication manifest, and PDF artifact migrated to
  0.8.46 and remained verifiable.

The upgrade fixtures now detect whether the source release supports explicit RLS
principals. Older source installations use their native scope behavior to create
authentic old-schema data; current verification binds the retained owner as an
explicit user principal. This keeps one fixture valid on both sides of the upgrade
without weakening current authorization checks.

## Rehearsal corrections

The inventory and network fixtures predated explicit RLS principals. They could
write their setup rows but could not read a newly created organization asset back
through the current user-aware policy. The fixtures now bind the bootstrapped owner
as the user principal for both setup and restored-data verification. This matches
an authorized technician request instead of bypassing policy with a system scope.

Clean restore projects also relied on an older Compose behavior that happened to
build the diagram-renderer dependency while targeting the backend. The scripts now
build both local images explicitly before creating the backend and restoring its
managed media volume. This makes the restore independent of images left by another
Compose project and keeps the media volume owned by the restore project.

## Remaining boundary

`acceptance.json` records all four groups as recovery `complete`; both listed
backup and upgrade rehearsals have passed. The production-image rehearsal is
recorded separately and also passes. Phase 8 still requires the human technician/
assistive-technology record, final release gate, and release approval. Deployment
remains separately authorized.
