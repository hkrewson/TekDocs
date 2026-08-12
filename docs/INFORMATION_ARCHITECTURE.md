# TekDocs workspace information architecture

This document defines which navigation families belong to the MSP and organization workspace contexts. It is a routing and ownership contract, not a claim that every listed domain is implemented.

## Context rules

- The URL is the active context. Organization routes use `/workspaces/organizations/{entity-id}/{area}`; MSP routes use `/{area}`.
- Every sidebar link is derived from the active context. An organization sidebar cannot contain an MSP route, and an MSP sidebar cannot retain an organization identifier.
- Entering an organization never grants access. The server resolves the identifier through tenant membership and policy checks before returning its capabilities.
- A client-context switcher searches only authorized organizations classified as clients. Multi-classified client organizations remain eligible. The MSP return is always a distinct parent-context action.
- The MSP-context switcher may search all authorized organization classifications so an operator can enter client or supplier workspaces.
- MSP operational pages contain only records whose owner is the installation's explicit MSP Workspace. `organization IS NULL` is a guarded scope projection of that owner, not an ownership default and never an implicit cross-client aggregate. Any future portfolio reporting requires a separate permission-aware projection.
- Vendor, manufacturer, and partner classifications remain capabilities on one organization identity. They are not separate tables or tenant boundaries.
- Access Control is an MSP-administration route available only when the authenticated policy context includes member-role administration. It lists built-in role definitions, tenant members, and each organization's MSP-staff access mode. It is not carried into an organization sidebar.
- `assigned_only` organizations require explicit MSP staff assignments. Additive custom tenant, organization, and access-collection roles are composed by the central policy service, but never create or bypass that staff-access edge. Entity audience defaults to MSP private; client-visible projections require explicit classification and exact organization ownership. Sensitive cost fields are omitted unless `costs.view` is granted for the active scope.

## Navigation matrix

| Area | MSP workspace | Client workspace | Supplier workspace | Delivery |
| --- | --- | --- | --- | --- |
| Overview | MSP operational summary | Selected client summary | Selected supplier summary | route available |
| Organizations | All clients, vendors, manufacturers, and partners | — | — | records available |
| People | MSP employees and shared contacts | Client employees and contacts | Supplier representatives | records available (`0.1.5`) |
| Sites | MSP offices and nested locations | Client sites, buildings, floors, rooms, offices, and desks | Supplier sites and offices | records available (`0.1.6`) |
| Custom fields | MSP-wide definitions and values on MSP records | Inherited MSP definitions plus client-local Site/Location definitions | Inherited MSP definitions plus supplier-local Site/Location definitions | definitions and Site/Location values available (`0.1.7`) |
| Relationships | Typed links and backlinks among visible MSP records | Client-owned records plus explicit links to eligible organization anchors | Supplier-owned records plus explicit links to eligible organization anchors | organization relationship UI and scoped search available (`0.1.8`) |
| Access control | Built-in roles, custom tenant/organization roles, staff-access modes, and explicit per-client MSP staff assignments | — | — | custom role and scoped assignment administration available (`0.1.11`) |
| Recycle bin | Archived organizations and MSP-owned domain records | Archived records owned by the exact organization | Archived records owned by the exact supplier | records and recovery available (`0.1.13`) |
| Documentation | Categorized MSP documents and reusable templates | Categorized client-owned and explicitly referenced documents, templates, managed attachments, and Markdown transfer | Categorized supplier-owned product/support documentation and templates | categories/templates/attachments/import-export available (`0.2.6`) |
| Files | MSP-owned managed files | Client-owned and explicitly referenced files | Supplier-owned files | `0.3.10` |
| Assets | MSP-owned assets with retained supplier provenance, hardware lifecycle, software installation state, typed relationships, and bounded bulk actions | Client-owned assets with the same exact-scope workflow | — | client workflow `0.3.4`–`0.3.6`; MSP parity `0.3.8`; relationships/bulk `0.3.10` |
| Licenses | MSP-owned software entitlements, covered installations, seats, and renewals | Client-owned entitlements with the same exact-scope workflow | — | client workflow `0.3.6`; MSP parity `0.3.8` |
| Networks | MSP networks | Client networks | — | `0.5.x` |
| Domains | MSP-owned registrations, renewal responsibility, managed subdomains, DNS observations, and monitoring | Client-owned registrations, renewal responsibility, managed subdomains, DNS observations, and monitoring | — | inventory `0.7.8`; hierarchy/renewals/monitoring `0.7.9`–`0.7.11` |
| Certificates | MSP TLS endpoints and validation history related to managed domains/hostnames | Client TLS endpoints and validation history related to managed domains/hostnames | — | `0.7.12`–`0.7.13` |
| Credential references | Links to externally protected credentials; no values stored or revealed by TekDocs | Client-scoped links whose provider independently enforces vault access | — | references `0.3.1`; runtime secret injection `0.3.2` |
| Services | MSP-owned commercial contracts, providers, renewals, and permission-projected costs | Client-owned contracts with the same exact-scope workflow | Provider relationship only | client workflow `0.3.7`; MSP parity `0.3.8`; dependencies/reminders later |
| Vendors | Suppliers derived from MSP-owned retained asset provenance | Suppliers derived from retained client-asset provenance and explicit commercial-contract provider relationships | — | client projection `0.3.4`; MSP parity `0.3.8` |
| Products | Supplier-catalog entry point; aggregate view remains later | assets consume products through the Assets workflow | Supplier-owned product/model templates, versioned specifications, and client-visible STATIC publication associations | supplier workspace `0.3.3`; documentation/provenance `0.3.4` |
| Tickets | MSP service queue | Client service requests | — | post-`1.0` placeholder |
| Accounting | MSP billing, purchasing, quotes, recurring work, and expenses | — | — | post-`1.0` placeholder |
| Compliance | MSP-owned frameworks, catalogs, assignments, reusable evidence, and risk register | client-owned frameworks, exact-client assignments, reusable evidence, and risk register | supplier catalog use is not currently exposed | catalogs `0.7.1`; assignments `0.7.2`; evidence `0.7.3`; risks `0.7.4`; bundles `0.7.5` |
| Activity, integrations | MSP governance and provider administration | only explicitly client-capable governance views | only explicitly supplier-capable views when introduced | integration runtime certified `0.7.0`; activity expansion later |

## ITFlow-informed terminology

ITFlow's documentation groups assets, certificates, clients, contacts, documents/files, domains, licenses, networks, credentials, services, tickets, and vendors under client management. Its accounting area separately groups expenses, invoices, payments, products, quotes, recurring billing, and trips. TekDocs uses that separation as a product-language and navigation reference while retaining its own schema, URL-derived context, reusable-entity model, and release boundaries.

References: [ITFlow documentation index](https://docs.itflow.org/), [clients](https://docs.itflow.org/clients), [assets](https://docs.itflow.org/assets), [contacts](https://docs.itflow.org/contacts), [invoices](https://docs.itflow.org/invoices), and [products](https://docs.itflow.org/products).
