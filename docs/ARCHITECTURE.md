# Architecture

## Runtime

TekDocs ships as a same-origin web application. Nginx serves the React build and proxies `/api/`, `/accounts/`, `/admin/`, and `/static/` to Gunicorn. Celery workers and the scheduler share the Django codebase. PostgreSQL is the system of record; Valkey supplies task transport and cache primitives.

The default Compose services are `db`, `valkey`, `backend`, `worker`, `scheduler`, and `frontend`. Persistent application artifacts use a storage provider: local volumes initially and S3-compatible storage later.

## Domain direction

`Tenant` is the MSP/future hosted boundary. `Entity` is the universal stable UUID and typed models attach to it. `EntityLink` supplies referential relationships without generic foreign keys. Every tenant-owned aggregate carries a tenant identifier and, where relevant, an owning organization.

Tenant-owned domain reads use explicit scoped managers. Omitting the tenant from a scoped manager fails before SQL is issued; organization-scoped queries match both the tenant and the exact selected organization, with null representing MSP-owned data. An `Organization` record is the stable scope anchor attached to an MSP-scoped `Entity`. Its normalized classifications allow the same business to act as a client, vendor, manufacturer, partner, or any valid combination without duplicating identity. Archive-on-delete retains the entity and its inbound references for the later recycle-bin workflow.

Organization CRUD is initially restricted to the installation owner with MFA through the central authentication policy boundary. This is a conservative temporary policy, not an inline role decision; the permission catalog and scoped role assignments replace it in the dedicated RBAC slices.

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
