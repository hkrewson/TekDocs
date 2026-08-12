# ADR 0065: Reusable compliance evidence

Date: 2026-08-12

Status: Accepted for `0.7.3`

## Context

The same artifact may support several controls, but copying it loses stable identity and review history. A tenant-wide evidence pool would also expose sibling-client material, while a mutable assignment edge could make old evidence appear to cover later control wording.

## Decision

- Evidence is an Entity-backed object owned by one explicit MSP or organization Workspace. It records a bounded note, URL, or exact-Workspace Entity source and an optional valid collection window.
- Evidence can be linked to multiple assignments only inside that Workspace. Every retained edge pins the assignment's exact control revision; advancing a control creates a new edge instead of rewriting prior provenance.
- Evidence reviews are append-only decisions. Central compliance policy, non-disclosing lookups, PostgreSQL relationship/actor/window guards, and forced RLS protect identity, reuse, and history.
- Evidence linkage does not grant visibility. Callers must already be authorized for the exact Workspace.

## Consequences

One artifact can be reused without content duplication while historical claims remain attributable to exact control wording. Evidence is documentation, not certification. Risk treatment, immutable signed bundles, retention exports, and certification remain later slices.
