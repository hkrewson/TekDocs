# ADR 0018: Entity and RBAC certification boundary

- Status: Accepted for `0.2.0`
- Date: 2026-08-09

## Decision

TekDocs maintains one explicit inventory for every Django model carrying a tenant foreign key. Each table is assigned to exactly one of three boundaries: forced-RLS entity-domain data, the authorization control plane, or the installation singleton. Certification fails when model discovery and this inventory differ, when the RLS subset differs from the active policy inventory, or when an ordinary tenant-owned model lacks the fail-closed scoped manager.

Entity-domain data remains protected by the non-owner runtime role and forced `USING`/`WITH CHECK` policies. Invitations, memberships, organization staff assignments, access collections, custom roles, permissions, and scoped assignments remain outside RLS because they establish identity, tenant context, reachability, or policy before a domain scope can be selected. The installation singleton similarly anchors bootstrap and server-derived tenant discovery.

The control-plane exception is not an absence of database enforcement. PostgreSQL makes membership tenant/user identity and invitation tenant/email/issuer identity immutable. Invitation issuers and accepters, organization-assignment creators, collection creators, custom-role creators, and scoped-assignment creators must belong to the same tenant. Existing triggers continue to enforce role ceilings, same-tenant organization/member/role/collection edges, assignment target shape, owner exclusion, and immutable authorization identities. Application paths use scoped managers and the central permission service, and the complete route/IDOR matrix tests every unsafe route method for insufficient-role and MFA denial.

`make test-certification` runs model-boundary, permission-catalog, control-plane integrity, authenticated-route, IDOR, and raw runtime-role checks against PostgreSQL. The migration-cycle gate reverses and reapplies both the latest control-plane guard migration and active RLS migration while proving representative authorization and domain state survives.

## Consequences

- A newly added tenant-bearing model cannot silently omit its isolation classification.
- Raw writes cannot retarget membership or invitation ownership across tenants or attribute authorization administration to a foreign user.
- RLS remains focused on client/entity domain data without creating a circular dependency during invitation redemption or tenant establishment.
- `0.2.0` certifies one MSP per installation. It does not certify hosted multi-MSP control-plane reads; that topology requires a separately reviewed identity and database isolation boundary before it can ship.
- Every future domain family must extend the inventory, route permission contract, negative isolation cases, migration fixture, and relevant performance dataset.
