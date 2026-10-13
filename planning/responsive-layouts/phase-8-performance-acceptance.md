# Phase 8 local performance acceptance

Date: 2026-10-12. Milestone: 0.9.8. Base: `b987fe738b47097654ffffad01d27357e18fa9cb`
plus the current worktree. This is local evidence, not a frozen-candidate release
attestation. Numeric measurements, test/image identities, and the runtime diff
fingerprint are retained in
[the benchmark record](../../.ecc/benchmarks/2026-10-12-0.9.8.json).

## Reproduction and remediation

The existing performance gate exercised database-backed history and the legacy
visual editor, but not Git source entry. Added a real-Git/PostgreSQL reference
with 250 documents and one shared live fragment, plus constrained browser
profiles for repository editing. The new source-read test reproduced a
**1,902.8 ms p95**, exceeding the existing **500 ms** warmed-read budget.
`read_authored_content` fetched and parsed every Markdown file to locate one ID.

The current index now serves only as a file locator. The source still comes
from Git, with accepted-commit comparison inside the repository read lock,
reconciliation checks, and parsed identity/digest verification. An absent,
stale, or inconsistent locator falls back to the original snapshot search.
No derived Markdown is returned as canonical source, no permission cache was
introduced, and unavailable Git storage still fails closed.

Seven regression cases cover the fast path, altered derived text, unavailable
Git, index lag, missing node/path, digest drift, wrong identity, and a real head
advance between lookup and read. Existing workspace/tenant denial tests remain
part of the authoring gate.

The large-capacity Make target also omitted the latency-enforcement setting.
A Docker diagnostic confirmed eight samples and enforcement disabled in its
shared timing helper, despite the capacity test asserting its own latency
ceiling. It now supplies the same setting as the other dedicated checks,
selecting 40 warmed samples. The corrected capacity invocation passed.

## Measured results

Post-fix Git reads, each with 40 warmed samples:

| Path | p95 | Queries | Limits |
| --- | ---: | ---: | --- |
| Last listing page | 22.2 ms | 51 | 500 ms / 64 queries |
| Composed document with shared fragment | 15.9 ms | 30 | 500 ms / 64 queries |
| Canonical authoring source | 47.4 ms | 36 | 500 ms / 64 queries |

The corrected pre-optimization capacity run retained 100 clients, 100,000
Entities, 250,000 legacy revisions, and 25,000 assets. First/middle/last asset
pages measured 114.3/243.1/354.7 ms p95; deep history 295.1 ms; entity search
35.6 ms. All remained below 500 ms, with query ceilings passing. The eight-request
burst maximum was 928.0 ms against 2,000 ms. Older workspace, inventory, portal,
and notification performance checks also passed before the source optimization.
These earlier measurements are not silently reclassified as post-fix evidence.

Final Chromium browser measurements used fresh contexts, sequential execution,
no retries, 4x/6x CPU throttling and constrained desktop/mobile networks:

| Editor / profile | Shell ready | Editor ready after shell |
| --- | ---: | ---: |
| Legacy / desktop | 5,044 ms | 6,614 ms |
| Legacy / mobile | 6,544 ms | 8,310 ms |
| Git / desktop | 4,957 ms | 346 ms |
| Git / mobile | 6,522 ms | 417 ms |

All passed the unchanged 8,000/12,000 ms limits. Initial decoded JavaScript was
677,714 bytes; legacy editing added 1,467,518 bytes, while Git editing added no
script resources. These are decoded resource measurements, not compressed wire
sizes. The separate compressed production bundle gate also passed.

The initial four-profile browser test exceeded its combined 30-second test
timeout while entering the third profile. Splitting it into four sequential
tests preserved every per-path assertion and each test's default timeout.
The corrected rehearsal passed all four profiles in 39.5 seconds.

## Verification and remaining scope

- Frontend: 752 tests, lint, type checks, production build and bundle ceilings
  passed; final performance-spec lint passed after splitting the profiles.
- Post-fix `make test-content-authoring`: all 158 tests passed, including source
  validation, forced RLS, and API contracts.
- Post-fix Git performance and repository-service tests passed together in
  Docker. Changed backend source lint and type checks passed.
- The initial aggregate `make test-public-beta-performance` invocation failed
  on the combined browser timeout. Corrected selections were rerun separately;
  this is not a claim that the original aggregate command passed.

The benchmark skill guided explicit before/after measurements and durable,
value-minimized metrics. The security-review checklist guided the locator,
identity, race, and unavailable-storage checks; this is a bounded review, not
the complete candidate source review.

Timing jobs ran sequentially on one local Docker host with its ordinary
background services left running. Browser API responses are mocked; actual Git
and PostgreSQL are measured separately. This is not physical-device telemetry,
Core Web Vitals, sustained concurrency, cold-cache evidence, maximum capacity,
or Git write/history-scale acceptance. Index drift deliberately keeps the slower
fallback. Retain `TD-RISK-013` and `TD-RISK-017` limitations.

Before release, rerun the complete maintained gate on the frozen candidate and
retain its matched evidence. Human technician walkthroughs, pilot, and the
remaining security review are separate outstanding requirements. No release
checkbox, version, tag, deployment, or candidate security attestation is closed
by this local record.
