# ADR 0035: Explicit workspace ownership identity

- Status: Accepted for `0.3.9`

## Context

TekDocs supports one MSP per installation. `Tenant` remains the installation boundary and a future hosted-tenancy seam, but nullable organization scope alone made MSP ownership indistinguishable from an accidentally omitted organization identifier. That ambiguity could silently misattribute a failed client create to the MSP and made retention behavior after organization removal less obvious.

## Decision

Every tenant has exactly one stable MSP `Workspace`; every `Organization` has exactly one stable organization `Workspace`. Every universal `Entity` has a required workspace foreign key. The Entity is the canonical ownership anchor for documents, blocks, assets, products, licenses, contracts, and later addressable domains; typed rows retain tenant/organization columns for direct indexing, RLS, and relationship validation rather than duplicating another ownership key.

The tenant is not presented as a collection of MSPs, and this change does not claim hosted multi-MSP isolation. Public routes retain their existing stable MSP and organization identifiers. The route resolver binds the corresponding internal workspace UUID together with tenant and organization scope.

Creation must either provide the route-resolved workspace or call the explicit owner-resolution factory. Ordinary `Entity.objects.create()` has no ownership default and fails at the non-null database boundary when workspace is omitted. PostgreSQL also rejects a workspace whose tenant/organization shape does not exactly match the Entity.

Workspace identity is immutable and cannot be deleted. Organizations remain archive-first records; their row, entity, workspace UUID, and all owned records remain linked while archived. The protected workspace relationship prevents physical organization deletion and therefore prevents ownership orphaning.

## Consequences

- `organization IS NULL` remains a useful denormalized MSP-scope predicate, but it is no longer the ownership identity.
- A client create that loses its organization route context cannot become MSP-owned merely because a nullable column was omitted.
- Existing installations receive deterministic MSP and organization workspaces before the Entity workspace column becomes non-null.
- The workspace table is authorization control-plane data: it is resolved before domain RLS can be bound, uses a fail-closed scoped manager, and has database identity guards. Domain Entities remain under forced RLS.
- Any future SaaS topology requires a separate hosted control-plane review; keeping `Tenant` avoids a schema rewrite but does not certify that topology.
