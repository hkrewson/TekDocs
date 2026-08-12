# ADR 0055: Notification digests, quiet hours, and delivery administration

Date: 2026-08-11

Status: Accepted

## Decision

The existing SMTP queue remains the sole notification-mail state machine. At dispatch time, currently authorized due items are grouped by recipient account and surface into batches of at most 25. Fixed autoescaped digest templates receive only permission-filtered title/message projections in memory. A deterministic batch Message-ID supports correlation while preserving the documented at-least-once crash window.

Per-surface preferences choose immediate, next-hour, or daily delivery. Daily and quiet-hour boundaries use a validated IANA time zone; quiet windows may cross midnight and defer pending delivery without incrementing attempts. Authorization and preferences are reevaluated before every claim.

Delivery administration is tenant-wide, MSP-only, metadata-only, and gated by the central MFA-required `notifications.manage` permission. Only dead-letter rows may be returned to pending. Each retry requires an operator reason, increments a retry generation, and creates append-only audit evidence in the same transaction. PostgreSQL accepts the terminal transition only when matching evidence exists.

## Consequences

- Hourly/daily delivery is a digest schedule, not a guarantee that an SMTP server will accept mail at that instant.
- TekDocs stores schedule preferences and delivery metadata, but never a destination address or rendered digest.
- Quiet time delays notification mail; it does not affect security or invitation-link transactional email.
- Delivery administrators can see account display names, organization labels, topics, state, timestamps, safe error codes, attempts, and retry generation. They cannot inspect notification content from this surface.
- Provider bounce/DSN ingestion and long-history delivery analytics remain future integration and stabilization work.
