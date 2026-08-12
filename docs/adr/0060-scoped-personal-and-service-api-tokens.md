# ADR 0060: Scoped personal and service API tokens

Date: 2026-08-12

Status: Accepted for `0.6.2`

## Context

Integrations need durable authentication without copying browser cookies or weakening the central Workspace/RBAC boundary. A database leak must not yield usable bearer values, service automation must not become an interactive administrator, and a guessed token identifier must not expose scope or lifecycle.

## Decision

- A token is personal or service, has mandatory 1–365 day expiry, exactly one MSP or organization Workspace, and immutable permission rows selected only from non-MFA API-eligible permissions. Organization tokens also require `workspaces.view` to resolve their exact route.
- Personal tokens retain their issuing human as subject. Service issuance creates a dedicated non-interactive User with an unusable password, no staff/superuser flags, tenant Read-only membership, and exact organization assignment when applicable. Service scopes are limited to implemented reads.
- Raw material is `tdp|tds`, a random display prefix, and 256-bit URL-safe secret. It is returned only at issuance/rotation; only Django's maintained password hash is stored. Rotation replaces both prefix and hash and invalidates the old value immediately.
- Issuance/rotation requires session authentication, CSRF, enrolled TOTP, and recent allauth reauthentication. Service management requires `integrations.manage`. Bearer authentication cannot call token-management endpoints.
- Bearer resolution occurs before request-wide PostgreSQL RLS. Effective authorization is the intersection of current subject policy, immutable token permission, and exact Workspace. A token is unusable until its initial permission set is sealed. Database triggers prevent service-login broadening, cross-tenant edges, authority retargeting, expiry/secret broadening outside a new rotation generation, revocation rewriting, and permission mutation/deletion after sealing.
- Lists, audit rows, notifications, exports, schemas, logs, and browser persistence never contain raw material. Revocation emits value-free audit evidence and disables a service subject.

## Consequences

Database disclosure alone does not reveal immediately usable tokens, and revocation or current-role changes reduce access without waiting for expiry. Bearer theft still grants the bounded authority until rotation, revocation, or expiry, so TLS and client-side custody remain mandatory. The settings UI deliberately treats the returned value as transient. Usage anomaly detection, administrative scale, and final integration certification remain owned by `0.6.9` and `0.7.0` under `TD-RISK-046`.
