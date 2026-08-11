# ADR 0038: Inventory and credential-reference stabilization

Status: accepted for `0.3.12`

## Context

The inventory domain now spans supplier catalog provenance, hardware lifecycle, software installations and entitlements, contracts and protected costs, attachments, relationships, CSV transfer, and external credential pointers. Its first implementation slices proved each boundary independently, but ordinary collection APIs remained unbounded and no one gate exercised their combined concurrency, recovery, upgrade, restore, authorization, and reference-data behavior.

Credential references deliberately store only validated provider pointers. Because TekDocs neither retrieves nor proxies the provider item, it also cannot truthfully assert that a saved pointer remains valid after an item is moved, deleted, or removed from the viewer's vault access.

## Decision

- Asset, software-license, contract, and credential-reference collection APIs use one bounded page contract. Page size defaults to 50 and cannot exceed 100; responses include exact `page`, `page_size`, `count`, and `has_more` metadata and retain stable model ordering.
- Pagination is applied only after exact Workspace scoping and central-policy authorization. MSP pages remain MSP-owned only; they never become cross-client aggregate views.
- Credential-reference collection serialization computes permission projections once per authorized collection. It never includes the provider URL. Opening remains a separately authorized, audited redirect whose event metadata is empty.
- The interface exposes native, keyboard-operable previous/next controls and clears or reloads collection state when query, page, or Workspace changes. Provider guidance explicitly explains that a stale 1Password pointer must be replaced with a newly copied Private Link.
- A PostgreSQL reference fixture composes the existing 100-client/10,000-entity/2,500-revision dataset with 120 assets, 60 licenses, 120 contracts, and 120 credential references. Selected 25-row pages must remain below the 500 ms local p95 threshold and within a fixed 32-query request ceiling, including session, RLS, Workspace, and policy resolution.
- Seat allocation is certified with competing database transactions against a one-seat entitlement. Archive/recovery tests retain immutable catalog/lifecycle provenance, CSV operations remain atomic and retry-safe, cost-denied responses remain structurally absent, and archived credential pointers cannot be listed or opened.
- Dedicated `0.3.11` upgrade and clean database/media restore rehearsals verify representative Workspace, catalog revision, asset provenance, lifecycle, license/seat, contract/cost, CSV identity, credential-pointer, attachment, and audit state.
- `make test-inventory-certification` composes inventory, commercial, credential, recycle-bin, IDOR, forced-RLS, migration, concurrency, and performance suites. It supplements rather than replaces the complete release gate.

## Consequences

Exact counts add a bounded count query and offset pagination is not the final search architecture. It is acceptable for this pre-1.0 operational surface and prevents accidental full-table browser responses. Cursor pagination or indexed search may replace it only with an explicitly versioned API decision and equivalent authorization evidence.

The 32-query ceiling is a whole-request ceiling, not evidence of an N+1 allowance: it includes session bookkeeping, transaction-local RLS binding, Workspace resolution, policy checks, the count, and a fixed set of related-data prefetches. The reference test fixes the page at 25 rows so a per-row regression breaches the ceiling.

TekDocs still does not know whether a 1Password item exists or whether the current user may reveal it. That authorization and truth remain solely with 1Password.
