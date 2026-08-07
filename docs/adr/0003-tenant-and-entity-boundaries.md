# ADR 0003: Tenant and entity boundaries

- Status: Accepted
- Date: 2026-08-07

## Decision

Optimize 1.0 for one MSP per self-hosted installation while retaining an explicit tenant key on all owned data. Give every addressable domain object a stable UUID through an `Entity` registry and represent cross-object references through typed `EntityLink` rows.

Application policy remains authoritative; PostgreSQL scoping and row-level controls are defense in depth.
