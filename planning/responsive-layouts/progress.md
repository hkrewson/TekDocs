# Progress and verification

Updated 2026-09-12. Version 0.8.46. Epic #77; existing delivery obligations remain open.

## Completed implementation slices

The Assets summary collection and typed browser API client are implemented under #86. This is a foundation slice, not completion of Phase 1 or the Assets redesign. The navigation slice adds the data router, capability-derived organization routes and registered Assets edit protection under #88; see [navigation-foundation.md](navigation-foundation.md). See [the API contract and integration notes](asset-collection.md). Personal collection preference persistence and its browser client are the next implemented foundation under #87; the chooser is now integrated in the Assets reference layout; see [assets-layout.md](assets-layout.md).

## Phase status

| Phase | Status | Outstanding completion boundary |
|---|---|---|
| 1 — Inventory/foundation | In progress | Expand nested states, extract reusable record header/sections through validation surfaces, and complete acceptance evidence; list/drawer/chooser and URL-backed Assets records implemented |
| 2 — Assets | In progress | Visible layout, preview assignment and site picker implemented; software history and expanded state/technician/release acceptance remain |
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

## Preview assignment implementation — 2026-09-12

Implemented under #79: a focused Assign hardware action inside the existing preview, using the established assignment choices and write endpoint. Status and assignment editors are mutually exclusive. Choice loading can be retried; failed mutations retain selected person/site/location without automatic retry. Site changes clear incompatible locations, and selecting a location supplies its owning site. Server-returned lifecycle state is accepted after save, including automatic in-stock-to-in-service transitions.

Durable coverage: `Assets.test.tsx` adds denial/conflict/request-failure retention, canceled navigation/discard, failed choice-read retry, site/location consistency and server lifecycle reconciliation. `asset-layout.spec.ts` adds six responsive assignment scenarios per browser with accessibility scans and focus restoration. `live-workspace.spec.ts` now performs assignment in the preview and verifies the result in the full record; its independent database assertions are retained.

During verification, the new browser scenario reproduced exact-label lookup failures for implicit select labels containing options; selectors now have explicit accessible labels, while the named-dialog and exact-label assertions remain. An initial production build failed on unsupported Testing Library `exact` options in new tests; string role names already match exactly, and correcting the test options restores type checking. No production logic or permission assertion was removed to pass either check.

This remains required pre-1.0, at 0.8.46. Site picker, software history, reusable record header/sections, expanded stale/permission-state acceptance, technician/native zoom/screen-reader validation and later surface migrations remain open. No external blocker is known. No schema or API contract changes, migration, push, deployment or publication are part of this slice.

The live assignment rehearsal also reproduced an ambiguous broad Site lookup matching the collection sort selector behind the drawer. Its assignment fields now use exact labels scoped to the named preview; save/full-record/database verification remains unchanged.

The full component gate reproduced an existing MAC-editor timing assumption: its heading arrived before the separate collection permission metadata, so an immediate Add address lookup failed. The test now awaits that authorized control, preserving its mutation and rendered-address assertions. No authorization was bypassed.

Verified runtime and browser evidence: the final focused browser matrix passes 78 tests across Chromium, Firefox and WebKit; the final `make test-e2e-live` passes the isolated Django/PostgreSQL journey and independent database fixture verification. The final live-test lint passes. Logs: `/tmp/tekdocs-preview-assignment-browser2.log`, `/tmp/tekdocs-preview-assignment-live3.log`, `/tmp/tekdocs-preview-assignment-live-lint.log`. Earlier focused component checks passed 21 Assets tests. These logs are ephemeral; source assertions are the durable evidence.

Final project gate: `make check` passes, including 473 frontend tests across 99 files, lint/typecheck, API/schema/generated-type drift, production build and unchanged bundle budgets. Evidence: `/tmp/tekdocs-preview-assignment-check3.log`. Wiki/product contracts and diff checks pass. This checkpoint is implemented and verified within its stated scope; Phase 1/2 and the overall layout epic remain open.

## Assets Site picker checkpoint — 2026-09-12

Implemented under #79/#86: searchable, paginated Site choices in the shared filter menu; named removable URL conditions; refresh/list-return preservation; loading/retry/unavailable-selected handling; and an additive minimal site-choice API. The API returns only site identities already exposed by active authorized assets in the exact workspace, including software installations. It does not expose site addresses or location trees or change Sites-management access. OpenAPI, generated types and route permission inventory are aligned. See [asset-site-filter.md](asset-site-filter.md).

Reproduced and addressed: a narrow-screen filter menu could extend left of the viewport; the Assets toolbar now anchors it within the available width and bounds its scrolling height. Choice rows remain mounted during selected-site metadata refresh. Browser assertions await the checked state after the asynchronous URL transition instead of assuming a synchronous controlled-radio update; checked state, URL, results and selection clearing all remain asserted.

The build budget caught a startup payload overrun. Redundant selected-site copy was removed and standard pagination messages reused. That was insufficient, so the static Overview content was extracted into an on-demand route module as a small #40/#78 navigation-foundation follow-up. The heading, content, capability table and navigation stay unchanged; the route has an explicit loading state and its existing test awaits the loaded heading. No budget was increased. An attempted locale simplification was reverted and is not part of the final implementation.

No schema or model migration, version change, push, deployment or Wiki publication is included. Software history presentation, reusable record header/sections, expanded stale/conflict/permission-transition acceptance, technician/native zoom/screen-reader checks and subsequent surface migrations remain open. The Site picker is no longer an outstanding implementation item; whole-phase acceptance is still required.

The long-value browser scenario reproduced an active-filter chip causing horizontal page overflow at 320 pixels. Filter buttons now wrap long labels within their available width. The final focused matrix passes all 96 checks across Chromium, Firefox and WebKit at 320/390/768/1024/1280/1440 pixels, including off-page site search, refresh, removal and selection clearing (`/tmp/tekdocs-site-browser-final2.log`). The full project gate subsequently passed; the live gate result is recorded below.

The real-stack Site-filter rehearsal reproduced assigned hardware disappearing from collection results. A direct serializer reproduction showed that DRF treated an omitted optional Boolean query parameter as an unchecked HTML checkbox (`assigned=False`). The collection now uses an optional query Boolean field whose omitted value remains absent. Explicit true/false behavior remains intact. Regression coverage includes actual person-assigned hardware filtered by site under the restricted PostgreSQL role, absent/true/false query parsing, and the live response containing the assigned switch after refresh. The temporary live diagnostics were removed; the stronger result assertion remains.

With optional assignment filtering corrected, the live Assets selection/refresh/full-record sequence passed. The continued documentation journey reproduced a broad Markdown assertion matching both a search excerpt and the rendered paragraph. It now matches the exact paragraph text, retaining the imported heading, success state and canonical content checks. No document behavior changed.

Verified project evidence: `make check` passes (475 frontend tests across 100 files, lint/typecheck, schema/generated-type drift, production build and unchanged bundle budgets; `/tmp/tekdocs-site-check6.log`). The final live-assertion lint also passes (`/tmp/tekdocs-site-final-live-lint.log`). All eight collection API tests pass, plus the nine-test focused site/permission/query matrix (`/tmp/tekdocs-site-all-api.log`, `/tmp/tekdocs-site-fixed-api.log`). Wiki/product contracts and diff checks pass. No model migration or recovery-format change is needed. The startup shell/style budgets remain close to their limits; later migrations should continue loading feature content on demand rather than increasing the thresholds.

Verified live evidence: the final `make test-e2e-live` passes the isolated real browser-to-Django-to-PostgreSQL journey and independent database fixture assertions (`/tmp/tekdocs-site-live7.log`). This includes assigning hardware, selecting its site, refresh, full-record navigation, subsequent document import and client-portal/recurring-invoice coverage. Synthetic fixtures were isolated and existing user/demo data was preserved. This bounded Site-picker checkpoint is implemented and verified; no external blocker is known. Whole-phase technician/accessibility/release acceptance remains open. Source tests and this record are durable; `/tmp` logs are ephemeral.

## Shared record navigation checkpoint — 2026-09-12

Implemented under #78/#79 in preparation for #40 and Phase 3: Assets now uses shared RecordHeader and RecordSections components. Complete URLs, ordinary desktop links, the mobile Sections selector, list-return navigation state, record/section heading focus and the existing dirty-form guard are retained. Record content, permissions, urgent warnings and section fetches remain domain-owned. See [record-navigation.md](record-navigation.md) for the consumer contract and remaining validation through Contracts/Networks. No second Assets implementation or demonstration route remains.

Focused component verification passes the integrated Assets suite and shared navigation scenarios, including canceled/discarded mobile changes, retained drafts, URL history, transient state and focus. The browser suite adds section focus and Back/Forward assertions at all six widths. Final project/browser/live results follow after completion. No backend, API/schema/model/recovery-format, version or deployment change is required.

Verified: `make check` passes lint/typecheck, the full component suite, schema/generated-type drift, production build and unchanged bundle budgets (`/tmp/tekdocs-record-nav-check.log`). The final two shared-navigation behavior tests also pass independently after removing a redundant rendering-only assertion (`/tmp/tekdocs-record-nav-focused-final.log`); all 21 Assets integration tests passed in the focused run. All 96 maintained browser checks pass across Chromium/Firefox/WebKit and six widths (`/tmp/tekdocs-record-nav-browser.log`). The isolated `make test-e2e-live` journey and independent PostgreSQL fixture verification pass (`/tmp/tekdocs-record-nav-live.log`). Existing user/demo data was preserved. Wiki/product contracts and diff checks pass.

This extraction checkpoint is implemented and verified; no external blocker is known. Contracts/Networks reuse, software history and whole-phase accessibility/technician/production/recovery/release acceptance remain open. The executable test sources and component contract are durable; temporary logs are ephemeral. No push, deployment or Wiki publication is included.
