# ADR 0120: Monitored-source Git custody

**Date**: 2026-10-31

**Status**: accepted and validated for the bounded development slice at `6c3824c6`; source review, local Docker/browser checks and exact-source hosted Build/CodeQL/Extended receipts complete

**Deciders**: TekDocs maintainer

## Context

Source settings, schedules and immutable observations belong to the existing SQL
workflow. Authored content moves to Git, while local revisions, signed
publications, control events, PDFs and all managed-file versions retain their
original custody. Previously the source interface was hidden after promotion and
applying an observation still called the retired database content writer.

## Decision

Fingerprint the complete source record and ordered observation history, validating
ownership, applied-pointer membership and actual body checksums. Bind reviewed
imports and dependency-group handoffs to that fingerprint. Do not place URLs,
settings or observation history in authored Git files. Invalid custody blocks
migration and handoff; polling and settings changes serialize on the source row.

Expose the existing source controls for promoted documents. A review compares
the selected retained observation with the current owned primary Git fragment.
Its fingerprint binds source workflow state, exact observation, current commit
and blob, and document/fragment authority generation. Require existing central
edit/MFA policy, a current accepted index, owned live primary placement and
reversible graph. Reload observation bytes from custody rather than trusting a
supplied model instance. Recompute the fingerprint under the same Git, repository,
document and source locks as the write.

Preserve local edits by refusing replacement whenever current text differs from
both the last applied observation and selected observation. A missing baseline
requires manual integration unless current text already matches the selected
observation. No automatic merge or force overwrite is introduced. The ordinary
repository editor remains the explicit manual integration path.

Use the maintained coordinated authoring writer. It retains existing ownership,
file/key, live-consumer and reversible-shape checks. Verify acceptance/indexing
before advancing the applied pointer and appending its value-free audit event.
An exception rolls SQL and Git references back together. Checks retain evidence
without changing document bodies. No new schema, runtime dependency, publication
format or network transport is needed; publication continues to freeze authored
Git bytes under the existing content certificates.

## Consequences

Retained source history and all old signed artifacts remain independent of
current authoring. Rollback projects current Git edits into the original block,
preserving older revisions, source configuration and applied pointer; re-promotion
still requires verified parity. A stale review is refused and the interface keeps
the panel open for review and retry. The review discloses propagation to live
consumers and unchanged pinned/signed content without exposing restricted
consumer metadata. Previously observed, unapplied changes remain reviewable
after later unchanged checks. Unsaved source settings disable apply/check.

Fresh/0.8.46 upgrade and independent encrypted recovery use synthetic sources and
observations without contacting an upstream server. Recovery compares actual
retained file/PDF bytes, source settings, observation metadata/bodies, all local
revisions, signatures, controls, authority and accepted Git sources exactly.
Local runtime validation reuses the single existing Docker project; independent
environments remain hosted-only.

This slice is development on 0.9.16. General cross-Workspace reuse, client delivery
and aggregate 1.0 acceptance remain separate. No release, deployment, live data
migration or renewal of existing risk exceptions is implied.
