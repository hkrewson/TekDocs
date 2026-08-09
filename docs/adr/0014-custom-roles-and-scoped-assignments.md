# ADR 0014: Custom roles and scoped assignments

Status: accepted for `0.1.11`

## Decision

TekDocs stores tenant-owned custom role definitions separately from their normalized permission rows. A role has one immutable assignment scope: `tenant` or `organization`. Its name, description, active permission set, and archival state are editable; its tenant and scope are not.

Custom roles are additive. Every non-owner keeps one built-in tenant role as a safe baseline. Tenant-scoped assignments add permissions throughout workspaces the member may already reach. Organization-scoped assignments add permissions only while authorizing a request for that exact organization. Neither kind of assignment creates an organization staff-access edge or bypasses an `assigned_only` boundary.

Only maintained catalog permissions explicitly marked custom-assignable may enter a custom role. Installation ownership, membership and role administration, organization access administration, secret access, and cost visibility are excluded. MFA remains metadata of the central permission catalog and applies regardless of whether a permission came from a built-in or custom role.

Assignments attach to authenticated tenant memberships, never Person records or job titles. Tenant, role, membership, and optional organization must share one tenant. PostgreSQL triggers guard these relationships and the immutable assignment identity. Archived roles remain referenced for auditability but immediately stop granting permissions and cannot receive new assignments.

Role definitions, permission changes, assignments, removals, and archival use owner-plus-MFA service boundaries and value-free audit events. Browser-submitted tenant ownership, permission metadata, and assignment scope are never trusted.

## Consequences

- Built-in and custom permission composition stays inside the central policy service.
- Organization reachability and permission grants remain independent, testable conditions.
- Editing a role has immediate additive effect on every active assignment and the UI must confirm that impact.
- Explicit denies, collection scope, MSP-private classification, and field-level sensitive-data policy remain `0.1.12`.
