# Phase 8 responsive workspace recovery acceptance

Checkpoint date: 2026-09-25. Version: 0.8.46. This record covers the backup and
clean-restore half of the recovery boundary for the ten broad workspace routes.
Upgrade rehearsals and the final release-candidate gate remain open.

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

`acceptance.json` records each group as `backup_complete`. It becomes `complete`
only after its listed upgrade rehearsal passes for the release candidate. Phase 8
also requires the human technician/assistive-technology record, production-image
checks, full release gates, and release approval. Deployment remains separately
authorized.
