# ADR 0058: Controlled client access certification

Date: 2026-08-11

Status: Accepted for `0.6.0`

## Context

The `0.5.1` through `0.5.9` slices established separate controls for immutable publication decisions, client identity, fail-closed portal projection, transactional events, notification inboxes, SMTP delivery, digest scheduling, administration, and long histories. Passing each feature suite independently does not prove that their authorization, database, worker, browser, upgrade, and recovery boundaries still compose.

## Decision

- `make test-portal-notification-certification` is the named PostgreSQL subsystem gate. It composes the complete client identity, invitation, publication, portal, outbox, inbox, SMTP, preference, scheduling, administration, history, permission/IDOR, forced-RLS, and migration suites plus the frontend accessibility/component suite.
- The release and hosted Compose gates invoke that named composition. Existing smaller targets remain useful diagnostics but cannot substitute for the certification target.
- The production-shaped live browser journey proves the audience transition across real sessions: one MSP user publishes, a different MFA-enabled staff member approves, an invited client receives only the portal projection and its permission-filtered inbox, and withdrawal removes availability without modifying retained evidence.
- The subsystem upgrade begins at exact `0.5.9`, crosses the non-destructive `0.5.10` network correction, and verifies the complete retained fixture at `0.6.0`. Independent PostgreSQL/media restore remains required.
- Formal certification adds no model, migration, route, event topic, payload field, or delivery capability. The existing ADRs 0049–0056 remain the implementation contracts.

## Consequences

“Certified” means the documented local repository gates passed for the implemented one-MSP-per-installation scope. It is not an external assessment, penetration test, delivery guarantee, compliance certification, or authorization to publish artifacts. SMTP remains at-least-once across the remote-acceptance crash window, asynchronous bounce ingestion remains future integration work, and supported encrypted backup/key-loss recovery remains later hardening.
