# Progress and verification

Updated 2026-09-12. Version 0.8.46. Epic #77; existing delivery obligations remain open.

## Completed implementation slices

The Assets summary collection and typed browser API client are implemented under #86. This is a foundation slice, not completion of Phase 1 or the Assets redesign. The navigation slice adds the data router, capability-derived organization routes and registered Assets edit protection under #88; see [navigation-foundation.md](navigation-foundation.md). See [the API contract and integration notes](asset-collection.md). Personal collection preference persistence and its browser client are the next implemented foundation under #87; the chooser is now integrated in the Assets reference layout; see [assets-layout.md](assets-layout.md).

## Phase status

| Phase | Status | Outstanding completion boundary |
|---|---|---|
| 1 — Inventory/foundation | In progress | Expand nested states, extract reusable record header/sections through validation surfaces, and complete acceptance evidence; list/drawer/chooser and URL-backed Assets records implemented |
| 2 — Assets | In progress | Visible layout replaced; preview assignment, site picker, expanded state/technician/release acceptance remain |
| 3 — Contracts/Networks | Pending | All planned migrations and shared-pattern validation |
| 4 — Operational records | Pending | All planned migrations |
| 5 — Documentation/files | Pending | All planned migrations |
| 6 — Financial/compliance/integrations | Pending | All planned migrations |
| 7 — Shell/remaining surfaces | Pending | All planned migrations |
| 8 — Acceptance | Pending | Technician, browser, production-image and release evidence for every supported surface |

No route is marked fully accepted. Assets has an implemented replacement layout with remaining acceptance work. The shell route inventory uses actual App.tsx declarations; organization areas now derive from the existing capability registry. Additional auth/portal/shell states are recorded separately; nested record/workflow coverage remains an explicit task.

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

## Assets visible layout checkpoint — 2026-09-12

Implemented under #79: bounded summary table/mobile rows, persistent column chooser/reset and page size, shared modal preview with bounded status action, record/section URLs, focused tabs and on-demand hardware history, list context/focus restoration, page-only selection and registered relationship editing. The old split layout and lifecycle below the collection are removed. See [assets-layout.md](assets-layout.md) for implementation details, URL compatibility, reproduction notes and remaining scope.

**Verified:** `make check` passes, including 468 frontend tests across 99 files, lint/typecheck, API/schema/type drift and unchanged production bundle budgets. Final focused browser matrix passes 60 tests across Chromium, Firefox and WebKit at 320/390/768/1024/1280/1440px and short heights, plus touch and 200% CSS zoom stress. Final `make test-e2e-live` passes the isolated browser-to-Django-to-PostgreSQL journey and independent database fixture verification. Desktop list and 320px preview screenshots were visually inspected. Final browser-test lint and `git diff --check` pass.

Reproductions retained in source: preference reset previously opened an unintended navigation confirmation; a commit-boundary reset fixes it (five repeated checks). Viewport-unit drawer height exceeded the zoomed viewport; inset sizing fixes the bounds assertions in all engines. A save-button-disabled assertion could mean either pending or completed save, so closing tests now also await the status selector becoming enabled. A deterministic paused-request browser scenario verifies pending saves retain close protection; filtered departure passed five repeat checks before the full matrix.

Evidence logs (ephemeral): `/tmp/tekdocs-assets-layout-check3.log`, `/tmp/tekdocs-assets-layout-browser6.log`, `/tmp/tekdocs-assets-layout-live3.log`, `/tmp/tekdocs-assets-filter-repeat.log` and `/tmp/tekdocs-assets-layout-final-lint.log`. Durable assertions are linked from the implementation record.

**Remaining, not blocked:** preview assignment, site chooser, software history presentation, reusable record header/sections, expanded stale/conflict/permission-state acceptance, manual native zoom/screen-reader/mobile-keyboard and technician walkthroughs, followed by applicable production/recovery/release gates. CSS zoom does not substitute for native browser zoom acceptance. Other surfaces remain pending. No phase/epic closure is claimed. Version remains 0.8.46; no push, deployment or Wiki publication. The sibling Wiki has a scoped local checkpoint alongside preserved earlier edits.
