# ADR 0059: Public API and generated client contract

Date: 2026-08-12

Status: Accepted for `0.6.1`

## Context

TekDocs already exposes a large session-authenticated `/api/v1` surface, but its collection envelopes, filter behavior, errors, retry headers, and browser request types were conventions by repetition rather than one enforceable compatibility boundary. Silent query typos could broaden selected endpoints, generic DRF errors varied by serializer, and hand-authored frontend request types could drift from the server schema.

## Decision

- Offset collections use `results`, `page`, `page_size`, `count`, and `has_more`, with a maximum page size of 100. Ordered histories may use their existing signed seek cursor with `results`, `has_more`, and `next_cursor`.
- Public query serializers derive from a strict base and reject undeclared parameters. Authorization and Workspace resolution remain prerequisites to filtering and pagination.
- Framework-generated failures use `{ "error": { "status", "code", "message", "fields?", "detail?", "request_id" } }`. `detail` is retained temporarily for compatibility; new consumers use the stable fields. The UUID is repeated in `X-Request-ID`.
- `Idempotency-Key` accepts 8–200 allowlisted ASCII characters. It is advertised only on naturally convergent staff-assignment operations in this slice. Echoing the key is correlation, not stored request/result replay; generic durable idempotency belongs to `0.6.5`.
- `backend/openapi.yml` is authoritative. `openapi-typescript` generates immutable TypeScript definitions and `openapi-fetch` provides a typed same-origin session/CSRF wrapper. The generated artifact is committed and `--check` is blocking locally and in CI.

## Consequences

New public endpoints have one contract to follow and frontend code can consume server-derived path/operation types without storing an alternate API model. This slice adds no database schema. Existing manually typed domain-conflict payloads remain operation-specific and must stay explicit in OpenAPI. Thirty pre-existing list/detail operation-ID collisions are deterministic today but not a suitable stable external naming contract; `TD-RISK-044` requires explicit IDs before `0.7.0`. Durable same-key/same-request replay remains intentionally unclaimed under `TD-RISK-045`.
