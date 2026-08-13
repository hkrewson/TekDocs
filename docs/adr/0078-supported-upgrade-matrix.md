# ADR 0078: Supported-minor upgrades are retained-state rehearsals

Date: 2026-08-13

Status: Accepted for `0.8.2`

## Decision

TekDocs supports a direct forward migration from the stabilized endpoint of every prior `0.x` line, beginning with `0.1.3`. The matrix pins both commit and checked-in version for `0.1.3`, `0.2.9`, `0.3.12`, `0.4.9`, `0.5.9`, `0.6.9`, `0.7.13`, and `0.8.0`. Each source uses the most representative fixture available at that boundary rather than treating an empty database migration as sufficient.

Existing domain upgrade rehearsals accept an explicit expected source version and always target the current working release. One blocking orchestrator executes all cases serially with unique Compose projects and real PostgreSQL. The current one-shot owner migration and constrained runtime role must start successfully after each migration.

Production downgrade is unsupported. Rollback after migration means full restore of a pre-upgrade encrypted recovery set into the retained old application version. Operators must not reverse arbitrary Django migrations, edit migration history, or run an old binary against a database touched by a new release.

## Consequences

The gate is intentionally expensive and belongs to release evidence rather than every fast edit. Adding a supported minor requires a stable source commit, retained fixture, matrix entry, and documented recovery point. Removing a source requires an explicit support-policy decision; silently dropping a failing historical case is prohibited.
