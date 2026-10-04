# ADR 0109: Repository foundation composed acceptance

Status: Accepted

Date: 2026-10-03

## Context

Issues #92 through #97 established repository identity, managed local custody,
bounded commits, portable workspace manifests, authenticated audit attribution,
reconciliation and repository-inclusive recovery. Passing those boundaries in
isolation does not prove that the same accepted objects survive their combined
runtime lifecycle. The `0.9.1` exit condition therefore requires one composed,
production-shaped rehearsal before parser or authored-content work begins.

## Decision

`make repository-foundation-acceptance` is the blocking composed boundary for
`0.9.1`. It creates one MSP workspace plus differently classified client and
vendor workspaces, initializes one private repository per workspace, and writes
distinct deterministic acceptance content through the bounded commit service.
It verifies stable ownership and repository identities, portable manifests,
empty derived/index state, absence of remotes and GitHub credentials, and the
failure of reads for another workspace's unique path.

The rehearsal injects an interruption after Git creates a candidate commit but
before PostgreSQL accepts it, verifies rollback to the prior accepted head, and
then proves abandoned-stage cleanup and retry. It recreates the backend and
worker against the persistent repository volume, captures the authenticated
encrypted recovery set, restores it to a clean stack whose application network
is Docker-internal, and compares the complete repository/workspace/tenant,
accepted-head and content-digest inventory byte for byte.

Extended Validation and the release gate run this boundary. It does not add a
public repository API, parser, indexer, document migration or remote Git client.

## Risk disposition

- The fixture calls the internal commit service because public managed
  authoring belongs to `0.9.5`. This is accepted only as milestone evidence and
  does not claim an authorization-ready repository API.
- Organization joins are intentionally hidden from an unscoped runtime process
  by row-level security. Acceptance validates classifications through the
  portable workspace manifests and never broadens the runtime role.
- The restored runtime network is proven `internal`; image construction remains
  a separate supply-chain operation and is not described as an air-gapped
  build. Restore never fetches a Git remote.
- The derived/index head is deliberately empty. Parsing, indexing and
  deterministic rebuild become the next `0.9.2` boundary in issue #101.
- The rehearsal is resource-intensive, so it runs in Extended Validation and
  the release gate rather than the fast local gate. Focused unit and contract
  tests continue to run on ordinary changes.

## Consequences

The application may advance to the `0.9.1` repository-foundation checkpoint.
The frozen `0.9.0` schema remains the exact prior upgrade source. GitHub and
other remotes remain optional post-1.0 replication integrations, and no current
PostgreSQL document content becomes repository-canonical in this checkpoint.
