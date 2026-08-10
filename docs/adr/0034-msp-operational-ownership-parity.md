# ADR 0034: MSP operational ownership parity without client aggregation

- Status: Superseded in ownership identity by ADR 0035; operational parity remains accepted
- Date: 2026-08-10

## Decision

The installation MSP is an operational data owner but is not modeled as a client organization. In `0.3.8`, an MSP-owned operational record carried the installation tenant and a null organization, while a client-owned record carried the same tenant plus exactly one client organization. ADR 0035 subsequently made both owners explicit Workspaces. The `organization IS NULL` predicate is now only the guarded projection of the MSP Workspace, not the owner identity and not every row in the tenant.

Assets, retained supplier provenance, hardware lifecycle, software installations and licenses, commercial contracts and protected costs use one owner-neutral service and persistence contract. Existing internal `Client*` model names remain temporarily for migration compatibility, but do not define ownership semantics. New public routes use `/api/v1/workspaces/msp/...` or `/api/v1/workspaces/organizations/{id}/...`, and the browser selects the route family from the explicit workspace kind.

Supplier catalogs remain organization-owned reference data. MSP asset creation receives a narrow, read-only PostgreSQL RLS projection of supplier catalog rows and only the client-visible STATIC publications explicitly associated with those products. This projection does not expose any client-owned operational row. Null-safe database comparisons (`IS NOT DISTINCT FROM`) enforce every owner edge, and serial/tag uniqueness treats the null MSP owner as a real uniqueness partition.

Catalog publication and entity membership is evaluated by narrowly granted `SECURITY DEFINER` predicates with `row_security = off` and a fixed `search_path`. RLS policies call those boolean predicates instead of joining other protected tables directly; this avoids recursive policy evaluation while preserving tenant, workspace-mode, audience, and catalog-association checks.

## Consequences

- The MSP can document its own equipment, software, entitlements, providers, agreements, costs, and supplier relationships with the same workflows available to clients.
- MSP routes are not reporting or aggregation surfaces. Cross-client summaries require a future separately permissioned projection and must never be inferred from tenant scope.
- A future model/API terminology cleanup may rename internal `Client*` classes to owner-neutral names, but it must be a behavior-preserving migration with no scope change.
- Network and domain models must adopt this owner-neutral scope from their first migration rather than repeating the client-only topology.
