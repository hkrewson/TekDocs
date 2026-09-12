# Personal collection preferences (#87)

Required pre-1.0 foundation; version remains 0.8.46. This slice provides persistence and the typed browser client. The column chooser and visible Assets layout remain #79 work; #87 stays open until their integration is verified.

## Ownership and API

`CollectionPreference` stores only tenant (installation), authenticated user, feature identifier, column identifiers and page size, plus identity/timestamps. The unique key is `(tenant, user, feature)`; no workspace identifier, filter, record value or client selection is persisted. Assets is the first registered feature. Future features must add their own reviewed column policy and default list.

The additive routes are `/api/v1/workspaces/msp/collection-preferences/{feature}` and `/api/v1/workspaces/organizations/{organization_entity_id}/collection-preferences/{feature}`. Both address the same personal preference, but resolve and authorize the requested workspace before reading or writing it. Assets requires ASSETS_VIEW, including for personal preference writes: read-only technicians can arrange their own display without gaining asset-edit permission. Preferences are personal presentation changes, not privileged domain mutations. The existing route authorization inventory records this distinction without weakening its MFA requirements for domain mutations.

- GET returns `columns`, `page_size`, `available_columns`, and `default_columns`. It does not create a row. Missing preferences return curated defaults and 25 rows.
- PUT replaces columns and page size. Only 25/50/100 are allowed. Name is mandatory; unknown, unavailable and duplicate columns are rejected. The stored/result order is curated, regardless of request order.
- DELETE removes the preference and returns defaults. It accepts no body.
- Unknown features return 404. Extra query parameters and unknown request fields are rejected. User, tenant, filter and record-value injection is not accepted. Responses are private and non-cacheable.

Each read and write reapplies current feature and column policy. Restricted identifiers are omitted from available/default/selected lists. A narrower workspace does not mutate the stored preference merely by reading it. A later explicit save replaces the whole personal selection with the current permitted selection. Concurrent device writes use last successful write wins; there is no automatic merge or background mutation retry.

Assets currently grants all six columns under ASSETS_VIEW: name, model, status, assignment, site and warranty. The policy registry supports per-column permissions; a regression test restricts warranty after persistence to verify filtering. The actual product does not invent a new warranty permission. Current workspace resolution is for operational Assets owners; future catalog/vendor feature registration must use its own appropriate resolver.

## Database and upgrade/recovery

Migration `0149_collectionpreference` creates the table, unique/page-size constraints and forced row-level security in one migration. Its reviewed classification is in `rls_contract.py` and `validation.py`. RLS requires the current tenant and current user, independently of workspace. Explicit trusted system principals retain tenant-scoped maintenance access. Unbound actors do not receive personal rows. Ordinary users cannot retarget rows to another user or tenant.

Tests migrate from pre-feature 0148 to current head, verify the forced policy, round-trip persisted choices through Django fixture export/restore and recheck database constraints. Migration tests restore current head in `finally`; they do not leave a pinned schema behind. These are focused preference upgrade/restore checks, not a replacement for full supported database backup/recovery and release rehearsals. The table contains no domain data; downgrading past 0149 removes personal choices, which then return to defaults on upgrade.

## Browser integration contract

`frontend/src/collections/preferences.ts` uses generated API types, exact workspace paths and CSRF-protected writes. Load failures return current permitted defaults without blocking the list; cancellation remains cancellation so late results cannot replace the current workspace state. There is no global/local-storage cache that could leak another user's choices. Callers supply their currently permitted curated identifiers, and successful responses are projected through both that list and the server's permission-filtered identifiers.

Save/reset failures reject rather than pretending the preference was saved; callers must retain the chooser draft and show an error. Writes are not automatically retried. List data authorization remains authoritative even when preference loading falls back. The integration must reload when user or workspace permissions change, apply URL page-size precedence deliberately, and clear page-only selection when page size changes. The forthcoming chooser must retain identity, use curated ordering and offer Reset to defaults.

## Verification

Final results are recorded in progress.md. API tests exercise default/save/reset, cross-workspace and cross-device continuity, unknown/private values, user/tenant isolation, revoked workspace access, column permission changes, runtime-role retarget denial and upgrade/restore. Browser-client tests cover safe defaults, canceled reads, permission projection, CSRF and failed writes without retries. The live workspace journey writes a technician preference through Django/PostgreSQL, reads it from the MSP workspace, verifies a separate owner's defaults and resets it.

No visible surface is marked migrated. No version bump, deployment, user/demo-data alteration or Wiki publication is part of this slice.

Reproduce locally by building the development test images (`docker compose build backend migrate`), running `make check`, and running `docker compose run --rm migrate pytest apps/core/tests/test_collection_preferences.py apps/core/tests/test_entity_rbac_validation.py apps/core/tests/test_permission_idor_matrix.py -q -k 'collection_preferences or every_tenant or route_permission_inventory or collection-preferences'`. `make test-e2e-live` creates an isolated production-image stack and runs the real session journey. None of these commands replace the running application containers.
