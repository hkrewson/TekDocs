# ADR 0015: Access collections and visibility policy

Status: accepted for `0.1.12`

## Decision

An access collection is a tenant-owned authorization grouping of organizations. It is not a documentation folder, tag, generic Entity collection, or ownership boundary. Collection membership points only to active organizations in the same tenant. Archiving a collection retains its membership and scoped assignments for history but immediately stops every grant derived from it.

A custom role may have immutable `tenant`, `organization`, or `collection` assignment scope. A collection-scoped assignment adds its permissions while authorizing an organization that is an active member of the selected collection. It never creates an organization staff assignment, changes `assigned_only` reachability, grants access to the collection itself, or changes record ownership. Adding or removing an organization from a collection changes effective permission composition immediately without rewriting role assignments.

Every universal Entity carries one server-maintained audience classification: `msp_private` by default or explicitly `client_visible`. The central audience policy applies this as a hard upper bound after tenant and organization ownership checks. MSP staff still require their normal permission and workspace reachability. A future client-portal projection must be both `client_visible` and owned by that exact organization; an MSP-owned reference requires an explicit publication/reference projection rather than raw Entity visibility. No role, including Owner, converts MSP-private data into client-visible output.

Sensitive fields use a separate central field-policy catalog. `cost` maps to `costs.view`; projection helpers omit denied keys instead of returning placeholders or nulls. `costs.view` becomes custom-assignable in this slice so a tenant, exact-organization, or access-collection role can grant cost visibility without exposing secrets or unrelated sensitive fields. Actual cost records remain in `0.3.7`.

Collection, visibility, role, and assignment administration remains owner-plus-MFA and CSRF protected. Tenant and scope identifiers are resolved server-side, and audit events contain no names, membership lists, permission sets, visibility values, or field values.

## Consequences

- Access collections solve reusable organization group authorization without consuming the future documentation-collection namespace.
- Permission grants, organization reachability, record ownership, audience visibility, and field visibility remain independent policy stages.
- Entity visibility is a conservative floor. Domain projections may add stricter rules later, but may never weaken `msp_private`.
- Client portal identities and visibility-management workflows remain in their owning portal/domain milestones; this slice establishes the stored classification and mandatory policy boundary.
- Explicit deny rules are unnecessary for `TD-RISK-001`: tenant/client isolation, assigned-only reachability, MSP-private audience classification, and sensitive-field policy are hard constraints evaluated after additive grants.
