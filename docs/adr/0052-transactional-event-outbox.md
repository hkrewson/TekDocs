# ADR 0052: Transactional event outbox

- Status: Accepted for `0.5.4`
- Date: 2026-08-11

## Decision

Invitation issuance/acceptance and client-visible publication availability/withdrawal write an `OutboxEvent` in the same PostgreSQL transaction as the domain change. Topics have exact payload schemas containing only reviewed enum metadata; subject and organization identifiers occupy typed columns. The event's scope, topic, subject, idempotency key, payload, and creation time cannot change or be deleted.

A scheduled Celery task reads a bounded tenant-scoped batch under forced RLS. It claims each row, recovers leases older than five minutes, and writes one append-only receipt for the named internal consumer. Failed attempts retain only an allowlisted code, use bounded exponential backoff, and enter dead letter after five attempts. Consumer implementations must treat the event UUID as their idempotency key.

## Consequences

- A committed domain transition cannot silently lose its future notification work, and rolled-back work cannot emit an event.
- The outbox is not an audit log, mail log, or arbitrary serialized-domain store.
- The receipt in this slice proves durable internal consumption only. Recipient authorization and inbox records arrive in `0.5.5`; SMTP remains `0.5.6`.
- Host/database administrators remain trusted. Application tenant isolation is enforced through normal scope binding and forced RLS.
