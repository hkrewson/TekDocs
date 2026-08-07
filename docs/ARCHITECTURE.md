# Architecture

## Runtime

TekDocs ships as a same-origin web application. Nginx serves the React build and proxies `/api/`, `/accounts/`, `/admin/`, and `/static/` to Gunicorn. Celery workers and the scheduler share the Django codebase. PostgreSQL is the system of record; Valkey supplies task transport and cache primitives.

The default Compose services are `db`, `valkey`, `backend`, `worker`, `scheduler`, and `frontend`. Persistent application artifacts use a storage provider: local volumes initially and S3-compatible storage later.

## Domain direction

`Tenant` is the MSP/future hosted boundary. `Entity` is the universal stable UUID and typed models attach to it. `EntityLink` supplies referential relationships without generic foreign keys. Every tenant-owned aggregate carries a tenant identifier and, where relevant, an owning organization.

Documents compose stable blocks. Block content changes only by adding immutable revisions. Placements select the latest revision or pin an exact revision. A STATIC publication resolves all dependencies and stores a signed manifest plus immutable render artifacts.

## Trust boundaries

- Browser to same-origin Django session and CSRF boundary.
- MSP users to client-scoped data.
- Client portal users to explicitly published data.
- Application to encrypted secret provider.
- Workers to untrusted external integrations.
- Application to uploaded files and rendered Markdown/PDF.

Authorization is centralized and deny-by-default. Database scoping and constraints backstop application policies; they do not replace them.
