# ADR 0053: Permission-filtered notification inbox

- Status: Accepted for `0.5.5`
- Date: 2026-08-11

## Decision

The transactional outbox consumer creates an immutable `InboxNotification` recipient edge for each eligible active account. The row stores event, tenant, organization, recipient, surface, creation time, and mutable read time; it does not store rendered copy, email addresses, document content, publication reasons, or arbitrary payloads.

MSP recipients must currently hold the event family's read permission in the event organization. Portal recipients derive only from immutable exact-client membership. On every list or read-state request, TekDocs re-authorizes the recipient, surface, organization, topic, and source object before constructing a fixed title, message, and typed navigation target. A no-longer-authorized notification is omitted rather than redacted into an oracle. Withdrawn client material receives a generic, non-linking access-change notice.

The MSP and portal use separate routes. Read state is CSRF-protected and reversible. PostgreSQL enforces tenant/event/organization/recipient agreement, immutable identity, no deletion, and forced tenant RLS. Only `read_at` may change.

## Consequences

- A notification is not a durable authorization grant and cannot retain a sensitive label after access changes.
- Recipient selection occurs when the outbox event is consumed; events already delivered by `0.5.4` are not backfilled or reinterpreted.
- The first inbox scans a bounded recent window and returns at most 50 authorized records. Scale/pagination refinement remains part of `0.5.9` stabilization.
- SMTP rendering and delivery are a separate consumer boundary assigned to `0.5.6`.
