# ADR 0040: Network racks, devices, and placement

- Status: Accepted for `0.4.1`
- Date: 2026-08-11

## Context

Network inventory must begin with physical objects that can later own interfaces, addresses, VLAN participation, and diagram relationships. A rack-unit label stored on an asset would not provide stable identity, same-Workspace validation, conflict detection, or permission-filtered backlinks. Treating the MSP route as tenant-wide inventory would also reintroduce the cross-client aggregation risk prohibited by ADR 0035.

## Decision

- `NetworkRack` and `NetworkDevice` are exact-Workspace typed records with stable Entities. MSP ownership uses the installation's explicit MSP Workspace; the nullable organization column remains only its guarded compatibility projection.
- A rack belongs to one active same-Workspace site and optional structured location. A device can be unplaced, placed at a site/location, or assigned a contiguous rack-unit range. Rack placement derives the device site/location from the rack.
- A device may point to one same-Workspace hardware `ClientAsset`. The device stores network role and placement only; serial, lifecycle, model revision, documentation provenance, and costs remain authoritative on the asset.
- API writes lock the rack before testing occupancy. PostgreSQL takes a transaction advisory lock keyed to the rack and rejects out-of-bounds or overlapping ranges, forged entity/site/location/asset edges, and rack changes that contradict placed devices.
- Logical topology reuses `EntityLink`. `connected_to` is symmetric and restricted to network-device targets; `depends_on` and general links retain their existing semantics and relationship permissions.
- List and detail routes resolve exactly one MSP or client Workspace before applying `networks.view` or MFA-backed `networks.edit`. The MSP surface never aggregates client devices.

## Consequences

The physical foundation can be referenced immediately without inventing interface or IP semantics early. Rack recovery, bulk transfer, topology diagrams, NetBox reconciliation, and network-wide scale certification remain later slices. A rack cannot be moved while devices are placed; operators must deliberately move/unplace devices first so placement history cannot silently change through a parent edit.
