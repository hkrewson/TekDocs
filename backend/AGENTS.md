# Backend Invariants

- Every tenant-owned model and query is tenant-scoped. Organization-scoped data must also enforce its client boundary.
- All authorization decisions go through the policy service. Do not scatter role-name checks through views, serializers, tasks, or templates.
- Every permission change requires allow, deny, cross-tenant, and cross-client tests.
- Use maintained libraries for authentication and cryptography. Never invent password hashing, token formats, encryption modes, or signature formats.
- Secret plaintext may exist only inside the secret provider and explicit reveal boundary. It must never enter logs, search, exports, task payloads, audit metadata, or list responses.
- Static publications and audit events are append-only.
- External HTTP activity must use the approved egress service with redirect, address, timeout, and size controls.
- Schema changes require normal Django migrations plus fresh-install and upgrade-path tests.
- A new model carrying a `tenant` foreign key must be assigned a reviewed boundary in `apps/core/rls_contract.py` and `apps/core/validation.py` in the same commit as its migration.
- A test that mutates schema, roles, or privileges shared by the rest of the session must restore that state in fixture teardown or `finally`, never only on the success path. Restore to migration head, never to a pinned revision.
- New runtime dependencies require maintenance, vulnerability, and license review.
