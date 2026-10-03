# Networks legacy-data cleanup rehearsal

Status: complete with compatibility records intentionally retained
Rehearsed: 2026-10-03
Authority: [`docs/adr/0104-corrected-network-documentation-and-reviewed-netbox-publication.md`](../docs/adr/0104-corrected-network-documentation-and-reviewed-netbox-publication.md)

## Disposition

TekDocs must not delete the retained rack, VLAN, VRF, interface, circuit or
handoff records at the `0.9.0` boundary. They remain necessary for upgrades,
exports and recovery, and ADR 0104 permits only lossless projection backfills
until a separate deprecation and operator-approved migration is designed and
rehearsed. This is the exact retained state for issue #99, not an unrecorded
cleanup deferral.

The `rehearse_network_model_cleanup` command now runs under an explicit
organization-scoped system principal, remains report-only by default and emits
value-minimized JSON covering supported rows, every retained legacy record
type, legacy relationships, eligible backfills, unresolved relationships,
conflicts and the destructive-removal disposition. `--apply` stops atomically
on a conflict and otherwise performs only these stable-FK projections:

- legacy VLAN to the supported network VLAN number;
- legacy rack placement to retained source-placement facts;
- interface/device asset identity to the IP-address asset projection; and
- interface/device asset identity to the MAC-address asset projection.

It does not clear a legacy foreign key or delete a row, entity or audit event.

## Production-shaped inventory

The isolated fixture contains one organization workspace with one supported
network, device, IP address and MAC address. Its retained compatibility
inventory is one rack, VLAN, VRF, interface, circuit and circuit handoff, with
one subnet-to-VLAN, subnet-to-VRF, device-to-rack, IP-to-interface and
MAC-to-interface relationship. The handoff is device-linked, so the expected
handoff-to-interface count is zero. A sibling workspace report returns no rows,
proving the command does not aggregate across organizations.

The fresh current-version rehearsal reported four eligible lossless backfills,
zero unresolved asset relationships and zero blockers. After apply, the fixture
retained every compatibility row and relationship while the VLAN number, rack
facts, IP asset and MAC asset projections matched their stable source links.

## Recovery and upgrade evidence

- `make network-backup-rehearsal` passed. It created the fixture in an isolated
  production-shaped stack, previewed and applied the four projections, captured
  PostgreSQL and managed media separately, destroyed the source volumes,
  restored into independently named clean volumes, and revalidated ownership,
  relationships, search/export behavior, projected assets and system health.
- `make network-upgrade-rehearsal` passed from `0.4.9` to `0.9.0`. The upgraded
  fixture reported the same exact legacy inventory, three remaining eligible
  projections (the migration had already populated the VLAN number), zero
  unresolved relationships and zero blockers. Apply, search/export, ownership,
  Django system checks and migration-drift checks all passed.
- Focused integration tests pass for report-only behavior, exact inventory,
  sibling-workspace isolation, IP and MAC projection, rack/VLAN projection and
  preservation of the original legacy links.

No development or production workspace was mutated during these rehearsals.
Future destructive compatibility removal is outside the current 1.0 plan and
requires its own deprecation decision, migration, export review, authorization
review and recovery evidence.
