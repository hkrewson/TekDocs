# ADR 0113: Managed Git authoring and explicit source conflicts

Status: Accepted

Date: 2026-10-05

## Context

The canonical Markdown repository and its PostgreSQL projection already exist,
but technicians still need a safe way to write repository-backed documents and
fragments. A browser draft, a filesystem operator, or another browser can
advance Git between read and save. Git and PostgreSQL cannot commit atomically.

## Decision

Staff document-edit permission gates writes to the exact MSP or organization
workspace; client portal users cannot read raw source or author. Each mutation
names a stable content UUID and, for an existing file, an exact base commit and
Git blob identity. The service builds a complete candidate snapshot, validates
the profile and composition graph, then commits through the existing
compare-and-swap repository service. A changed target never overwrites the
other author: the API returns base, current and proposed source with a 409.
An unrelated head advance can be accepted if the target source is unchanged.

The editor patches only requested frontmatter fields and/or Markdown body,
retaining comments and untouched fields. Files may move within their repository;
the previous path becomes a bounded alias, while UUID-based wikilinks, includes,
templates and entity references remain stable without text rewriting. Alias
collisions are rejected. Source readers resolve an exact current path or alias
within one repository. Raw source and compare content are never returned from
another workspace.

The accepted commit is authority even if projection work fails after a write.
PostgreSQL's accepted and indexed commit markers form a durable retry signal;
the authoring path indexes synchronously when possible and a periodic task
retries lagging repositories. Reconciliation does not infer acceptance from the
newest filesystem commit. The UI keeps drafts through navigation warnings and
shows three-way source plus a deliberate rebase action on conflict.

## Consequences

Local Git supplies revision history without a GitHub credential. There is no
schema migration: the existing accepted/indexed markers and graph tables are
used. Legacy database documents and publication workflows remain separate
until `0.9.6` and `0.9.7`. A failed post-commit index cannot retract the Git
commit; health must continue to expose and retry lag rather than reporting the
write as absent. Remote synchronization and arbitrary direct source editing
remain out of this slice.
