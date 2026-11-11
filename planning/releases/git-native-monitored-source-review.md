# Git-native monitored-source acceptance review

Scope: the implementation introduced at `1807fed5` and its candidate-acceptance
corrections described in [the slice record](../git-native-monitored-sources.md).
This is automated source review, not independent human assurance or release
approval. Exact-source hosted evidence follows the acceptance push.

## Spec review

The first review found that review fingerprints did not directly include every
source setting, unsaved non-URL settings could escape the navigation guard, and
historical changed observations could permanently block publication after later
changes were applied. It also found missing stale-settings, upgrade, rollback,
recovery and clean-start browser evidence. Each finding was corrected and the
review reached a clear fixed point.

The final design validates retained observation digests, binds exact settings,
Git commit and blob into review, and records each successful application as a
separate immutable proof. A changed observation blocks publication precisely
when neither application proof nor the upgraded current pointer covers it.

## Standards and security review

The review checked tenant/organization/source ownership, runtime actor binding,
forced RLS, PostgreSQL and ORM immutability, audit-aware upgrade provenance,
lossless rollback refusal, managed-Git compensation and exact recovery custody.
The new application proof is scoped and append-only; populated application
history refuses schema reversal before any proof is removed. Re-review found no
remaining concrete standards, correctness or security findings.

## Evidence disposition

Local production frontend build, focused Ruff and mypy, Django system and
migration-drift checks, and shell syntax pass. The retained runtime database role
cannot create the isolated test database, so the database, browser, supported
upgrade, encrypted recovery and production-container claims remain pending the
exact-source hosted Build and Extended gates. CodeQL remains a separate required
source gate. No production deployment or existing-data transition is authorized
by this record.
