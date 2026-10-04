# ADR 0108: Repository-inclusive encrypted recovery

Status: Accepted

Date: 2026-10-03

## Context

PostgreSQL and managed media were already part of the supported authenticated
recovery set. Once authored Markdown becomes canonical in managed Git,
database-only recovery can restore permissions and accepted object identifiers
without restoring the objects those identifiers name. An optional Git remote
cannot close that gap because it may be absent, unavailable, behind, or under a
different custody boundary.

## Decision

The supported recovery format includes a separately encrypted managed-repository
artifact. TekDocs briefly pauses application writers, captures PostgreSQL and
the repository volume in one bounded maintenance window, and resumes only the
services that were running before capture.

Each repository is represented by a Git bundle. Temporary local recovery refs
make every immutable `RepositoryCommit` object reachable for bundle creation,
including retained evidence no longer reachable from the accepted branch. The
refs are removed before capture completes. A portable manifest binds repository,
tenant and workspace UUIDs; object format; accepted and indexed commits; every
verified commit; bundle name; and bundle checksum. It contains no repository
path, remote credential, document content, or operational secret.

Restore authenticates the outer recovery manifest and every encrypted component,
then validates the repository archive, member allowlist, checksums, bundle
structure, object formats and retained commits before destructive replacement.
Repositories are reconstructed from bundles rather than copied configuration,
so remotes and remote credentials are not restored or counted as recovery.

After PostgreSQL is restored, TekDocs compares its complete repository inventory
and accepted/indexed heads with the repository manifest and runs accepted-head
reconciliation. Any missing, added, swapped, truncated, advanced, mismatched, or
unavailable repository fails the operation. The recovery rehearsal can place the
restore stack on a Docker-internal network so DNS, GitHub and other remote
services are unavailable throughout restoration and verification.

## Consequences

- Supported backup now includes PostgreSQL, managed media, managed repositories,
  deployment secrets, component checksums, and a separately custodied key.
- Backup requires a short write pause; read/write services resume automatically
  on success or failure.
- Restore never fetches a Git remote and does not preserve remote configuration.
- A healthy optional remote is replication, not backup completion.
- Old recovery-v1 sets remain evidence for their database-first versions but do
  not satisfy recovery for a repository-backed TekDocs release.
