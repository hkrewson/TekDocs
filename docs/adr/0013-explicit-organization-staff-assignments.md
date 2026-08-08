# ADR 0013: Explicit organization MSP staff assignments

Status: accepted for `0.1.10`

## Decision

Represent per-client MSP access with one tenant-owned assignment from an active `TenantMembership` to an `Organization`. The assignment targets the authenticated membership identity, never a Person record, contact email, employment association, job title, or free-form name.

An assignment is necessary only when the organization uses `assigned_only`; it is never sufficient authorization. The central policy service first resolves the member's tenant role and requested permission, then applies the organization access mode and explicit assignment, and finally enforces the permission's MFA requirement. The installation owner retains break-glass access without an assignment.

Assignment administration requires the dedicated `organizations.assign_staff` permission, enrolled TOTP, CSRF, tenant-scoped member and organization lookups, and value-free audit events. Adding an existing assignment and removing a missing assignment are idempotent so safe retries cannot create duplicate edges or misleading audit entries.

PostgreSQL enforces one tenant across the assignment, organization, and tenant membership and rejects identity/ownership mutation. The unique organization/member edge prevents duplicates. Workspace discovery, direct routing, domain APIs, entity search, and relationship traversal consume the same policy-filtered organization boundary.

## Consequences

- Assignment does not alter a tenant role, elevate a permission, satisfy MFA, or make a user a client-portal identity.
- Client Administrator and Client User remain catalog definitions only. Custom roles and tenant-, organization-, and collection-scoped role grants remain `0.1.11`–`0.1.12`.
- Assignments may be retained while an organization uses `all_authorized`, allowing a later switch to `assigned_only` without rebuilding the intended staff list.
- Removing the final assignment is allowed because the owner always retains break-glass access.
