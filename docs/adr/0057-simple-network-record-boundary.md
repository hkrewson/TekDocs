# ADR 0057: Simple network record and physical-asset boundary

- Status: Accepted for `0.5.10`
- Date: 2026-08-11
- Supersedes the ordinary product surface in ADRs 0040–0048; their compatibility, isolation, and database-safety decisions remain applicable to retained rows.

## Context

The certified `0.5.0` network subsystem still exposed its internal schema as product navigation: racks, devices, individual addresses, subnets, VLANs, circuits, wireless, DNS, and manual NetBox identities. Hiding only Interfaces and VRFs did not make that surface lightweight. It asked an MSP operator to maintain a partial NetBox clone and duplicated physical identity outside Assets.

The intended TekDocs workflow is smaller. An operator records a network, not every possible host address. Physical objects—including racks, switches, firewalls, and access points—are Assets. NetBox remains optional integration authority for deeper DCIM/IPAM.

## Decision

- The ordinary API and browser surface call the existing stable prefix-backed entity a **Network**. It owns a structured location, name, description, optional VLAN number, canonical CIDR, calculated gateway, full or explicit assignable range, two DNS resolver addresses, and notes.
- Gateway and full usable range are projections, not editable duplicate values. IPv4 uses the first usable host except `/31` and `/32`, which follow the prefix's actual address set. Explicit ranges must be complete, ordered, same-family, contained, and must not include reserved IPv4 network or broadcast identifiers.
- The existing `NetworkSubnet` table and Entity IDs are extended in place. Legacy VLAN/VRF relationships, individual addresses, services, circuits, racks/devices, search/export data, and NetBox identities are retained behind compatibility APIs. No rows are guessed, reassigned, or deleted.
- MAC addresses are authored as repeatable fields of one exact-Workspace hardware Asset and use asset view/edit permissions. The retained canonical address table remains the implementation seam so existing stable IDs and uniqueness guards survive.
- Ordinary Networks navigation no longer offers separate racks, devices, IP/MAC addresses, VLANs, subnets, circuits, wireless/DNS objects, or NetBox links. New racks and network appliances are created as hardware Assets. Any future rack-placement UI must extend Assets rather than create a competing physical-object identity.
- NetBox connection settings and reconciliation will be delivered only through the provider-neutral integration boundary. Manual identity APIs remain compatibility-only until that connector exists.

## Consequences

The product surface now matches the common MSP documentation task and avoids requiring host-by-host inventory. PostgreSQL still preserves and guards previously certified data. This leaves deliberate compatibility debt: old granular routes and tables remain callable by existing clients and exports. Removing or transforming them requires deprecation, operator-visible export, upgrade/restore proof, and a separately authorized migration.
