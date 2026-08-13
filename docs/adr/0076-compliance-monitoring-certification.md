# ADR 0076: Compliance and monitoring certification

Date: 2026-08-13

Status: Accepted for `0.8.0`

## Context

The `0.7.1` through `0.7.13` slices established separate compliance, reminder, approved-egress, domain, DNS-observation, and certificate-monitoring controls. Passing those suites independently does not prove that exact-Workspace authorization, retained evidence, workers, browser flows, upgrades, recovery, and production images still compose.

## Decision

- `make test-compliance-monitoring-certification` is the named PostgreSQL subsystem gate. It composes compliance catalogs, assignments, evidence, risks, signed bundles, reminders, domains, hostile egress, certificate monitoring, stabilization, permission/IDOR, forced RLS, migration preservation, entity/RBAC certification, and frontend tests.
- The production-shaped browser journey creates an exact-client framework and control review, verifies a signed bundle, and creates a registered domain, renewal reminder, and fixed-port certificate endpoint through React, Django, and PostgreSQL.
- The exact-prior upgrade begins at commit `8fdde2d` (`0.7.13`) and preserves a signed compliance bundle plus successful digested domain/certificate evidence. An independent PostgreSQL/media restore verifies the same fixture.
- Production-target image and secret-file behavior remain mandatory release evidence through the existing rehearsal.
- Certification adds no model, migration, route, permission, dependency, external collector authority, inbox/SMTP monitoring routing, or cross-client dashboard.

## Consequences

“Certified” means the documented local repository gates passed for the implemented one-MSP-per-installation scope. It is not an external compliance certification, penetration test, registrar/DNS authority, certificate-management service, or authorization to publish artifacts. A host or database administrator remains trusted. Supported encrypted backup/key-loss recovery, proxy-aware DAST, and general monitoring-recipient routing retain later roadmap owners.
