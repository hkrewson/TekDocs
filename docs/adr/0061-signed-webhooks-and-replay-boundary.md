# ADR 0061: Signed webhooks and replay boundary

Date: 2026-08-12

Status: Accepted for `0.6.3`

## Context

Webhooks cross an untrusted network boundary in both directions. A destination may resolve to private infrastructure, change between validation and connection, redirect elsewhere, retain sensitive payloads, or fail indefinitely. An inbound sender may forge or replay a valid request. Endpoint discovery also occurs before tenant RLS can be bound, so its identity and database ownership require a separately reviewed control-plane boundary.

## Decision

- An endpoint belongs to exactly one organization and is inbound or outbound. Outbound subscriptions are selected from the existing value-minimized outbox topics; inbound accepts only `integration.ping` with empty data in this slice. There is no MSP aggregate subscription.
- A random signing key is returned only at creation/rotation and envelope-encrypted with tenant, endpoint, and generation as associated data. Rotation advances exactly one generation; endpoint identity, destination, direction, and topics are immutable. Deactivation retains evidence.
- Signatures are `v1=` HMAC-SHA256 over `{delivery_id}.{unix_timestamp}.` followed by exact body bytes. Receivers get delivery ID, timestamp, signature, and canonical JSON. Inbound verification applies a five-minute window, strict header formats, constant-time comparison, then an append-only unique endpoint/delivery receipt.
- Each matching outbox event projects at most one delivery per endpoint. Temporary failures use bounded exponential retry; permanent or exhausted failures dead-letter. Delivered rows and inbound receipts are immutable. Inspection contains endpoint/topic, lifecycle timestamps, attempt count, safe error code, and HTTP status only—never request/response bodies or exception text.
- Outbound URLs require a public DNS hostname on standard HTTPS with no credentials, query, or fragment. Every resolved address must be globally routable. The client connects to one pinned resolved address while verifying certificate hostname/SNI, follows no redirects, and enforces connect/read/body limits.
- Endpoint management uses session/CSRF, `integrations.manage`, enrolled MFA policy, and recent allauth reauthentication. Public inbound failure copy does not reveal whether an endpoint exists. PostgreSQL guards exact organization/tenant edges, key rotation, delivery history, receipt immutability, and forced tenant RLS for delivery data.

## Consequences

TekDocs can deliver signed value-minimized events and reject straightforward forged/replayed inbound requests without treating a configured URL as unrestricted server egress. A host administrator with the deployment master key and database can still decrypt signing keys, and remote acceptance remains at-least-once across a crash after the receiver accepts but before local commit. Provider credentials, arbitrary provider payloads, domain mutations, generalized shared egress, scale/upgrade abuse evidence, and final integration certification remain later milestones under `TD-RISK-047`.
