# TekDocs Product Charter

TekDocs is a self-hosted, documentation-first MSP knowledge and inventory platform. Its defining capability is addressable, reusable information: documents compose immutable-revision content blocks, and every domain object has a stable identity that can be referenced elsewhere without copying it.

## 1.0 success criteria

- One MSP installation can securely organize client organizations, people, vendors, assets, software, networks, credentials, documentation, compliance evidence, and reminders.
- Live block reuse updates every authorized placement; pinned references and STATIC publications remain unchanged.
- The Documentation index begins as a title-first list. A live document title links to its editable source; an immutable STATIC publication title opens that retained publication instead.
- Every document has one authoritative ownership scope: the MSP or one client organization. An MSP-owned document may be referenced into any number of client Documentation indexes without copying it or changing its owner.
- Invited client users see only explicitly published or assigned information for their organization.
- PostgreSQL is the canonical transactional and revision store. Git is an optional sanitized export target.
- A fresh Docker install, upgrades, backup/restore, and security gates are documented and reproducible.
- The public code remains open under AGPL-3.0-only.

## Product boundaries

Knowledge and inventory are the 1.0 release line. The integration framework is required, but named third-party connectors are stretch work. Full appointment scheduling, bidirectional MDM/IPAM/asset connectors, SNMP monitoring, ticketing, billing, anonymous trust portals, and a hosted multi-MSP control plane are post-1.0.
