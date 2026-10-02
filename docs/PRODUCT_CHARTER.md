# TekDocs Product Charter

TekDocs is a self-hosted, documentation-first MSP knowledge and inventory platform. Its defining capability is addressable, reusable information: canonical Markdown documents compose canonical Markdown fragments through stable links, Git retains their revisions, and every operational domain object has a stable identity that can be referenced without copying it.

## 1.0 success criteria

- One MSP installation can securely organize client organizations, people, vendors, assets, software, networks, domains, external credential references, documentation, compliance evidence, and reminders.
- Domains are addressable MSP- or client-owned records rather than a flat checklist. Registered domains retain renewal and expiration responsibility, managed subdomains retain hierarchy and provenance, and related TLS endpoints retain validation and certificate-expiry evidence.
- An authorized MSP user can enter an organization workspace from its record, browse and create only data owned by that organization, search-switch among authorized organizations, and return to the MSP workspace without losing the active route.
- Organization classifications describe capabilities rather than separate identities: a business may be a client, vendor, manufacturer, partner, or a combination, and its workspace exposes the union of applicable areas.
- Live fragment reuse updates every authorized inclusion; pinned references resolve an exact retained Git object and STATIC publications remain unchanged.
- The Documentation index begins as a title-first list. A live document title links to its editable source; an immutable STATIC publication title opens that retained publication instead.
- Every document has one authoritative ownership scope: the MSP or one client organization. An MSP-owned document may be referenced into any number of client Documentation indexes without copying it or changing its owner.
- Invited client users see only explicitly published or assigned information for their organization.
- Managed local Git repositories are canonical for authored documentation content, portable metadata and composition. PostgreSQL is canonical for authorization, workspace binding, workflow, templates/enrollment control, managed files, retained publications, audit and operational records; its document/search/link projections are rebuildable from accepted Git commits.
- The default installation requires no GitHub or remote Git service. Repository storage is part of the supported local data store and encrypted backup/recovery boundary.
- A fresh Docker install, upgrades, backup/restore, and security gates are documented and reproducible.
- The public code remains open under AGPL-3.0-only.

## Product boundaries

Knowledge, inventory, bounded invoice issuance, recovery, and a provider-neutral integration contract are the 1.0 release line. Named connectors are tracked explicitly in the 1.0 milestone. Native ticketing/PSA, CRM, general-ledger accounting, payment processing, payroll, RMM/MDM control, anonymous trust portals, and a hosted multi-MSP control plane are excluded. `docs/PRODUCT_BOUNDARY.md` is the maintained capability matrix.
