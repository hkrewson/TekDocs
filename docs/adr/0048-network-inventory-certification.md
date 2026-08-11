# ADR 0048: Network inventory certification

- Status: Accepted for `0.5.0`
- Date: 2026-08-11

## Context

Releases `0.4.1` through `0.4.9` introduced and then deliberately narrowed the network subsystem. A minor-version boundary must not merely restate that individual feature tests passed. It needs one repeatable gate tying together exact-Workspace authorization, PostgreSQL enforcement, the asset-backed lightweight product boundary, legacy preservation, performance, recovery, browser behavior, and production packaging.

## Decision

- `0.5.0` adds no network domain family, connector authority, import/apply path, secret custody, monitoring, or cross-client aggregate.
- `make test-network-certification` is the named subsystem gate. It composes all network-family, NetBox seam, relationship, permission/IDOR, forced-RLS, migration, scale/query-budget, frontend component, and accessibility tests.
- Certification additionally requires `make check`, the exact `0.4.9` production-shaped upgrade rehearsal, independent PostgreSQL/media backup/restore, the real browser-to-Django-to-PostgreSQL journey, security scans, and production-image validation.
- Risks `TD-RISK-031` through `TD-RISK-038` remain mitigated controls with recurring owners; certification does not claim that inventory is live network truth or that TekDocs replaces NetBox.
- Interface/VRF compatibility is supported retained data, not an advertised ordinary authoring surface. No removal date is established.

## Consequences

The network subsystem has one auditable closeout contract and one command for its principal automated evidence. Later changes to a certified family or its projection must extend this gate and reconsider the corresponding risk. External publication, signed tags/images, hosted checks, and deployment still require explicit authorization and cannot be inferred from local certification.
