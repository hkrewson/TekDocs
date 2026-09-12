# Progress and verification

Updated 2026-09-12. Version 0.8.46. Epic #77; existing delivery obligations remain open.

## Completed implementation slice

The Assets summary collection and typed browser API client are implemented under #86. This is a foundation slice, not completion of Phase 1 or the Assets redesign. See [the API contract and integration notes](asset-collection.md).

## Phase status

| Phase | Status | Outstanding completion boundary |
|---|---|---|
| 1 — Inventory/foundation | In progress | Expand nested states, shared UI, navigation, personal preferences, dirty guard and full acceptance evidence |
| 2 — Assets | Pending | Replace the existing visible layout, wire the collection client, previews/full records, edit guards and responsive verification |
| 3 — Contracts/Networks | Pending | All planned migrations and shared-pattern validation |
| 4 — Operational records | Pending | All planned migrations |
| 5 — Documentation/files | Pending | All planned migrations |
| 6 — Financial/compliance/integrations | Pending | All planned migrations |
| 7 — Shell/remaining surfaces | Pending | All planned migrations |
| 8 — Acceptance | Pending | Technician, browser, production-image and release evidence for every supported surface |

No route is marked migrated. The shell route inventory uses actual App.tsx declarations and organization map keys. Additional auth/portal/shell states are recorded separately; nested record/workflow coverage remains an explicit task.

## Verified

- `make check`: version, supply-chain, repository/security evidence tooling, Wiki/product/language contracts, Compose, workflow lint, backend lint/typecheck, migration drift, OpenAPI drift, generated types, frontend lint/typecheck/unit tests/build and bundle budgets pass (451 frontend tests across 97 files; backend typecheck covers 191 source files).
- Docker focused browser-client tests: five tests pass, including new collection URL encoding, false boolean filters, cancellation forwarding, detail errors without retries, and legacy calls.
- Docker/PostgreSQL focused collection tests pass, including the constrained runtime-role client-access test. Final combined collection/route-inventory check: six tests passed (three collection tests and three route-inventory/authentication/malformed-path checks).
- No schema migration or application version change. Existing API behavior remains covered by compatibility assertions.

## Not yet verified

No visual migration, responsive browser matrix, live browser-to-backend walkthrough, preferences migration/upgrade/recovery, technician walkthrough or full release acceptance is claimed. These remain required before the corresponding phase closes. There is no external blocker; this is remaining implementation work.

## Reproduction

Build local development test images (without replacing application containers), then run `make check`. Run focused backend checks with `docker compose run --rm migrate pytest apps/core/tests/test_asset_collections.py apps/core/tests/test_permission_idor_matrix.py -q -k 'asset_collection or asset-collection or test_route_permission_inventory'`. These operate on isolated test data. Frontend coverage includes `frontend/src/inventory/api.test.ts` in the ordinary frontend gate.

The sibling Wiki Roadmap has an uncommitted scoped update. Pre-existing Wiki edits remain untouched. No push, deployment or Wiki publication has been performed.
