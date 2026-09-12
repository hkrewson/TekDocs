# Progress and verification

Updated 2026-09-12. Version 0.8.46. Epic #77; existing delivery obligations remain open.

## Completed implementation slices

The Assets summary collection and typed browser API client are implemented under #86. This is a foundation slice, not completion of Phase 1 or the Assets redesign. The navigation slice adds the data router, capability-derived organization routes and registered Assets edit protection under #88; see [navigation-foundation.md](navigation-foundation.md). See [the API contract and integration notes](asset-collection.md). Personal collection preference persistence and its browser client are the next implemented foundation under #87; the chooser remains pending.

## Phase status

| Phase | Status | Outstanding completion boundary |
|---|---|---|
| 1 — Inventory/foundation | In progress | Expand nested states, list/preview/record UI, URL-backed record/list navigation, personal preference chooser integration and full acceptance evidence; data router and registered Assets edit guards implemented |
| 2 — Assets | Pending | Replace the existing visible layout, wire the collection client, previews/full records, edit guards and responsive verification |
| 3 — Contracts/Networks | Pending | All planned migrations and shared-pattern validation |
| 4 — Operational records | Pending | All planned migrations |
| 5 — Documentation/files | Pending | All planned migrations |
| 6 — Financial/compliance/integrations | Pending | All planned migrations |
| 7 — Shell/remaining surfaces | Pending | All planned migrations |
| 8 — Acceptance | Pending | Technician, browser, production-image and release evidence for every supported surface |

No route is marked migrated. The shell route inventory uses actual App.tsx declarations; organization areas now derive from the existing capability registry. Additional auth/portal/shell states are recorded separately; nested record/workflow coverage remains an explicit task.

## Verified — Assets collection checkpoint

- `make check`: version, supply-chain, repository/security evidence tooling, Wiki/product/language contracts, Compose, workflow lint, backend lint/typecheck, migration drift, OpenAPI drift, generated types, frontend lint/typecheck/unit tests/build and bundle budgets pass (451 frontend tests across 97 files; backend typecheck covers 191 source files).
- Docker focused browser-client tests: five tests pass, including new collection URL encoding, false boolean filters, cancellation forwarding, detail errors without retries, and legacy calls.
- Docker/PostgreSQL focused collection tests pass, including the constrained runtime-role client-access test. Final combined collection/route-inventory check: six tests passed (three collection tests and three route-inventory/authentication/malformed-path checks).
- No schema migration or application version change. Existing API behavior remains covered by compatibility assertions.

## Not yet verified

Whole-page visual migration, the full responsive/browser matrix, preferences migration/upgrade/recovery, technician walkthrough and full release acceptance remain open. The edit-confirmation slice has focused browser evidence; see the checkpoint below. These remain required before the corresponding phase closes. There is no external blocker; this is remaining implementation work.

## Reproduction

Build local development test images (without replacing application containers), then run `make check`. Run focused backend checks with `docker compose run --rm migrate pytest apps/core/tests/test_asset_collections.py apps/core/tests/test_permission_idor_matrix.py -q -k 'asset_collection or asset-collection or test_route_permission_inventory'`. These operate on isolated test data. Frontend coverage includes `frontend/src/inventory/api.test.ts` in the ordinary frontend gate.

The sibling Wiki Roadmap has an uncommitted scoped update. Pre-existing Wiki edits remain untouched. No push, deployment or Wiki publication has been performed.

## Navigation checkpoint — 2026-09-12

- Implemented: data router, capability-derived organization route registration, registered Assets dirty/active/busy edit handling, Keep/Discard/native unload, and independent hardware history refresh with retry.
- Focused browser verification: 27 tests pass across Chromium, Firefox and WebKit. Six viewport widths, 600px height, keyboard focus/background locking, axe checks, Back/Forward, native refresh cancellation, and post-Keep-editing hardware request values are covered.
- Final `make check` passes: 459 frontend tests across 98 files, backend typechecking, contract/drift checks and production build. Original bundle limits remain unchanged: shell 130,940 / 131,072 compressed bytes; shell stylesheet 24,571 / 24,576 bytes. This leaves little shell budget headroom; future foundation components should remain feature-loaded.
- Final `make test-e2e-live` passes, including the real browser journey and independent PostgreSQL fixture verification. The first attempt exposed a delayed modal-dismissal race through its asset-tag database assertion; the fix passes the strengthened request assertions and five repeated Chromium reproductions. No database assertion was weakened.
- Evidence logs: `/tmp/tekdocs-layout-navigation-make-final.log`, `/tmp/tekdocs-layout-navigation-browser-final.log`, `/tmp/tekdocs-layout-navigation-race-repeat.log`, and `/tmp/tekdocs-layout-navigation-live-final.log`. These local logs are ephemeral; the reproducible checks and regression assertions are retained in source.
- Verified scope: the registered Assets editing workflows and shared guard. No external blocker. Wider record navigation, layout acceptance and release gates remain pending rather than inferred from these results.
- Remaining next implementation: personal collection preferences (#87), then the Assets list/drawer/tabbed record slice (#79) and URL/scroll-restoration work remaining in #88. No supported route is yet marked fully migrated.

## Personal preferences checkpoint — 2026-09-12

- Implemented foundation under #87: authenticated Assets preference API, installation/user ownership and forced RLS, migration 0149, generated types and browser client with safe read defaults and explicit write failures. See [personal-preferences.md](personal-preferences.md).
- Verified: 19 focused API/authorization/isolation/CSRF checks passed; the final preference suite separately passed all 12 cases, including malformed requests and upgrade/restore. Six browser-client tests passed. Final `make check` passes with 465 frontend tests across 99 files, backend typechecking over 192 files, migration/OpenAPI/generated-type checks and unchanged bundle limits. Final `make test-e2e-live` passes both the real browser journey and independent PostgreSQL fixture verification. The column chooser and Assets list integration remain pending; no route is marked migrated.
- Next: integrate the preference API into the shared column chooser and replace the Assets collection with the planned responsive list, preview and record navigation (#79).

- Evidence logs (ephemeral local artifacts): `/tmp/tekdocs-preferences-make-verified.log`, `/tmp/tekdocs-preferences-verified-api.log`, `/tmp/tekdocs-preferences-tests-complete.log`, `/tmp/tekdocs-preferences-client2.log`, and `/tmp/tekdocs-preferences-live-final.log`. Reproductions and assertions are retained in source.
- Known limits: last successful preference write wins between devices; there is no chooser UI yet. Full supported backup/recovery, responsive visual acceptance and release gates remain required. No external blocker. The sibling Wiki Roadmap has a scoped, uncommitted update; pre-existing Wiki work is preserved. No push, deployment or Wiki publication.
