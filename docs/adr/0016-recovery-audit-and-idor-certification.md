# ADR 0016: Recovery, audit immutability, and IDOR certification

Status: accepted for `0.1.13`

## Decision

TekDocs provides a workspace-scoped recycle bin for ordinary domain records whose current lifecycle already uses archival: organization anchors, person associations, sites, location subtrees, and custom-field definitions. Audit events, authentication lifecycle rows, access-control configuration, and relationship edges are retained through their existing history or recreation contracts and are not general recycle-bin records. STATIC publications remain permanently append-only when introduced.

Recycle-bin discovery derives its MSP or active-organization scope from the route. It never accepts tenant or organization ownership from the request body. A record is listed only when the caller has `recycle_bin.view`, the record type's read permission, and the applicable organization reachability. Recovery additionally requires `recycle_bin.restore`, the record type's existing archive or management permission, and MFA. All decisions remain in the central policy service.

Site archival is one cascade batch identified by the site's archive timestamp. Recovering a site restores the site and only descendant locations carrying that exact timestamp; locations archived earlier remain archived. Location recovery similarly restores one exact-timestamp subtree and requires an active site and active parent outside that subtree. Person associations require any retained structured site/location dependencies to be active. Stale, conflicting, missing-dependency, and guessed-identifier attempts fail atomically and non-disclosingly.

Audit events are insert-only evidence. PostgreSQL rejects every UPDATE or DELETE on the audit table through a trigger, including ORM bulk operations, raw SQL, foreign-key cascades, and future accidental maintenance code. TekDocs supplies no application bypass or retention endpoint. Destructive schema/table administration, including `TRUNCATE`, remains within the trusted database-owner boundary.

A maintained permission/IDOR inventory enumerates every implemented authenticated route family and its read/mutation permission, scope shape, identifier shape, MFA requirement, and CSRF expectation. A blocking parameterized suite consumes that inventory and supplements existing domain-specific semantic tests. New route families must enter the inventory before the entity/RBAC subsystem can be certified at `0.2.0`.

## Consequences

- Recovery is not a generic unarchive flag and cannot bypass the domain permission that authorized archival.
- Archived organization workspaces are restored from the MSP recycle bin because an archived workspace cannot be selected safely.
- Restoring a parent never revives a descendant that was archived in an earlier, separate operation.
- Audit retention or legal deletion, if ever required, needs a separately reviewed operator mechanism and cannot be added as an ordinary API.
- Relationship recreation and access-control configuration recovery remain explicit workflows rather than ambiguous recycle-bin ownership.
