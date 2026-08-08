# ADR 0008: People associations and access assignments

- Status: Accepted
- Date: 2026-08-08

## Decision

Represent each human once as a tenant-owned `Person` anchored to a stable Entity. Represent employment and contact context separately as a scoped `PersonAssociation`. An association belongs either to the MSP (`organization = NULL`) or to exactly one organization and carries relationship type, role or responsibility, location label, and office. Phone, email, full name, and preferred name remain on the person identity in `0.1.5`.

The active URL workspace selects associations, not arbitrary people. MSP People returns only MSP associations; an organization People route returns only associations for that authorized organization. A person associated with multiple organizations therefore appears in each permitted context without duplicating their identity. Creating a record in `0.1.5` creates a new person plus one association. Attaching an existing person is deferred to the typed-link/search foundation so accidental identity merging is not introduced early.

Role and responsibility are descriptive business data and never grant application permissions. Future account linkage associates a Person with an authenticated User explicitly. Client access policy and RBAC assignments target User identities, never names, email strings, job titles, or Person records.

Each client will ultimately declare one of two access modes:

- all MSP users holding the required tenant permission may access it; or
- only specifically assigned MSP users holding the required permission may access it.

The policy service will combine that hard client-assignment boundary with tenant/client/collection role assignments, MSP-private classification, and field permissions. Assignment is necessary but never sufficient permission. These controls remain `0.1.9`–`0.1.10`; until then People administration uses the existing installation-owner-plus-MFA boundary.

Location is an intentionally migration-safe text label in `0.1.5`. The `0.1.6` Sites and Locations slice adds an optional structured reference while preserving the label for rooms, desks, remote locations, and imported values that do not map cleanly to a site record.

## Consequences

- Person identity can be reused without using an EAV model or copying contact details.
- Editing identity-level phone or email will eventually need an impact preview when shared-person attachment becomes available.
- Workspace list, detail, create, update, archive, search, filter, and sorting paths must all apply the same association scope.
- Database guards must reject cross-tenant person and organization associations even if application scoping is bypassed.
- Future list-column preferences are presentation data only and cannot reveal a field the API did not authorize.
