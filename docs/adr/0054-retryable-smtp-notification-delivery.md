# ADR 0054: Retryable SMTP notification delivery

Date: 2026-08-11

Status: Accepted

## Decision

New inbox projections create one separate SMTP delivery row. The row identifies the tenant, organization, inbox notification, recipient account, and surface, but never copies an email address or rendered message. A scheduled dispatcher claims bounded work, repeats installation membership and notification authorization, checks the current surface preference, resolves the current account address in memory, and sends fixed autoescaped text/HTML through the central email boundary.

Temporary transport failures retry with bounded exponential backoff. Synchronous permanent recipient failures dead-letter. Revoked authority or disabled preferences suppress delivery. Only allowlisted error codes are retained. Delivery identity is immutable, terminal states are append-only, preferences cannot be deleted, and both tables use forced tenant RLS with membership/scope guards.

## Consequences

- SMTP downtime cannot block domain commits or the in-app inbox.
- Existing inbox rows are not backfilled during upgrade, preventing stale surprise email.
- Preferences are deliberately immediate and surface-specific; batching, digest schedules, quiet time, and administration remain `0.5.7`.
- SMTP has an at-least-once crash window after remote acceptance and before the database marks success. A stable Message-ID aids correlation but is not a deduplication guarantee.
- TekDocs handles synchronous SMTP rejection. Later asynchronous bounce/DSN ingestion requires a provider integration and is not claimed here.
