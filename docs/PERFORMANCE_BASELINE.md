# Performance baseline

TekDocs treats performance as an authorization-preserving release property. A faster query is not acceptable when it broadens tenant, organization, audience, or field visibility.

## Current reference fixture

`backend/apps/core/tests/test_stabilization_performance.py` creates a fixed-shape PostgreSQL fixture with:

- 100 client organizations;
- 10,000 organization-distributed reference entities;
- 250 people and organization associations;
- 50 sites and 250 nested locations; and
- 25 typed entity links.

The fixture contains 10,650 addressable entities before bootstrap-owned records. UUIDs and credentials remain randomly generated, while record counts, ownership distribution, searchable labels, and relationships are deterministic.

The gate measures eight warmed HTTP requests for each ordinary read and rejects a p95 of 500 ms or greater. It separately captures Django query counts around the underlying authorized services so latency improvements cannot hide an N+1 regression.

| Read path | Query budget | 0.1.15 observed p95 |
| --- | ---: | ---: |
| Workspace discovery | 12 | 7.0 ms |
| Organization list | 12 | 14.1 ms |
| Client People search/list | 4 | 15.3 ms |
| Client Sites list | 3 | 35.7 ms |
| Client Entity search | 5 | 11.4 ms |
| Client relationship discovery | 6 | 10.9 ms |

Observed service query counts were 3, 3, 2, 2, 3, and 2 in the same order. These values are evidence from one run, not a universal capacity promise.

## Reference environment

The `0.1.15` evidence was collected in Docker Desktop 29.2.1 on an Apple M4 Max host. Docker reported 12 CPUs and approximately 8 GB of assigned memory. The database and test runner used the repository Compose services and PostgreSQL 17 image contract.

Run the blocking cross-cutting suite with:

```sh
make test-stabilization
```

Run the performance fixture alone when profiling:

```sh
docker compose run --rm migrate pytest apps/core/tests/test_stabilization_performance.py -q -s
```

## Interpretation and growth

- The 500 ms threshold applies to ordinary indexed reads on the documented reference environment, not imports, reports, or external integrations.
- Query-count budgets are ceilings. A change that exceeds one must be optimized or explicitly reviewed with updated evidence; increasing the number to make a failure pass is not a fix.
- Cold image startup and fixture construction are excluded from request timing.
- The fixture exercises only domain families implemented by `0.1.15`. Documentation blocks/revisions and asset records join the reference dataset when those models ship, growing toward the 1.0 target of 100 clients, 100,000 entities, 250,000 block revisions, and 25,000 assets.
- Before 1.0, measurements require a quieter documented reference host, search-index coverage, concurrency/load testing, and retained trend artifacts. This baseline is an early regression tripwire, not a production sizing guide.
