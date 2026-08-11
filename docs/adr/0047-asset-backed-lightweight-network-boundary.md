# ADR 0047: Asset-backed lightweight network boundary

- Status: Accepted for `0.4.9`
- Date: 2026-08-11

## Context

The early network slices deliberately modeled interfaces and VRFs so their ownership, validation, and migration behavior could be evaluated. Product review established a smaller boundary: TekDocs should document the common MSP facts—physical assets and racks, VLANs, subnets, IP and MAC addresses, wireless/DNS, circuits, and external NetBox identity—while NetBox remains the home for detailed DCIM/IPAM.

An unbacked `NetworkDevice` also duplicated physical identity. A missing organization or asset edge could make placement operationally ambiguous. Removing the earlier tables would be destructive and would break retained exports, publications, integrations, and upgrades.

## Decision

- Every newly created network-device record must reference one active hardware asset in the exact Workspace. PostgreSQL independently rejects unbacked inserts and forged/cross-Workspace/non-hardware edges.
- IP and MAC records may point directly to an active exact-Workspace hardware asset. New browser/API workflows use that edge; a legacy interface edge remains readable and is checked for agreement when both are present.
- Interfaces and VRFs disappear from ordinary navigation and new subnet forms. Their models, rows, internal compatibility APIs, search/export projections, and relationships remain intact for migration and recovery.
- Migration marks pre-existing unbacked devices explicitly as `legacy_unbacked` and backfills direct IP/MAC asset ownership when an old interface resolves through an asset-backed device. It never guesses from names or deletes a row.
- A legacy device can be repaired by selecting an asset; it cannot be newly created, stripped of its asset, or returned to legacy state.
- NetBox identifiers remain references only. This change neither adds a connector nor migrates deep network data automatically.

## Consequences

Physical identity now belongs to inventory and network placement augments it rather than duplicating it. Common address workflows are shorter and permission-aware. Existing Interface/VRF-era data stays reversible and exportable, but ordinary operators are not encouraged to maintain a partial NetBox clone. Later removal of compatibility tables, if ever proposed, requires a separately authorized export/migration and deprecation release.
