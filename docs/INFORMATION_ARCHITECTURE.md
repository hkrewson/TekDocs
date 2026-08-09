# TekDocs workspace information architecture

This document defines which navigation families belong to the MSP and organization workspace contexts. It is a routing and ownership contract, not a claim that every listed domain is implemented.

## Context rules

- The URL is the active context. Organization routes use `/workspaces/organizations/{entity-id}/{area}`; MSP routes use `/{area}`.
- Every sidebar link is derived from the active context. An organization sidebar cannot contain an MSP route, and an MSP sidebar cannot retain an organization identifier.
- Entering an organization never grants access. The server resolves the identifier through tenant membership and policy checks before returning its capabilities.
- A client-context switcher searches only authorized organizations classified as clients. Multi-classified client organizations remain eligible. The MSP return is always a distinct parent-context action.
- The MSP-context switcher may search all authorized organization classifications so an operator can enter client or supplier workspaces.
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
| Documentation | MSP-owned documentation | Client-owned and explicitly referenced documentation | Supplier-owned product/support documentation | `0.2.x` |
| Files | MSP-owned managed files | Client-owned and explicitly referenced files | Supplier-owned files | `0.3.8` |
| Assets | MSP-owned equipment | Client equipment and software | — | `0.3.5`–`0.3.8` |
| Licenses | MSP entitlements | Client entitlements and seats | — | `0.3.6` |
| Networks | MSP networks | Client networks | — | `0.5.x` |
| Domains | MSP-owned registrations, renewal responsibility, managed subdomains, DNS observations, and monitoring | Client-owned registrations, renewal responsibility, managed subdomains, DNS observations, and monitoring | — | inventory `0.7.8`; hierarchy/renewals/monitoring `0.7.9`–`0.7.11` |
| Certificates | MSP TLS endpoints and validation history related to managed domains/hostnames | Client TLS endpoints and validation history related to managed domains/hostnames | — | `0.7.12`–`0.7.13` |
| Credentials | MSP-protected secrets | Client-protected secrets | — | `0.3.1`–`0.3.2` |
| Services | MSP services and contracts | Client services, providers, and dependencies | — | relationship seam in `0.3.7` |
| Vendors | MSP supplier directory/relationships | Vendors related to the client through assets or services | — | `0.3.4` |
| Products | MSP-visible supplier catalog | — | Supplier-owned product/model templates | `0.3.3` |
| Tickets | MSP service queue | Client service requests | — | post-`1.0` placeholder |
| Accounting | MSP billing, purchasing, quotes, recurring work, and expenses | — | — | post-`1.0` placeholder |
| Compliance, activity, integrations | MSP governance and provider administration | only explicitly client-capable governance views when introduced | only explicitly supplier-capable views when introduced | later roadmap slices |

## ITFlow-informed terminology

ITFlow's documentation groups assets, certificates, clients, contacts, documents/files, domains, licenses, networks, credentials, services, tickets, and vendors under client management. Its accounting area separately groups expenses, invoices, payments, products, quotes, recurring billing, and trips. TekDocs uses that separation as a product-language and navigation reference while retaining its own schema, URL-derived context, reusable-entity model, and release boundaries.

References: [ITFlow documentation index](https://docs.itflow.org/), [clients](https://docs.itflow.org/clients), [assets](https://docs.itflow.org/assets), [contacts](https://docs.itflow.org/contacts), [invoices](https://docs.itflow.org/invoices), and [products](https://docs.itflow.org/products).
