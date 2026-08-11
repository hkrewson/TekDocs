# ADR 0050: Client portal identity boundary

- Status: Accepted for `0.5.2`
- Date: 2026-08-11

## Context

Client users authenticate through the same maintained Django/allauth session machinery as MSP users, but they must not inherit the MSP application's workspace navigation or general domain APIs. Treating a client role as an ordinary tenant role would make every future endpoint responsible for remembering a second audience check.

## Decision

- A client membership is bound to exactly one active organization classified as a client. Its built-in role is `client_user` or the reserved `client_administrator`; ordinary MSP memberships carry no organization.
- Invitations carry the intended membership role and immutable organization binding. Only an authorized MSP user can issue, resend, or revoke them; acceptance keeps the existing digest-only, single-use, CSRF-protected flow.
- The authenticated context declares an explicit `msp` or `client_portal` surface and, for portal users, the one organization identity.
- The central MSP `require_permission` boundary rejects every client-portal membership regardless of its role catalog entries. Portal endpoints use a separate `require_client_portal_member` boundary and derive scope only from the membership, never a route-supplied organization.
- PostgreSQL constraints and triggers independently enforce role/scope agreement, same-tenant active-client ownership, and immutable membership and invitation organization edges.
- The browser renders a separate, minimal portal shell for client sessions. It does not construct the MSP sidebar, workspace switcher, or administrative routes.

## Consequences

The same secure session implementation can serve both audiences without making a portal account an MSP tenant user in practice. Portal document projection is deliberately added in `0.5.3`; this slice establishes identity and isolation only.
