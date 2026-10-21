# Read-only migration preview correction

Date: 2026-10-20. Scope: issue #105, first MSP document readiness.

## Acceptance and diagnosis

Preview must leave content and repository health metadata unchanged, including
reused or pinned content, while preserving repository integrity and tenant checks.
The operator's ordinary document passed inventory, but the production v0.9.9
preview raised `ReadOnlySqlTransaction: cannot execute UPDATE in a read-only transaction`.
The accepted-snapshot reader called `_record_reconciliation`, which saved repository
health metadata. The explicit read-only transaction correctly refused that write.

Before modifying runtime code, the existing
`test_inventory_is_repeatable_read_only_and_exact_workspace` was run with its
preview inside a PostgreSQL read-only transaction in isolated Docker. It failed
with the same exception at `_record_reconciliation` (1 failed in 82.64 seconds).
Local log: `/tmp/tekdocs-preview-readonly-before.log`.

## Correction

Migration preview/export reads suppress reconciliation persistence for accepted
snapshots, retained snapshots and accepted history. Candidate composition validation
also suppresses persistence when reading historical includes. Integrity classification
and refusal of unavailable accepted content still run. Normal repository operations
retain the existing persistence defaults.

All existing preview calls in the migration inventory test module now run inside
an explicit PostgreSQL read-only transaction, retaining their existing assertions.
There is no database migration or HTTP/OpenAPI contract change. Internal operator
guidance is updated here; ADR 0115 explicitly keeps this procedure out of the
public Wiki for the current single-operator deployment.

## Evidence and delivery

- **Verified:** the focused Docker reproduction passes after the correction
  (1 passed in 88.72 seconds; `/tmp/tekdocs-preview-readonly-after.log`).
- **Verified:** Docker Ruff and mypy passed (269 source files for mypy).
- The broader Docker run used the complete selections from
  `make test-document-migration-inventory` and `make test-content-authoring`, plus
  `test_repository_service.py`, through a temporary isolated-project adapter of
  the repository's PostgreSQL shard runner. It recorded 180 passed and 51 errors
  in 327.44 seconds. All errors occurred in repository-service setup/teardown
  after PostgreSQL reported `DiskFull`. This is a failed run, not a passing gate.
  Log: `/tmp/tekdocs-preview-validation.log`. Its disposable stack was removed by
  the runner; no unrelated Docker environments or caches were pruned.
- **Verified:** fresh isolated repository-service rerun passed all 32 tests in
  95.27 seconds, with Ruff and mypy passing again. Log:
  `/tmp/tekdocs-preview-repository-retest.log`. All selected cases have passing
  execution evidence across the runs; the original combined run remains failed.
  No aggregate coverage claim is made from these runs.
- Full `make document-migration-release-gate` and exact-candidate hosted Build,
  CodeQL and Extended validation remain release work; this focused regression
  does not certify a new release.
- **Blocked for production use:** v0.9.9 still contains the defect. A new frozen
  runtime candidate needs full release validation, hosted checks, fresh security
  disposition and explicit publication/deployment authorization. Existing v0.9.9
  release evidence does not certify this change.
- The broader authority reversibility gap remains open. This correction does not
  authorize importing or promoting the production document.

Do not remove the read-only guard as a workaround. No production retry is needed
until the corrected runtime has been delivered.
