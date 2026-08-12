# ADR 0064: Scoped compliance control assignments

Date: 2026-08-12

Status: Accepted for `0.7.2`

## Context

A catalog states what a control says, but not whether one workspace considers it applicable, who is accountable, what implementation state has been observed, or when it should be reviewed. Storing that operational state on the shared control would rewrite other workspaces and historical reviews. Assigning arbitrary people or accepting an owner UUID without current authorization would also create stale or cross-client accountability edges.

## Decision

- Each exact MSP or organization Workspace may have one mutable operational assignment per stable control. The assignment retains the exact control revision most recently reviewed.
- Applicability, implementation status, authorized user owner, and review due date form the current projection. Every save appends an immutable review containing the exact revision and state observed at that decision.
- Owners are active TekDocs users, not ordinary Person/contact records. The server offers and accepts only tenant members with current `compliance.view` authority for the exact Workspace; assignment does not grant access.
- Central `compliance.view`/`compliance.edit` policy, non-disclosing Workspace lookups, PostgreSQL relationship and retention triggers, and forced Workspace RLS protect both the current projection and retained reviews.

## Consequences

Catalog upgrades do not silently claim that a prior review covered new wording; the next review advances the assignment's pinned revision. Removing access makes a former owner ineligible for future assignment without rewriting prior evidence. This slice does not add evidence links, risk treatment, certification claims, or signed bundles.
