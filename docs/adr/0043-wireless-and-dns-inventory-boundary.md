# ADR 0043: Wireless and permission-aware DNS inventory

- Status: Accepted for `0.4.5`
- Date: 2026-08-11

## Context

Wireless documentation becomes dangerous if an inventory form quietly turns into another password vault. DNS records can expose client topology even when they appear operationally harmless, and loose owner/value fields can create contradictory or cross-client data. TekDocs also needs to distinguish maintained inventory from active DNS authority or monitoring.

## Decision

- `WirelessNetwork`, `DNSZone`, and `DNSRecord` are addressable records owned by one exact MSP or organization Workspace. The central `networks.view` and MFA-backed `networks.edit` permissions, permission inventory, database scope binding, and forced RLS protect every list, detail, and mutation route.
- A wireless record stores an SSID, purpose, security mode, lifecycle state, hidden/client-isolation posture, and optional same-Workspace site, VLAN, and subnet. SSIDs retain exact case and are limited to 32 UTF-8 bytes. A selected subnet must belong to the selected VLAN.
- TekDocs does not accept a PSK, RADIUS password, or other wireless credential. Operators use external credential references when access material must be documented; this slice does not add a provider pointer to the wireless schema.
- A DNS zone and every record name use lower-case ASCII/IDNA canonical form without a trailing dot. An owner must be the zone apex or a descendant. Supported records are A, AAAA, CNAME, MX, TXT, SRV, CAA, NS, and PTR with bounded, type-aware fields.
- A/AAAA records may retain a stable same-Workspace `NetworkIPAddress` link, and the linked value must match. CNAME cannot coexist with another record at the same owner. DNS writes share a Workspace advisory lock so conflict checks remain atomic.
- Application services provide specific validation guidance; PostgreSQL independently guards entity type, exact ownership edges, SSID byte length, VLAN/subnet consistency, canonical zone ownership, IP links, and CNAME conflicts.

## Consequences

Wireless posture and DNS values are searchable only after exact Workspace authorization and are available in both MSP and client contexts without cross-client aggregation. TekDocs is not a DNS server, resolver, Wi-Fi controller, secret custodian, live configuration validator, or certificate monitor in this slice. Live DNS/certificate observation remains in the later domain-monitoring milestones.
