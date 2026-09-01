# ADR 0094: Unified workspace search

Status: accepted
Date: 2026-08-31

## Decision

TekDocs provides one normalized lexical search contract for documentation and operational records in the active workspace. The server begins with the existing permission-filtered Entity visibility query, applies an explicit public record-family and safe-field allowlist, and only then computes ranking, excerpts, facets, counts, and application targets.

The search remains PostgreSQL-backed and does not add an external index or second authorization authority. Query text, terms, result types, pages, page size, candidate count, excerpts, ordering, and database statement time are bounded. Exact and prefix title matches outrank identifiers; identifiers outrank resolved document-body matches. Stable display-name, result-family, and UUID tie-breaks make pagination reproducible.

The API returns one projection for every family: stable ID, public result type, internal entity type, title, bounded safe excerpt, workspace label, numeric relevance, update time, optional document review state, and an application-relative target. The browser treats that target as navigation, never authorization; the destination route reauthorizes the record.

## Isolation and disclosure

- MSP queries remain MSP-owned and never aggregate client workspaces.
- Organization queries resolve one authorized organization and do not widen into sibling or reference-organization records.
- Archived, withheld, sibling-workspace, foreign-tenant, and otherwise inaccessible records cannot affect results, excerpts, facets, counts, or pagination.
- Only fields already disclosed by normal read surfaces are allowlisted. Credential pointers, secret values, provider payloads, audit metadata, financial values, and arbitrary custom fields are excluded.
- Direct destination routes remain authoritative when a record changes or access is revoked after search.

## Consequences

Operators can discover documentation and safe operational identifiers without learning which subsystem owns a record. PostgreSQL remains the single data and permission authority, and changes are immediately searchable without an asynchronous indexing delay. If scale later requires maintained full-text columns or another index, it must preserve this authorization-before-projection contract and prove equivalent denial, RLS, ranking, pagination, upgrade, and restore behavior.
