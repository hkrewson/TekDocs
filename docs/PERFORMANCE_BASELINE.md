# Performance baseline

TekDocs treats performance as an authorization-preserving release property. A faster query is not acceptable when it broadens tenant, organization, audience, or field visibility.

## Public-beta reference fixture

`backend/apps/core/tests/test_public_beta_capacity.py` expands the fixed PostgreSQL shape to:

- 100 client Workspaces;
- at least 100,000 addressable Entities;
- 250,000 immutable revisions in one intentionally deep history; and
- 25,000 assets in one intentionally large operational Workspace.

It measures warmed first/middle/final asset pages, the last revision-history page, broad exact-Workspace Entity search, whole-request query ceilings, and an eight-request authorized burst. Ordinary reads retain the 500 ms local p95 tripwire; the burst has a separate two-second ceiling. This composition is deliberately available through `make test-public-beta-performance` rather than making every fast edit loop rebuild hundreds of thousands of rows.

The frontend side of that gate uses the production build with deterministic Chromium CPU/network throttling for constrained desktop and mobile viewports. It proves the optional editor is not loaded before a document opens and applies ready-time plus decoded-JavaScript ceilings. Emulation makes regression runs comparable; it is not a physical-device certification.

## Earlier stabilization fixture

`backend/apps/core/tests/test_stabilization_performance.py` creates a fixed-shape PostgreSQL fixture with:

- 100 client organizations;
- 10,000 organization-distributed reference entities;
- 250 people and organization associations;
- 50 sites and 250 nested locations; and
- 25 typed entity links; and
- one reusable document with 2,500 immutable block revisions.

The fixture contains at least 10,650 addressable entities before bootstrap-owned documentation records. UUIDs and credentials remain randomly generated, while record counts, ownership distribution, searchable labels, relationships, and revision depth are deterministic.

The gate measures eight warmed HTTP requests for each ordinary read and rejects a p95 of 500 ms or greater. It separately captures Django query counts around the underlying authorized services so latency improvements cannot hide an N+1 regression.

| Read path | Query budget | 0.1.15 observed p95 |
| --- | ---: | ---: |
| Workspace discovery | 12 | 7.0 ms |
| Organization list | 12 | 14.1 ms |
| Client People search/list | 4 | 15.3 ms |
| Client Sites list | 3 | 35.7 ms |
| Client Entity search | 5 | 11.4 ms |
| Client relationship discovery | 6 | 10.9 ms |
| Document revision-history page | 3 | 20.6 ms (`0.2.9` evidence) |
| Client asset page (25 of 120) | 32 whole-request queries | `< 500 ms` (`0.4.0` certification) |
| Client software-license page (25 of 60) | 32 whole-request queries | `< 500 ms` (`0.4.0` certification) |
| Client contract page (25 of 120) | 32 whole-request queries | `< 500 ms` (`0.4.0` certification) |
| Client credential-reference page (25 of 120) | 32 whole-request queries | `< 500 ms` (`0.4.0` certification) |

Observed service query counts for the original six paths were 3, 3, 2, 2, 3, and 2 in the same order. The document-history service ceiling is three queries. The inventory ceilings cover the complete authenticated HTTP request—including session bookkeeping, transaction-local RLS binding, Workspace and policy resolution, count, page read, and fixed relation prefetches—so they are not directly comparable with the earlier service-only counts. These values are evidence from local runs, not a universal capacity promise.

## Reference environment

The `0.1.15` evidence was collected in Docker Desktop 29.2.1 on an Apple M4 Max host. Docker reported 12 CPUs and approximately 8 GB of assigned memory. The database and test runner used the repository Compose services and PostgreSQL 17 image contract.

Run the blocking cross-cutting suite with:

```sh
make test-stabilization
make test-documentation-certification
make test-inventory-certification
make test-portal-notification-certification
```

Run the performance fixture alone when profiling:

```sh
docker compose run --rm migrate pytest apps/core/tests/test_stabilization_performance.py -q -s
docker compose run --rm migrate pytest apps/core/tests/test_inventory_stabilization.py -q -s
make test-public-beta-performance
```

## Interpretation and growth

- The 500 ms threshold applies to ordinary indexed reads on the documented reference environment, not imports, reports, or external integrations.
- Query-count budgets are ceilings. A change that exceeds one must be optimized or explicitly reviewed with updated evidence; increasing the number to make a failure pass is not a fix.
- Cold image startup and fixture construction are excluded from request timing.
- The public-beta fixture reaches the planned 1.0 reference record counts. It does not establish the maximum supported dataset, sustained concurrency, a hosted-service SLA, or an operator-specific production sizing guide.
- Final release-candidate measurements still require a quiet documented reference host, retained trend artifacts, and remediation of any browser, database, or external-review regression.
