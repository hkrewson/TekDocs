# ADR 0012: Central policy service and built-in roles

Status: accepted for `0.1.9`

## Decision

TekDocs authorizes implemented operations through one maintained permission catalog and policy service. Callers request a stable permission key and an optional route-resolved organization; they never branch on a role name. The service resolves installation membership, the built-in role, organization access mode, and MFA requirement, then either returns a scoped decision context or denies without disclosing inaccessible records.

The installation owner is an immutable bootstrap identity and implicitly receives every catalog permission. Tenant memberships may use Administrator, Technician, Contributor, or Read-only. Client Administrator and Client User are defined now so product language and permission intent remain stable, but they cannot be assigned as tenant-wide roles. `0.1.10` adds an explicit MSP staff access edge; organization-scoped role grants remain a later RBAC slice.

Existing and newly accepted memberships default to Read-only. Role changes require the `memberships.assign_role` permission, enrolled TOTP, tenant scoping, a tenant-assignable target role, and a different non-owner target identity. They create value-free audit events.

Every organization records one MSP-staff access mode:

- `all_authorized`: a tenant member may enter only when their role also grants the requested permission;
- `assigned_only`: the installation owner retains break-glass access, while non-owners are denied until explicit user-to-organization assignments are implemented in `0.1.10`.

The mode is an additional hard constraint, never a permission grant. Workspace discovery and direct routes use the same policy-filtered organization queryset so UUID knowledge, backlinks, and stale client state cannot bypass it.

## Consequences

- Permission names become an API and audit-review contract; changes require tests, documentation, and compatibility review.
- MFA is permission metadata enforced centrally, not a repeated view convention.
- Frontend capability hiding may improve navigation but is never authoritative.
- This release deliberately does not add custom roles, organization/collection role grants, explicit deny rules, or client-portal identities. Explicit MSP staff access assignments arrive in `0.1.10`; role composition remains `0.1.11`–`0.1.12`.
- PostgreSQL integrity guards and scoped managers remain active, but runtime-role RLS remains `0.1.12`.
