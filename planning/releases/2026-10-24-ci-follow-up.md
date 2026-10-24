# October 24 CI follow-up

Scope: the housekeeping run 40068404406 and dependency PRs 121, 122, 123 and 126.
Acceptance: retain the IP property assertion and its health check; reproduce
reported incompatibilities; align coupled development tools; identify bundle
growth without increasing budgets. No production deployment or new release.

## IP property health check

Main run 40068404406 and React-plugin PR run 40068566103 failed
`test_canonical_host_property` during Hypothesis input generation, not its
canonicalization assertion. Main reported two inputs in 1.67 seconds, with one
1.668-second draw. Seed: 242596917881777902355762999379099477115.

The exact production `canonical_host` function and test decorator/assertion were
extracted with Python AST and replayed using installed Hypothesis 6.165.2 in
Docker. Both 0.25-CPU and 0.05-CPU seeded replays passed. Those are isolated pure
function replays, not reproduction of the full shard environment. Root cause
remains unknown; CPU contention is a hypothesis, not a diagnosis. No test input
range, assertion, timing allowance or Hypothesis health check was relaxed.
Only failed jobs of the existing main run were requested again (attempt 2).

## Coupled tooling

- PR 126's exact package/lock files reproduced npm ERESOLVE in fresh Node
  24.22.1 Docker: Vitest 5.0.5 conflicts with coverage-v8 4.1.10. Both are now
  pinned to 5.0.5 and grouped together for future updates, including majors.
- PR 122's lock reproduced both browser and live-workspace preflight failures:
  package 1.64.1 versus image/rehearsal 1.62.1. Playwright is now pinned to
  1.64.1 in the package, image and three browser/performance rehearsals. The
  upstream image manifest digest was retrieved from MCR and pinned. Node remains
  24.22.1. The image built and Chromium, Firefox and WebKit each launched,
  rendered content and clicked a button with network disabled.
- Playwright proposals are separated from the routine development group because
  its browser image and version assertions require coordinated review.
- npm regenerated the lock. Two shared build-tool transitive packages changed:
  sourcemap-codec 1.5.5 to 1.6.0 and tinyexec 1.3.0 to 1.3.1. Direct application
  dependencies are unchanged. License and security gates still apply.

## Bundle investigation

Fresh Docker builds with the same application source and each exact lock:

| Dependency set | Compressed shell bytes | 131,072-byte limit |
| --- | ---: | --- |
| Current main | 130,376 | Pass |
| Exact PR 121 | 141,582 | Fail |
| PR 121, React/React DOM restored to 19.2.8 | 133,277 | Fail |
| Above, React Router restored to 8.3.0 | 131,598 | Fail |
| Above, Lucide restored to 1.30.0 | 130,392 | Pass |

These are sequential ablations, not independent additive package sizes. The
remaining PR dependency updates passed all existing bundle limits in that
experiment. React, routing and icon updates require their own size review before
merging; moving bytes into another eagerly loaded chunk is not a performance fix.
Budgets and direct production dependencies remain unchanged here. React and
React DOM are now proposed together; React Router and Lucide are separated from
the routine production group so they cannot block unrelated patch maintenance.
No automatic approval or merge is enabled by these groups.

## Local capacity and evidence limits

Initial full Chromium and network-module runs failed provisioning with Docker
ENOSPC. Previously authorized unused build-cache cleanup reclaimed 16.04 GB;
containers and data volumes were not pruned. Those runs remain failures and are
superseded only by explicit successful reruns. An initial frontend gate selected
old host node_modules (Vitest 4); it was stopped and is not update evidence.
Fresh locked Docker validation is the authoritative local frontend run.

The broader maintained-browser matrix and performance checks must confirm the
new browser tooling in hosted validation before its next release. No source
review or risk acceptance is inferred for a new runtime release from this work.

## Verified follow-up and remaining gates

Fresh locked Docker frontend validation passed all 127 files / 772 tests, API
consistency, lint, type checking, coverage, build and existing bundle budgets.
The shell remains 130,376 compressed bytes. The production npm audit passed its
high/critical threshold (known low KaTeX findings remain); license policy passed
609 package versions. All three Playwright engines passed image smoke checks.

A new early supply-chain check rejects mismatched Vitest/coverage versions,
manifest/lock disagreement, Playwright package-chain mismatch, stale image or
rehearsal versions, and a missing digest pin. Positive and negative checks pass; the full security-tooling gate passed 120
checks with three optional live checks skipped.
This catches known incompatible proposals before expensive CI fan-out; it does
not replace runtime browser testing or authenticate a registry digest itself.

Both full local browser and network-module retries again hit Docker ENOSPC
during image construction despite the cache cleanup. They remain blocked, not
passed. Required hosted confirmation: Chromium regression, live browser journey,
the core-c shard and the maintained browser/performance release jobs. The two
isolated Hypothesis replays passed, but the full-shard timing cause remains
unconfirmed. No Hypothesis test change is included.

No user-facing product behavior, database schema or API contract changed; no
public Wiki update is required for this internal test-toolchain maintenance.
The existing release/update instructions remain valid.
