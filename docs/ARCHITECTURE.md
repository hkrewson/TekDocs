# Architecture

## Runtime

TekDocs ships as a same-origin web application. Nginx serves the React build and proxies `/api/`, `/accounts/`, `/admin/`, and `/static/` to Gunicorn. Celery workers and the scheduler share the Django codebase. PostgreSQL is the system of record; Valkey supplies task transport and cache primitives.

The default Compose services are `db`, `valkey`, `backend`, `worker`, `scheduler`, and `frontend`. Persistent application artifacts use a storage provider: local volumes initially and S3-compatible storage later.

## Domain direction

`Tenant` is the MSP/future hosted boundary. `Entity` is the universal stable UUID and typed models attach to it. `EntityLink` supplies referential relationships without generic foreign keys. Every tenant-owned aggregate carries a tenant identifier and, where relevant, an owning organization.

`EntityLink` types are selected from a maintained catalog with forward/inverse labels, target-type rules, and canonical handling for symmetric links. Relationship reads resolve both outgoing links and incoming backlinks through the same URL-derived workspace visibility service used by bounded Entity search. An organization workspace may discover active MSP-owned organization anchors for explicit relationships, but never sibling-owned child records. PostgreSQL guards same-tenant endpoints, empty metadata, immutable identity, canonical symmetry, and immutable archival. ADR 0011 defines the full relationship and search contract.

`Person` is one tenant-wide human identity attached to an MSP-scoped `Entity`. `PersonAssociation` records employment or contact context in exactly one URL-selected workspace: a null organization is the MSP, while a non-null organization is that client or supplier. Descriptive role and responsibility fields never grant permissions. Database triggers reject person/entity/organization tenant mismatches, and ordinary reads use the same fail-closed scoped manager contract as other organization-owned records. ADR 0008 defines future user linkage and client-assignment policy.

`CustomFieldDefinition` supplies a stable MSP-wide or organization-specific key for one Entity type. Immutable `CustomFieldDefinitionVersion` rows contain server-generated JSON Schema and presentation metadata. Entity values remain in the existing `Entity.custom_fields` JSON object as a strict envelope containing the exact validating version ID, sequential version number, and value. PostgreSQL guards enforce tenant, organization, target-type, version, and envelope consistency; application validation provides operator-friendly errors. MSP definitions are inherited by matching organization-owned entities, while organization definitions never cross their owning workspace. ADR 0010 defines the complete versioning and inheritance contract.

`Site` is an addressable MSP- or organization-owned facility with address, timezone, phone, and operator code metadata. `Location` is an addressable building, floor, suite, room, office, desk, or area in one site's parent-child tree. Database triggers enforce identical workspace scope across entity, site, location, and parent records and reject hierarchy cycles. Person associations can reference an active site/location while retaining free-text location and office snapshots for unmapped imports and historical display. ADR 0009 defines this placement contract.

Tenant-owned domain reads use explicit scoped managers. Omitting the tenant from a scoped manager fails before SQL is issued; organization-scoped queries match both the tenant and the exact selected organization, with null representing MSP-owned data. An `Organization` record is the stable scope anchor attached to an MSP-scoped `Entity`. Its normalized classifications allow the same business to act as a client, vendor, manufacturer, partner, or any valid combination without duplicating identity. Archive-on-delete retains the entity and its inbound references for the later recycle-bin workflow.

Organization CRUD is initially restricted to the installation owner with MFA through the central authentication policy boundary. This is a conservative temporary policy, not an inline role decision; the permission catalog and scoped role assignments replace it in the dedicated RBAC slices.

Workspace context is an explicit URL and query boundary, not ambient authorization stored in a browser or server session. The MSP workspace selects tenant-owned records whose organization scope is null. An organization workspace selects that organization's owned records through both tenant and organization identifiers after policy authorization. Organization anchor records remain MSP-owned so they can be discovered and selected without making their child data visible. Opening separate browser tabs in different workspaces cannot alter either tab's scope.

The shell derives its workspace label and available sections from organization classifications. A multi-classified organization receives the union of applicable navigation capabilities and displays every applicable classification; vendor, manufacturer, and partner are retained as classifications rather than separate table hierarchies. Hidden navigation is only presentation—every endpoint, worker, search result, backlink, export, and creation path independently enforces the selected scope.

PostgreSQL scope helpers consume transaction-local tenant, organization, and organization-mode settings. Same-tenant organization anchors, entity ownership, and entity-link endpoints are protected by database triggers. RLS policies are not yet enabled for the runtime role: ADR 0006 defines the staged activation work required before that defense can be claimed.

Documents compose stable blocks. Block content changes only by adding immutable revisions. Placements select the latest revision or pin an exact revision. A STATIC publication resolves all dependencies and stores a signed manifest plus immutable render artifacts.

## Trust boundaries

- Browser to same-origin Django session and CSRF boundary.
- MSP users to client-scoped data.
- Client portal users to explicitly published data.
- Application to encrypted secret provider.
- Workers to untrusted external integrations.
- Application to uploaded files and rendered Markdown/PDF.

Authorization is centralized and deny-by-default. Database scoping and constraints backstop application policies; they do not replace them.
