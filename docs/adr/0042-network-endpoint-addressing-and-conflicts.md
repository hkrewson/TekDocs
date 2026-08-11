# ADR 0042: Network endpoint addressing and conflicts

- Status: Accepted for `0.4.3`
- Date: 2026-08-11

## Context

An interface, host address, or MAC record is useful only when its ownership and assignment edges remain trustworthy. Duplicate-address checks also need the same routing boundary and transaction serialization as parent subnet changes. Globally unique IPs would reject normal MSP use of overlapping private space in separate VRFs; treating VLANs as routing namespaces would hide real conflicts.

## Decision

- `NetworkInterface`, `NetworkIPAddress`, and `NetworkMACAddress` are addressable exact-Workspace records with stable Entities. An interface belongs to one device. An IP belongs to one subnet and may reference one interface. A MAC may reference one interface.
- IP input must be the canonical compressed IPv4/IPv6 host representation. Its family is derived. It must be contained by its parent prefix; IPv4 network and broadcast identifiers are rejected unless `/31` or `/32` host semantics apply.
- An address is unique within the Workspace's default routing table or one explicit VRF. The same address may exist in separate VRFs. VLAN identity does not affect conflicts.
- MAC input is canonical lowercase colon-separated EUI-48 and unique across one Workspace. EUI-64 and vendor enrichment remain outside this slice.
- Interface names are case-insensitively unique on one device. A shared namespace advisory lock serializes IP writes with subnet writes, and device-scoped locks serialize interface naming. PostgreSQL independently guards canonical form, exact ownership edges, containment, reserved identifiers, and conflicts.
- Prefix changes fail if they would exclude or reserve an existing host, or move an address into conflict. Errors remain bounded and do not reveal records in another Workspace.

## Consequences

Endpoint assignments have a durable IPAM contract suitable for later DNS, wireless, diagram, and NetBox reconciliation slices. This is inventory and conflict detection, not active discovery, DHCP authority, switch-port telemetry, or an assertion that a recorded address is reachable.
