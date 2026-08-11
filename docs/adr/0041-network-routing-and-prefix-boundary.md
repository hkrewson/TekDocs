# ADR 0041: Network routing and prefix boundary

- Status: Accepted for `0.4.2`
- Date: 2026-08-11

## Context

Subnet inventory is unsafe if CIDRs are only presentation strings or if overlap is checked without a shared routing context. MSPs also legitimately reuse RFC 1918 space across isolated VRFs, so a tenant-wide uniqueness rule would be incorrect. VLAN identity is Layer 2 metadata and cannot safely be treated as an implicit routing namespace.

## Decision

- `NetworkVRF`, `NetworkVLAN`, and `NetworkSubnet` are exact-Workspace typed records with stable Entities. MSP records use the installation's explicit MSP Workspace and never aggregate client prefixes.
- A VLAN ID is 1–4094 and unique inside one Workspace. A subnet contains one canonical IPv4 or IPv6 network prefix, its server-derived family, an optional same-Workspace VRF, and an optional same-Workspace VLAN.
- Null VRF means the Workspace's default routing table. The default table and every explicit VRF are independent overlap namespaces. Any containment, equality, or partial intersection inside one namespace is rejected; the same prefix in different VRFs is valid.
- VLAN association does not change overlap semantics. Multiple non-overlapping IPv4/IPv6 prefixes may refer to one VLAN.
- Writes take a transaction advisory lock derived from tenant, Workspace owner, and VRF/default identity before checking existing prefixes. PostgreSQL repeats that lock and validates canonical CIDR, address family, entity/ownership edges, and overlap so direct and concurrent writes fail closed.
- Exact MSP/client routes apply `networks.view` and MFA-backed `networks.edit`, forced RLS, and the authenticated route inventory. No automatic prefix normalization silently changes submitted host bits; validation returns the canonical network as operator guidance.

## Consequences

The next address/interface slice can assign individual addresses against stable canonical parent prefixes without redefining isolation. Prefix moves between VRFs may fail until conflicts are resolved deliberately. Route distinguisher is retained as operator metadata in this slice; BGP semantic validation and reconciliation remain later integration work.
