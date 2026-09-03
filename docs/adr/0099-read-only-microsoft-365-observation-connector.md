# ADR 0099: Read-only Microsoft 365 observation connector

Status: accepted

## Context

MSPs need Microsoft tenant identity, domains, directory identities, license assignments, and managed-device facts beside their documentation. TekDocs must not become an identity or device-management authority, and an application credential must not create a cross-client data path or expand into mail, files, authentication methods, recovery keys, or administrative writes.

## Decision

- Microsoft 365 is a provider-registry adapter bound to one exact MSP or organization Workspace. The configured Entra tenant ID is validated against both the app-only token claim and the Graph organization response.
- Authentication uses OAuth 2.0 client credentials with the fixed Graph `.default` audience. Tenant ID and application ID are non-secret configuration; the client secret is envelope-encrypted and is decrypted only at the worker request boundary. Access tokens and Graph response bodies are never retained.
- The required application roles are `Organization.Read.All`, `User.Read.All`, `GroupMember.Read.All`, `LicenseAssignment.Read.All`, and `DeviceManagementManagedDevices.Read.All`. Verified domains come from the organization projection, avoiding an additional directory-domain permission. A digest of the consented roles detects later drift. Mail, file, authentication-method, and BitLocker-key permissions are rejected.
- The adapter records only allowlisted scalar projections for tenant identity, verified domains, users, groups and direct memberships, subscribed SKUs/user assignment counts, and Intune managed devices. Stable Graph IDs form remote identity. Raw records are hashed and discarded.
- Graph paging links and user delta links are opaque, bounded worker cursors. Initial complete collections may infer remote retirement; later user delta runs retire only explicit `@removed` records. Throttling uses bounded `Retry-After` handling and durable retries.
- Reconciliation remains observational. The connector never creates, edits, disables, licenses, deletes, or writes back to Microsoft or silently mutates TekDocs records.

## Consequences

The integration can show current, source-timestamped Microsoft facts and permission failures without copying broad tenant data. Administrators must create and maintain a dedicated app registration and Intune must be licensed for managed-device reads. Certificate credentials and delegated consent remain deferred; adding either requires a new secret-boundary and threat review.
