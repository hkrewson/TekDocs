# Contributing

Start with `README.md`, the current issue or milestone, and the public GitHub Wiki when it is available. Keep changes aligned to one roadmap slice and include tests for behavior and security boundaries. Machine-specific agent instructions are local files and must not be included in public commits.

Contributions must use the Developer Certificate of Origin 1.1 and include a `Signed-off-by` trailer in each commit (`git commit -s`). Do not submit customer data, credentials, proprietary code, or dependencies with unclear redistribution rights.

## Branch and validation contract

Use short-lived branches and pull requests for development. `main` is the green
development/integration authority and may be ahead of production. Production is
identified by immutable application and receipt tags plus verified image digests;
there is no mutable production branch. See the
[CI and environment state contract](planning/ci-and-environment-state.md) for the
documentation, pull-request, main-integration, scheduled and release lanes.
