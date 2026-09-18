# Progress and verification

Updated 2026-09-17. Version 0.8.46. Epic #77; existing delivery obligations remain open.

## Completed implementation slices

The Assets summary collection and typed browser API client are implemented under #86. This is a foundation slice, not completion of Phase 1 or the Assets redesign. The navigation slice adds the data router, capability-derived organization routes and registered Assets edit protection under #88; see [navigation-foundation.md](navigation-foundation.md). See [the API contract and integration notes](asset-collection.md). Personal collection preference persistence and its browser client are the next implemented foundation under #87; the chooser is now integrated in the Assets reference layout; see [assets-layout.md](assets-layout.md).

## Phase status

| Phase | Status | Outstanding completion boundary |
|---|---|---|
| 1 — Inventory/foundation | In progress | Expand nested states, extract reusable record header/sections through validation surfaces, and complete acceptance evidence; list/drawer/chooser and URL-backed Assets records implemented |
| 2 — Assets | In progress | Layout, preview actions, site filtering and software audit history implemented; expanded state/technician/release acceptance remains |
| 3 — Contracts/Networks | In progress: Contracts and simplified Networks collection/full record migrations | Remaining network object surfaces, wider validation and phase acceptance |
| 4 — Operational records | In progress: Organizations/People/Sites accepted; Stock workspace complete | Complete the connected vendor catalog, products, and licenses, then run grouped live-stack acceptance; see [operational-records.md](operational-records.md) and [stock-workspace.md](stock-workspace.md) |
| 5 — Documentation/files | Pending | All planned migrations |
| 6 — Financial/compliance/integrations | Pending | All planned migrations |
| 7 — Shell/remaining surfaces | Pending | All planned migrations |
| 8 — Acceptance | Pending | Technician, browser, production-image and release evidence for every supported surface |

No route is marked fully accepted. Assets has an implemented replacement layout with remaining acceptance work. The shell route inventory uses actual App.tsx declarations; organization areas now derive from the existing capability registry. Additional auth/portal/shell states are recorded separately; nested record/workflow coverage remains an explicit task.

## People record workspace checkpoint — 2026-09-17

Implemented as the first piece of the grouped Organizations/People/Sites milestone under #81. Person names now open the complete record in the shared right-side drawer and full-screen mobile presentation. The overview exposes contact, role, responsibility, relationship, site and location details. Creation and editing stay within that workspace; the prior page-level overlay is removed. The `person` URL parameter restores records outside the current page using the existing scoped detail endpoint, with explicit loading and unavailable states. Failed mutations retain the form, Escape/backdrop/mobile return use a dirty-change guard, and archive retains its explicit confirmation.

Verified: 13 focused People component/client scenarios pass, including an off-page direct link, complete overview, inline editing, retained denial, structured placement, archive, and canceled/discarded dirty dismissal. The full frontend gate passes lint, typechecking, OpenAPI drift, 584 tests across 116 files, the production build, and unchanged compressed bundle limits. No backend, schema, migration, version, deployment, or Wiki publication change is required. Sites and Organizations remain open in this same milestone; grouped responsive browser and live-stack acceptance is deferred to that boundary as recorded in [operational-records.md](operational-records.md).

## Sites record workspace checkpoint — 2026-09-17

Implemented as the second piece of the grouped Organizations/People/Sites milestone under #81. The expanded site-card layout is replaced by a bounded, searchable, sortable, paginated collection and one responsive record drawer. The drawer combines address and contact facts, the complete nested location hierarchy, custom fields, and guarded site/location create, edit, and archive actions. Search, sort, page, and selected-site URL state restore on refresh; a direct selected-site URL retrieves records outside the current page. Failed writes retain the active form, dismissal protects dirty edits, and archiving a parent location immediately removes its complete descendant branch from the open record.

The Sites API now returns canonical page metadata, applies deterministic server ordering, caps page size, and rejects undeclared query parameters. OpenAPI and generated TypeScript contracts are aligned. Focused Sites component/client tests, the full PostgreSQL Sites module, and the reference collection query-budget test pass. The full project gate passes backend lint and typing, migration and API-schema agreement, all 585 frontend tests across 116 files, coverage, the production build, and unchanged compressed bundle limits. Organizations remains open; grouped responsive browser and live-stack acceptance is deferred to that boundary as recorded in [operational-records.md](operational-records.md).

## Organizations/People/Sites milestone acceptance — 2026-09-17

Organizations completes the first grouped Phase 4 journey. The former organization cards and modal editor are replaced by a bounded, searchable, filterable, sortable, paginated collection and the shared responsive record drawer. The drawer provides complete organization facts, classifications, access mode, custom fields, guarded create/edit/archive actions, and the existing client-workspace entry. Selected records and collection state are URL-addressed, including off-page direct records and Back/Forward restoration. The Organizations API and generated contract now expose canonical page metadata and direct detail retrieval without changing workspace authorization rules.

All 21 grouped responsive scenarios pass across Chromium, Firefox, and WebKit at the six required widths, covering long values, page bounds, accessibility, history, keyboard dismissal, and dirty-change protection. The surrounding 894-test browser run had one unrelated Chromium Markdown-editor timing failure; that unchanged test passed immediately in focused rerun and also passed in WebKit during the matrix. The project checks pass backend lint and typing, migration and OpenAPI agreement, all 587 frontend tests across 116 files, coverage, the production build, and unchanged compressed bundle budgets; an unchanged Circuit test that raced in the first full run passed all eight cases in isolation and in the clean full frontend rerun. The real browser-to-Django-to-PostgreSQL journey passes end to end with persisted organization, People, Site, location, and custom-field checks. The next substantial Phase 4 piece is the connected vendor catalog, products, licenses, and stock journey. Version, deployment, and Wiki publication remain unchanged.

## Stock collection and record workspace checkpoint — 2026-09-17

Completed the Stock piece of the vendor catalog, products, licenses, and stock milestone under #81. The former split list/detail page and separate editors are replaced by a bounded, searchable, sortable, paginated collection and one complete responsive drawer. Search, sort, page, and selected-item state are URL-addressed. Direct links retrieve authorized items outside the current page. The drawer combines purchasing provenance, exact pricing, quantity and reorder facts, external order/tracking links, append-only movement history, and guarded create, edit, adjustment, and archive actions.

The server rejects undeclared collection parameters, caps page size, returns canonical metadata, and exposes scoped detail reads while retaining the existing invoice permission and tenant boundary. Immediate dirty-state notification closes a keyboard timing gap found by the responsive browser run: Escape directly after typing now always offers Keep editing or Discard changes. OpenAPI and generated TypeScript types are aligned.

Verified: six focused PostgreSQL scenarios pass. All 21 Stock browser scenarios pass across Chromium, Firefox, and WebKit at 320, 390, 768, 1024, 1280, and 1440 pixels, including long values, bounds, focus, accessibility, and immediate dirty dismissal. The project frontend gate passes all 590 tests across 117 files, localization enforcement, coverage, typechecking, the production build, and unchanged compressed bundle budgets. Vendor catalog, products, and licenses remain before grouped live-stack acceptance. Version, deployment, Wiki publication, and existing user/demo data remain unchanged.

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

## Software audit history checkpoint — 2026-09-12

Implemented under #79/#86: software History now reads actual creation/update audit events for the selected record, on demand, with 25-event pages and URL-addressed history page state. The existing Activity permission is preserved. Empty, denied, failed, loading and retry states are distinct; canceled/late reads cannot replace another page. This does not invent past installation values or expose metadata. See [software-history.md](software-history.md) for API and navigation contracts.

The additive activity entity filter is applied within the existing workspace/tenant scope before counts and action summaries. Legacy consumers retain their defaults. OpenAPI/generated types document the supported query interface. Focused API/runtime-role and component/client checks pass; final full project/browser/live results follow. No model/migration/RLS/recovery-format or version change is required. Contracts/Networks and broader phase acceptance remain open.

Verification reproduced a blank `entity_id=` being discarded by DRF as an omitted optional HTML form field, broadening the activity query. The new filter now preserves supplied values for UUID validation; blank/malformed identifiers are rejected, while genuine omission retains legacy workspace activity. A regression assertion covers the blank case. The initial live run completed software History but its renderer crashed later during publication withdrawal; the rerun uses the unchanged journey assertions after other heavy checks finish. Test-helper lint findings were corrected without removing its canceled/stale-response assertions.

Verified project evidence: `make check` passes with 480 frontend tests across 102 files, API/generated-type drift, lint/typecheck, production build and unchanged bundle budgets (`/tmp/tekdocs-software-history-check3.log`). Final backend lint/typecheck/schema drift checks also pass after the blank-filter fix (`/tmp/tekdocs-software-history-final-backend.log`). All four focused API scenarios pass, including restricted-role pagination and blank/malformed query denial (`/tmp/tekdocs-software-history-api2.log`). All 114 browser checks pass across three engines and six widths, including completed-page heading focus (`/tmp/tekdocs-software-history-browser2.log`). Wiki/product contracts and diff checks pass. The final live result follows below.

Verified live evidence: the final isolated `make test-e2e-live` passes the real browser-to-Django-to-PostgreSQL journey and independent database fixture assertions (`/tmp/tekdocs-software-history-live2.log`). Actual software creation/update events are visible after installation editing and refresh. The later publication withdrawal and portal/recurring workflows also pass with unchanged assertions; the earlier renderer crash was not reproduced. Existing user/demo data was preserved. No external blocker is known.

The final visible-focus check reproduced the History heading receiving focus outside the viewport on four Chromium desktop widths after paging. History page navigation now allows the browser to bring its focused heading into view; record/list return restoration is unchanged. The strengthened assertion requires both focus and viewport visibility across all maintained widths/engines.

Final focus correction verified: targeted lint/typecheck/production build and all 18 software-history browser scenarios pass with both heading focus and viewport visibility asserted (`/tmp/tekdocs-software-history-focus-fixed.log`). This is the focused follow-up to the passing 114-test matrix and full project gate. The bounded software-history checkpoint is implemented and verified. Contracts/Networks reuse and remaining phase accessibility/technician/production/recovery/release acceptance stay open. No push, deployment or Wiki publication is included. Executable tests and these notes are durable; temporary logs are ephemeral.

## Full asset record drawer checkpoint — 2026-09-13

User validation revised #79: the quick preview repeated the row and added an unnecessary full-record step. Asset names now open the complete record in a broad overlay/full-screen mobile drawer. Both presentations share AssetRecord sections and editing; the row-level Open record link is removed, with optional Open in full page inside the drawer preserving the selected section. The accepted contract, route/state inventory and implementation notes are updated; see [asset-record-drawer.md](asset-record-drawer.md). Version remains 0.8.46.

The drawer uses shared assignment, detail, network/installation, relationship and history content. The former quick-status component and duplicated assignment editor are replaced by shared Overview editing. Close exits the whole drawer after section navigation, with dirty/busy protection; URLs and browser navigation remain compatible. Screenshots exposed tiny inherited lifecycle text and redundant section spacing; record-scoped styling now restores readable fact/form sizes and a compact heading. Background locking and a single drawer scrolling body remain.

The first browser run reproduced a test race: its new reopen/Escape sequence sent Escape before the asynchronously opened drawer mounted, then attempted to click the now-inert background. The test now waits for the visible drawer and focused Close button before Escape. No application delay, forced click, reduced assertion, or weakened timeout was added. Final gate evidence follows below. No backend/API/model/recovery-format change is needed; user/demo data remains protected. Local refresh is authorized; production deployment and publication remain separate.

The next completed matrix exposed a second transition race in two narrow Chromium cases: the test matched the still-open drawer heading after clicking Open in full page, then changed its Sections selector before navigation completed. The browser test now requires the drawer to close, the record URL to appear, and the full-page h1 to be visible before section interaction. All heading-focus and Back/Forward assertions remain.

Verified: `make check` passes all 480 frontend tests across 102 files, lint/type/schema checks, production build and unchanged bundle budgets (`/tmp/tekdocs-full-drawer-check.log`). Final record-scoped readability styling and explicit browser-transition assertions are covered by the follow-up lint/build/browser run. The local Wiki Roadmap has the scoped contract update, but a full-checkout Wiki validation is blocked by pre-existing missing pages in this older local Wiki clone; the repository manifest/contextual-topic contract passes. No missing pages were fabricated or unrelated Wiki work overwritten.

Verified final browser evidence: all 117 checks pass across Chromium, Firefox and WebKit at 320/390/768/1024/1280/1440 pixels, including drawer section refresh/close, full-page transitions, dirty edits, assignment, focus, accessibility scans and touch/CSS zoom (`/tmp/tekdocs-full-drawer-browser-final.log`). The same final run passes frontend lint, typechecking, production build and unchanged bundle budgets after the readability adjustment. Desktop/mobile screenshots were visually inspected; executable tests and the contract notes are durable, while `/tmp/tekdocs-full-drawer-images` and logs are ephemeral. Live evidence follows below.

Verified live evidence: `make test-e2e-live` passes the isolated real browser-to-Django-to-PostgreSQL journey and independent database fixture assertions (`/tmp/tekdocs-full-drawer-live.log`). Hardware details, assignment and network addresses save inside the full drawer, with retained full-page verification. Subsequent documentation, portal and recurring workflows pass. Existing user/demo data was preserved. The bounded full-drawer implementation is verified; broader phase/technician/release acceptance and the pre-existing incomplete local Wiki checkout remain open.

## Assets refresh/public-port correction — 2026-09-13

Follow-up to #79 at 0.8.46: direct HTTP reproduction returned `301 Location: http://localhost:8080/assets/` for `/assets` at local port 3200. An HTTPS-proxy-header reproduction also returned `http://docs.example.invalid:8080/assets/`. The route collided with Nginx's physical bundle directory; client-side navigation avoided the document request, explaining intermittent refresh behavior. Both route spellings now serve the revalidated entry document directly, and Nginx-generated directory redirects are relative. Bundle caching, missing-chunk 404s and security headers remain intact.

Verified: the new real-production-image `make test-frontend-routing` gate passes all three scenarios, including local/proxy route subcases and static-file behavior (`/tmp/tekdocs-port-routing-final.log`). Its corrected root-directory probe independently failed against the old image with the exact internal-port Location before passing with the fix (`/tmp/tekdocs-port-routing-before2.log`). The gate is included in release acceptance. See [frontend-routing.md](frontend-routing.md) for cached-redirect recovery and rollout boundaries. No backend/API/schema/recovery-format or version change is involved. Final project/local-refresh evidence follows.

Verified final evidence: `make check` passes, including 480 frontend tests, lint/type/schema checks, production build and unchanged bundle budgets (`/tmp/tekdocs-port-routing-check.log`). The authorized local frontend rebuild completed; direct `/assets` with preview/section parameters and `/assets/` under HTTPS proxy headers now return 200 HTML with no Location header and revalidation/security headers. Local readiness reports healthy database/renderer and version 0.8.46. The local Wiki Roadmap is updated without publishing. Production deployment is not performed; the shared-image reproduction supports the cause there, but the remote instance has not been inspected or changed.

## Asset drawer backdrop dismissal — 2026-09-13

User-requested #79 follow-up: outside clicks dismiss the drawer and the Close button is removed. Escape remains; full-screen mobile provides a Back to assets link because there is no exposed backdrop. The dialog heading receives initial focus and Shift-Tab keeps focus inside. Dismissal requires a gesture starting and ending outside, so internal clicks and drag-out gestures remain safe. All paths use the existing dirty/busy guard and list-return callback. The accepted contract, drawer/navigation notes and state inventory are updated. Version stays 0.8.46; no API, model, migration or recovery-format changes are needed. Component checks pass; final browser/project/live evidence follows.

Verified project/browser evidence: `make check` passes all 480 frontend tests, lint/type/schema checks, production build and unchanged bundle budgets (`/tmp/tekdocs-backdrop-check.log`). All 120 focused browser checks pass across Chromium/Firefox/WebKit and six widths (`/tmp/tekdocs-backdrop-browser.log`), including native backdrop gestures, blocked underlying navigation, internal clicks, drag-out protection, mobile return, failed/pending saves, focus restoration, accessibility and touch/CSS zoom. The repository Wiki contract and diff checks pass. Final isolated live and local-refresh evidence follows.

Verified live evidence: `make test-e2e-live` passes the isolated browser-to-Django-to-PostgreSQL journey and independent fixture assertions (`/tmp/tekdocs-backdrop-live.log`). Outside clicks now exercise both dirty Keep editing and clean dismissal after hardware/network saves. Later document, portal and recurring workflows pass unchanged. Existing user/demo data was preserved. The bounded dismissal follow-up is verified; broader layout rollout and technician/release acceptance remain open. Local refresh is authorized; production and Wiki publication remain separate.

## 2026-09-13 — Contracts visible migration (#80)

Contracts in MSP/client workspaces now replaces the old split panels with a bounded
collection and shared full record drawer/page. Overview, Costs, permitted Related
and actual History are URL-addressable. Costs keep currencies/intervals separate;
summary requests never read cost rows and legacy consumers retain their projection.
Personal preferences reuse the existing model; no migration or version change.
See [contracts-layout.md](contracts-layout.md) for the complete implementation and
handoff boundary. Networks remains the next visible migration, not a completed one.

Browser verification: 120 Assets/Contracts checks passed across Chromium, Firefox
and WebKit, plus three contract touch/200% CSS zoom checks. Contract coverage includes
six widths, native-dialog accessibility, focus, outside dismissal, failed-edit guards,
column persistence/reset, off-page search, denied costs and unavailable direct links.
Synthetic mobile/desktop screenshots were reviewed locally. Component-focused checks
passed for Contracts, SoftwareHistory and Assets (28 tests); API-client coverage was
expanded for the explicit summary and detail requests.

Reproduced harness issues: the first new browser tests sent Escape before drawer
focus and refreshed before the preference write completed; synchronization now waits
for those outcomes without removing assertions. The live journey's existing Assets
site check captured an outstanding pre-refresh response whose body was invalidated by
navigation. It now consumes the applied filter response before testing refresh. The
first broad frontend pass had one unrelated SearchResults test exceed its timeout
under concurrent Docker work (480 others passed); that unchanged test passes isolated
(4/4). The full gate is being rerun with fewer concurrent jobs; final results follow.

Final broad verification: `make check` passes (102 component files, 481 tests,
OpenAPI/types, Python lint/type/migration checks and production bundle budgets).
The unchanged SearchResults test passes in the full rerun. The isolated live
browser-to-Django-to-PostgreSQL journey passes, including contract creation, cost
creation, history refresh, subsequent recurring enrollment/stop and retained
record/audit assertions. Browser checks remain 120 combined plus 3 touch/zoom.
No domain-data migration or version change was introduced. Final API/local runtime
completion is recorded below.

API/runtime completion: `make test-commercial` exited successfully, covering
commercial records, recycle bin, permission/IDOR, runtime RLS and migration
stabilization (the suite retains its existing skipped case). `make up` completed
with existing data volumes retained. Local `/api/v1/health/ready` reports status ok,
database/renderer ready and version 0.8.46; `/services` returns 200. Backend/frontend
health checks pass. This is the authorized local refresh only; no production
publication, push or tag occurred. The Wiki Roadmap checkpoint is updated locally.

Verified: this bounded Contracts implementation and the gates above. Inferred:
the transient unrelated search timeout was resource contention; no test or search
code was changed to make it pass. Blocked: none for this checkpoint. Still open:
Networks, later surface migrations, technician/assistive-technology acceptance and
full pre-1.0 release/recovery obligations. Temporary logs/screenshots are local;
executable test sources and these notes are the durable evidence.


## 2026-09-13 — Simplified Networks visible migration (#80)

The supported Networks page now uses bounded responsive rows and full record
drawers/pages. Curated personal columns, global search/VLAN filter/order, on-demand
detail/history, protected inline editing and an optional relationship map replace
the original wide scrolling table and always-loaded topology. Calculated gateways,
range/overlap validation and existing network permissions remain authoritative.
Existing APIs remain compatible; selected GET details and summary query options are
additive. No model/migration/recovery-format/version change. See
[networks-layout.md](networks-layout.md) for the exact scope and follow-up inventory.

Focused component tests pass. All 24 six-width browser checks pass across Chromium,
Firefox and WebKit. Initial mocked-browser failures were reproduced: an overly broad
API mock intercepted page refresh URLs; after narrowing it, the conflict test lacked
the random CSRF cookie required by the real client. The tests retain the assertions
and now exercise their intended request boundaries. Touch/zoom and full gates follow.

Do not mark Phase 3 complete: legacy device/rack/addressing/interface/wireless/DNS/
circuit/NetBox interfaces are not mounted by the current shell and still require
explicit disposition, parent/child layout work and acceptance. Technician walkthroughs
and the existing pre-1.0 security/recovery/release obligations remain open.

The full project gate passes: 102 component files / 481 tests, backend lint/type
and migration checks, OpenAPI/generated types, and production bundle budgets.
All 24 network browser scenarios pass, plus 3 touch/200% CSS zoom scenarios.
Mobile editor screenshots were reviewed locally. The touch test initially used a
DOM-test-only required-field matcher; the browser test now asserts the same native
required property with Playwright's supported matcher. No application assertion was
removed. The final summary/detail TypeScript boundary also passes focused lint and
type checks; summaries cannot be treated as loaded descriptions/notes.

The isolated live browser-to-Django-to-PostgreSQL journey passes, including network
creation, calculated range/gateway and DNS in the drawer, refresh, collection search,
and independently retained database records. The authorized local rebuild completed
with existing volumes retained. Local readiness reports database/renderer ready,
status ok and version 0.8.46; `/networks` returns 200. No production push/publication
or version change. The broader network-validation gate remains in progress; final
completion is recorded below.

Final network validation passed: `make test-network-validation` exited successfully,
covering network inventory/addressing/endpoints/services/circuits, reconciliation,
transfer, relationships, permission/IDOR, runtime RLS, migration stabilization,
network stabilization and a second complete 481-test frontend pass. The existing
suite skip remains unchanged. Final focused type/lint checks pass after tightening
the summary type. Wiki manifest and whitespace checks pass.

Verified: this bounded simplified Networks migration, all checks above, the isolated
live journey and healthy local 0.8.46 runtime. No blocker remains for this checkpoint.
No broader advanced-network or whole-phase acceptance is inferred from those results.
The tracked implementation notes and executable tests are durable; temporary logs and
synthetic screenshots remain local. Production deployment, publication and all
remaining pre-1.0 delivery obligations are separate and remain open.

### 2026-09-13 — Parent network address collection (Phase 3 #80)

Implemented the next bounded slice: IP addresses inside the supported Networks
record drawer/page. Addresses loads only on its section; bounded search, status
filtering, numeric IP ordering, personal columns and paging operate within the
selected parent. Child selection is URL-addressable and stays in the existing
record surface. Create/edit retains failed values and uses the shared dirty guard.
Updates omit assignment/interface/parent keys, preserving those existing links.
No version change, data migration, production publication or fixture writes to user
data. The API adds explicit query parameters while preserving legacy payload and
ordering defaults. OpenAPI/types and the route inventory are updated.

Type checking and focused lint pass. Initial new browser assertions used labels
that differed from the localized UI; corrected those labels after reproducing the
failures. A preference refresh test and live edit refresh test initially navigated
before the asynchronous save completed; both now require visible completion before
refresh, preserving their persistence assertions. Two baseline Firefox cases timed
out during concurrent heavy suites; final browser verification runs with one worker.
The initial general check exited 137 during frontend lint while other suites were
running; it must pass in a lower-contention rerun before this checkpoint is closed.
Mobile screenshots were inspected: the focused address editor fits the parent
full-screen drawer without horizontal overflow. Full final evidence follows below.

The strengthened live save assertion exposed a real backend defect rather than
only test timing: IP-address PATCH returned 500. A separate PostgreSQL regression
reproduced `FOR UPDATE cannot be applied to the nullable side of an outer join`.
`update_ip_address` now explicitly locks the address and entity, leaving the existing
namespace lock in place. All nine endpoint tests pass, including a new status/DNS
update that asserts parent and hardware assignment preservation. No schema change.

The first coverage run fell below the existing function threshold. Added four
behavioral component tests for bounded parent reads/search, page preferences, selected
facts, assignment-preserving saves, failed creation, navigation protection and
unavailable records. They also reproduced a double confirmation on cancelling a new
address: the local guard action immediately initiated a second router-blocked move.
Child return/new-form cancellation now delegates directly to the router guard;
local cancellation of an existing edit still uses the explicit guard. The component
suite passes without reducing coverage thresholds or weakening assertions.

Final live evidence: the isolated browser-to-Django-to-PostgreSQL journey passes
with address create, successful status update, and refresh of the saved DNS/status.
The existing independent database-fixture assertions also pass. All 54 layout
browser checks passed before the cancellation follow-up; all 27 affected child
address checks pass again after that fix across Chromium, Firefox and WebKit.
New component tests pass (4), and the complete endpoint regression set passes (9).
The final broader network gate and general check are being completed below.

Final `make check` passes: backend lint/type/migration checks, schema synchronization,
frontend lint/types, all 485 component tests in 103 files, coverage enforcement
(functions 70.44%, existing 70% minimum unchanged), production build and bundle
budgets. The application changes require no migration. Wiki manifest and whitespace
checks pass. The local rebuild is underway with existing volumes retained.

The authorized local `make up` completed without removing volumes. Readiness reports
status ok, database/renderer ready and version 0.8.46; `/networks` returns 200. Test
locally through Networks → network name → Addresses. No production push, publication,
version change or replacement of existing user/demo data occurred.

Final `make test-network-validation` exited successfully after the fixes: network
inventory/addressing/endpoints/services/circuits, reconciliation/transfer,
relationships, permission/IDOR, runtime RLS, migration stabilization and network
stabilization all pass, followed by all 485 frontend tests and coverage. The existing
suite skip remains unchanged. The earlier failed gate ran before the new component
harness corrections; this final complete rerun supersedes it.

Verified: this bounded Addresses implementation, all gates above, the live workflow,
and healthy local 0.8.46 runtime. No blocker remains for this checkpoint. Inferred:
the shared pattern is suitable for further network child surfaces; those still need
their own implementation and evidence. Phase 3, technician acceptance, production
publication and the broader pre-1.0 obligations remain open. Durable architecture,
query/navigation contracts, tests and route-state inventory are tracked here; the
Wiki Roadmap follow-up remains local and unpublished.

### 2026-09-13 — Parent Wireless records (Phase 3 #80)

Bounded slice: parent-associated wireless SSID collections and selected record
editing within the existing network drawer/full page. Added server parent/search/
status/order/summary query support, personal network-wireless preferences, generated
API contracts, mobile sections and URL state. Extracted NetworkChildCollection from
Addresses to keep both child collections consistent. No version or schema change.

Reproduced an existing wireless PATCH failure in PostgreSQL before fixing it:
FOR UPDATE rejected nullable site/VLAN/subnet joins. Restricted locks to the wireless
record and its entity, preserving the existing workspace lock. The focused API suite
passes (7 tests), including status edits retaining site/VLAN/subnet IDs, 31 records,
bounded counts, off-page search, deterministic ordering, summary/legacy compatibility,
invalid queries, cross-parent denial and preference save/reset.

Focused type/lint and 9 child component tests pass. Initial verification caught an
unused extraction import, React's prohibition on passing a ref-mutating callback to
a directly invoked render function, and a Playwright-only matcher in a component
test. Used a static record component and the supported component focus matcher;
assertions remain intact. Browser, live and full gates are in progress below.

All 78 browser checks pass across Chromium, Firefox and WebKit, including the
existing Networks/Addresses scenarios after the shared component extraction. New
Wireless coverage exercises six widths, long descriptions, off-page SSID search,
URL selection/full-page/Back/refresh, focus return, columns, removable status filters,
failed PATCH/dirty dismissal, touch, short screens and 200% zoom. Mobile screenshots
were inspected: readable facts within one drawer body and no horizontal overflow.

`make check` passes: backend lint/types, migration drift, schema synchronization,
frontend lint/types, all 490 tests in 104 files, coverage enforcement, production
build and bundle budgets. No thresholds were loosened. The live browser-to-Django-
to-PostgreSQL journey passes, including wireless creation, a successful status edit,
and refresh retaining status/security mode. Existing independent database-fixture
assertions also pass. The local rebuild is underway with existing volumes preserved;
the full network gate remains in its migration/recovery stage.

The authorized local `make up` completed with volumes retained. Readiness reports
status ok, database/renderer ready and version 0.8.46; `/networks` returns 200. Local
test path: Networks → network name → Wireless. No production push/publication,
version change, or replacement of existing user/demo data occurred. Wiki manifest
and whitespace checks pass. Full network validation completion is recorded below.

Final `make test-network-validation` exited successfully: network inventory,
addressing, endpoints, services, circuits, reconciliation/transfer, relationships,
permission/IDOR, runtime RLS, migration stabilization and network stabilization,
followed by all 490 frontend tests and coverage. The existing suite skip remains
unchanged. This completes the bounded parent Wireless checkpoint.

Verified: the implementation, shared Addresses regression coverage, full checks,
isolated live workflow and healthy local 0.8.46 runtime. No blocker remains for this
checkpoint. Inferred: the shared child-list pattern is suitable for additional
network records; each still requires its own implementation and evidence. Unassigned
wireless browsing, association management, other network surfaces, technician
acceptance, release gates and broader pre-1.0 obligations remain open. Tracked
implementation notes and tests are durable; the Wiki update remains local/unpublished.

### 2026-09-13 — Workspace Wireless register (Phase 3 #80)

Bounded slice: discover and edit assigned/unassigned SSIDs across the current
workspace from Networks → Wireless. Shared complete-record drawer, Overview/History,
optional page, URL list context, association filter and network column. Server query
and personal wireless-register preferences are additive; OpenAPI/types updated.
No schema migration or version change. Association reassignment remains follow-up.

Focused API suite passes (8 tests); focused Networks/Addresses/Wireless components
pass (18 tests). Initial verification reproduced unsafe-any lint in browser state
and matcher typing, then corrected explicit unknown boundaries. A fixture edit
accidentally referenced standalone in the Addresses helper, reproducing a type/build
failure and browser failure; restored that helper's fixed parent assertion. Component
Escape simulation did not dispatch the native dialog cancel event in JSDOM; use the
native cancel event there, with actual keyboard Escape covered in browser tests.
The new History browser assertion initially omitted “network” from the catalog label;
updated the assertion to the existing copy after observing the rendered result.
No production behavior or verification threshold was weakened to resolve these.

Full checks, all maintained browser engines, network/migration validation, live
Django/PostgreSQL rehearsal and local rebuild results are recorded below when done.

The real browser-to-Django-to-PostgreSQL rehearsal passes, including creation of an
unassigned SSID from the register, status update and persisted null parent/status
after refresh. Existing independent database-fixture assertions also pass. Local
make up completed with retained volumes; readiness reports database/renderer ready
and version 0.8.46. No production publication or replacement of user/demo data.

The full component run exposed a pre-existing Assets test timing failure: it fired a
native cancel synchronously after observing saved lifecycle text while the guard's
React update was still settling. Reproduced the same failure against archived HEAD
source (20 pass/1 fail) and current source. Wrapped the successful user save in async
act to settle React updates before the separate cancel event, retaining the original
no-dialog assertion. All 21 Assets tests then pass. No application guard behavior was
changed. The complete make check gate is rerunning with this harness correction.

All 102 network browser checks pass across Chromium, Firefox and WebKit. Coverage
includes prior Networks/Addresses/parent Wireless behavior, six widths, unassigned
SSID discovery, retained query state, History/refresh, full-page/Back/Forward, focus
return, inaccessible records, association filters, failed saves and dirty dismissal,
touch/short heights and 200% CSS zoom. Synthetic mobile screenshots were visually
inspected. No page or drawer horizontal overflow or accessibility violations in the
checked record states. Broader technician/release acceptance remains open.

Final make check passes: backend lint/types, schema/migration drift checks, frontend
lint/types, all 495 tests in 104 files, coverage enforcement, production build and
bundle budgets. The long network gate has completed its main API/IDOR/RLS/migration
suite and moved to network stabilization; final completion is recorded below.

Final make test-network-validation exited successfully: main network API, service,
transfer/reconciliation, permission/IDOR, runtime RLS and migration stabilization
suite; network stabilization; then all 495 frontend tests and coverage. The existing
suite skip remains unchanged. This completes the bounded workspace Wireless slice.

Verified: implementation/API contracts, focused tests, all maintained browser
engines, full checks, isolated live workflow, and healthy local 0.8.46 runtime.
No blocker remains for this checkpoint. Inferred: the shared standalone/parent
collection pattern can support later network records; each needs its own evidence.
Wireless association editing, remaining network surfaces, technician acceptance,
release gates and broader pre-1.0 obligations remain open. Wiki changes remain local
and unpublished. No production push, release, version bump or data replacement.

### 2026-09-13 — Wireless parent-network assignment (Phase 3 #80)

Bounded slice: attach, move or remove a wireless record's parent network in a focused
section in either parent Wireless or the workspace register. Searches existing bounded
network summaries, PATCHes only subnet_id, preserves site/VLAN/facts, and uses the
shared dirty guard. Moving out of a parent list returns to that list; workspace
filtered-list departure is explained within the open drawer. Corrected shared child
record notices that previously said “asset.” No API/migration/version change.

Initial focused verification reproduced a component test passing the Playwright-only
exact option to Testing Library; removed that unsupported option while retaining the
exact string name match. Type/lint and 14 focused tests then passed. Added lookup
failure/retry/empty and read-only assertions before the full gate. Full browser, live,
network validation and make check results follow below.

Browser verification reproduced an exact getByLabel lookup failure on the native
parent select: the wrapped label includes option text, while its accessible combobox
name is correctly “Matching parent networks.” Switched browser/live queries to that
exact role and accessible name, retaining the selected ID/value assertions. Stopped
the obsolete live/browser run and reran with the corrected harness; UI copy and
behavior were unchanged by this correction.

The full initial make check passed (500 tests/105 files and production budgets).
Browser runs then reproduced a real post-save dismissal race at 1024/1280px: the
ordinary-save callback queued the same record URL for a later animation frame,
which could reopen a drawer just dismissed by Escape. NetworkChildCollection now
queues selection navigation only for creation or a move out of the parent collection.
Kept the immediate post-save Escape assertion unchanged and reran the full checks
and browser suite; creation and parent-departure navigation remain covered.

The live assignment workflow passed: create an unassigned SSID, attach it to the
management network, refresh and verify its parent/status, then remove the parent
and refresh again. Existing database fixture assertions pass. A final live run includes
the later post-save navigation-race correction. Synthetic mobile assignment screenshots
were inspected: bounded native results, selected parent, errors and actions remain
in the single drawer body; no nested drawer or separate scrolling panel is introduced.

Final make check passes with the navigation-race fix: all 500 component tests in
105 files, coverage enforcement, backend/frontend lint/types, schema/migration drift
checks, production build and bundle budgets. Chromium and Firefox assignment checks
pass at all six widths, including immediate post-save dismissal without reopening.
Remaining browser/live/network gate results and local runtime readiness follow below.

The final live browser-to-Django-to-PostgreSQL journey passes with the navigation
fix included, including persisted attach/remove and retained status after refresh.
Independent database fixture assertions pass. Authorized local make up completed with
volumes preserved; readiness reports database/renderer ready at version 0.8.46 and
the Wireless route returns 200. Test locally: Networks → Wireless → SSID → Change
parent network (also available in a parent network's Wireless section). No production
push, publication, version change or replacement of user/demo data occurred.

All 126 network browser checks pass across Chromium, Firefox and WebKit, including
the six widths, attach/remove, parent-list departure, active-filter notices, bounded
off-page parent lookup, read/edit navigation, dirty/failed saves, touch/short screens,
200% CSS zoom and accessibility. The immediate post-save Escape regression passes
without changing its assertion. Mobile screenshots from Chromium/WebKit were inspected.
The final broad network gate remains in migration/recovery validation below.

Final make test-network-validation exited successfully: network inventory/addressing/
endpoints/services/circuits, reconciliation/transfer, relationships, permission/IDOR,
runtime RLS and migration stabilization; network stabilization; then all 500 frontend
tests and coverage. Existing suite skip remains unchanged. This completes the bounded
wireless parent-network assignment checkpoint.

Verified: attach/move/remove, partial-update preservation and foreign-parent rejection;
shared drawer/list navigation including the reproduced post-save race fix; full checks,
126 maintained-browser checks, isolated live workflow and healthy local 0.8.46 runtime.
No blocker remains for this checkpoint. Inferred: bounded parent lookup can inform
later association editors, but each still needs its own rules and validation. Site/VLAN
editing, other network records, technician/release acceptance and existing pre-1.0
security/recovery/recurring obligations remain open. Wiki changes remain local/unpublished.

### 2026-09-13 — VLAN and VRF registers (Phase 3 #80)

Bounded slice: Networks VLAN/VRF collection views, complete record drawers/pages,
Overview/History, personal columns, bounded search/sorting/paging and guarded editing.
Existing APIs gain additive summary/query parameters; schema/types updated. Shared
collection supports records without a parent subnet and omits meaningless status
filters. Related subnet navigation and remaining network work stay open. No migration,
permission-model change or version bump.

Focused type/lint and 21 components pass, including prior Address/Wireless behavior.
The first production/live build reproduced a browser fixture type error: a VLAN/VRF
union was accessed without narrowing its kind-specific field. Used property narrowing,
retaining identical record/search assertions. Full check/live runs restarted with that
correction. Browser coverage also includes added column/reset and failed/empty-list
checks. Final verification and local readiness results follow below.

Final make check passes: 506 component tests in 106 files, coverage enforcement,
backend/frontend lint/types, migration/schema drift checks, production build and bundle
budgets. The live browser-to-Django-to-PostgreSQL journey passes: create VLAN and VRF,
edit their descriptions and refresh persisted records. Independent database fixture
assertions pass. All six additional column/reset/retry/empty browser checks pass.
The authorized local rebuild is underway with existing volumes/data preserved.

Local rebuild completed with retained volumes. Docker readiness reports database and
diagram renderer ready, version 0.8.46. VLAN Chromium and VRF WebKit short-screen
screenshots were visually inspected; retained form values and section navigation are
readable in the single scrolling drawer. Wiki contract passes (37 pages, 25 topics).

The first broad browser run passed 173/174 cases. The existing WebKit wireless parent
reassignment test at 1280px intermittently opened a dirty confirmation after a saved
edit when Escape was pressed. Ten unchanged focused repeats passed. No test or guard
was weakened; the cause remains unconfirmed. A full WebKit network/addressing rerun
is in progress. This observation remains a navigation acceptance follow-up rather than
a claim that the intermittent failure was fixed.

WebKit confirmation completed: all 60 network/addressing cases pass, including the
original wireless scenario. Across the executed runs all 180 distinct network and
addressing browser cases passed at least once (54 new addressing cases); the original
173/174 result remains recorded above. Ten additional unchanged focused repeats pass.
No browser test or application code was changed to retire that intermittent result.

Final `make test-network-validation` exits 0: network APIs, permission/IDOR/RLS and
migration stabilization, high-volume network stabilization, and the full 506-test
frontend coverage suite pass. Verified: local Docker readiness and both new routes,
API/schema compatibility, full check, live persistence and browser scenarios.
Unconfirmed: intermittent existing WebKit post-save guard cause. Still open: related
subnet navigation, remaining network surfaces and technician/release acceptance.
This bounded VLAN/VRF register checkpoint is complete; Phase 3 remains open.

## Associated VLAN/VRF networks — Phase 3 #80, pre-1.0 0.8.46

Adds lazy Networks sections to VLAN/VRF drawers and full pages, compact associated
subnet lists, whole-association search, 25/50/100 paging, and canonical full network
links with browser Back/refresh context. Exact association filters validate authorized
parent entities, preserving existing numeric VLAN filtering and all domain rules.
API/schema/types, route inventory and implementation notes updated; no migration.

Initial component run reproduced an incorrect test import path; corrected it without
changing assertions. Nine focused component tests pass. An initial backend run used
a stale image and selected no tests (exit 5); rebuilt image and restarted API checks.
The first full check raced generated-type refresh and rejected stale types; types are
now regenerated from the rebuilt schema and the full check is rerunning. Initial
Chromium six-width related navigation checks pass; 390px screenshot visually inspected.
Final gate, live and browser results follow below.

The rebuilt API checks pass for both parent kinds, covering exact association (rather
than same VLAN number), 31 records, off-page search, stable ordering, invalid IDs and
foreign-workspace denial. The 90-case addressing browser suite passes across Chromium,
Firefox and WebKit. A 230-character network name also passed the 390px overflow and
round-trip check without application changes; long-name fixtures are retained.

Full lint reproduced a FormData value stringification warning; narrowed the value to
a string, preserving the existing search behavior. Focused lint/types pass and the
full check restarted. Live navigation through associated records passed, but Chromium
crashed later in the existing recurring-invoice workflow (Target crashed, line 81).
The complete live rehearsal is rerunning unchanged; no assertion was weakened.

Final make check passes (509 component tests, 107 files; lint/types, migration/schema
drift, coverage, production build and unchanged bundle budgets). The complete live
rehearsal passes on unchanged retry, including VLAN/VRF associated subnet creation,
opening full network records, refresh and Back to the parent section. Independent
PostgreSQL fixture assertions pass. The first browser crash remains recorded above
as an unconfirmed browser crash with no inferred application fix. Local rebuild and
the expanded long-name/short-height/200%-zoom browser cases are finishing.

Expanded related-navigation run passes all 36 cases across three engines: six widths
per parent kind, 230-character identifiers, page/search/refresh/Back, and short-height
200% zoom. Chromium VLAN and WebKit VRF mobile screenshots were visually inspected.
Local make up completed without removing volumes; readiness reports PostgreSQL and
diagram renderer ready at 0.8.46. The broad network gate remains running its migration
checks; final disposition follows below.

Final `make test-network-validation` exits 0: network/API, IDOR/permission/RLS,
migration stabilization, high-volume network stabilization and all 509 frontend
components with coverage pass. `make check`, the 90-case browser suite, 36 expanded
related-navigation cases and the complete live PostgreSQL journey pass. Wiki contract
passes (37 pages, 25 contextual topics); final diff has no whitespace errors.

Verified: this bounded associated-network navigation checkpoint and local 0.8.46
readiness with retained data. Unconfirmed: the initial Chromium process crash later
in the live invoice workflow; the unchanged complete rerun passes. Existing broader
wireless intermittent-navigation observation remains tracked in its earlier checkpoint.
Still open: wireless site/VLAN editing, remaining network record surfaces, technician
walkthroughs and release acceptance. Phase 3 and the wider pre-1.0 plan remain open.

## Wireless site/VLAN assignment — Phase 3 #80, 0.8.46

Adds focused assignment/removal in both wireless surfaces, one active editor, bounded
name/code/VLAN-number lookup, retained failed/denied selections and partial updates.
New assignment-choice APIs preserve existing legacy consumers and exact-workspace
network permission boundaries. Schema/types, route inventory and handoff notes updated.
No domain model, migration, dependency or version change.

Initial checks reproduced long-line lint and an overly broad translation-key type;
formatted the new code and narrowed the key union. Component scenarios passed before
and after the typing correction. The API test reproduced page-two emptiness because
the new endpoint inherited a 100-row default; explicitly set its default to 25 without
weakening the six-record second-page assertion. Both API scenarios now pass.

New browser assignment/save/remove/Escape scenarios reproduced stale dirty confirmation
after visible editor removal (Chromium site/VLAN, including 390/1440px). Stopped the
broad failing run and changed shared guard registration/cleanup to a layout effect.
Nineteen focused navigation/wireless components pass; unchanged browser repetitions
and broad regression checks are in progress. Final results follow below.

Both API checks pass with the corrected default. Thirty unchanged site/VLAN
assignment-save-remove-Escape repetitions pass (five repeats per kind across three
engines) after synchronous guard cleanup. Initial make check passes; it is rerunning
against the final guard change. The live PostgreSQL rehearsal and full network gate
are running. Broader browser navigation coverage follows the live run.

Final make check passes: 513 components in 108 files, frontend/backend lint and types,
schema/migration drift, coverage, production build and unchanged bundle budgets. The
complete live browser-to-Django-to-PostgreSQL journey passes with both assignments,
removal and refresh while retaining wireless status; independent fixture assertions
pass. Local rebuild and broad network/asset/contract browser regressions are underway.
The full network gate has reached its migration checks without failures.

Authorized local rebuild completed with existing volumes/data retained. Docker
readiness reports database and renderer ready at 0.8.46. The mobile site-assignment
failure screenshot was visually inspected: selection, error and controls remain
readable within the single drawer scroll body. Broader browser and network gates
are still finishing; final results follow below.

All 225 network/asset-edit/contract browser scenarios pass across Chromium, Firefox
and WebKit, including the old parent-assignment regression and both new association
flows. Thirty additional post-save dismissal repeats passed earlier. No browser
assertion was weakened to resolve the stale guard; cleanup timing changed.

The broad network run completed API, IDOR/RLS and migration cases but failed its
final route-inventory completeness assertion: the two new lookup routes were missing
from permission_inventory.py. Added their networks.view contracts and the organization
URL argument to the matrix fixture. No runtime policy changed. Rechecking the complete
permission module on the rebuilt image; unaffected passed network/migration evidence
is retained. Remaining high-volume and frontend gate stages will follow that rerun.

The complete permission/IDOR module now exits 0 on the rebuilt image, including both
new route contracts and anonymous/non-member probes. Targeted inventory lint passes.
The original broad run's other network/API/RLS/migration cases passed and are unchanged
by this metadata-only correction. Completing the remaining recipe stages with
`make -o test-networks test-network-validation` avoids repeating those already-passed
expensive migration cases; this is segmented gate evidence, not a claim that the
initial unmodified command succeeded. Final stage results follow below.

Final remaining gate stages exit 0: high-volume network stabilization and all 513
frontend components with coverage pass. Network validation is complete in the segments
described above: original passing network/API/RLS/migration cases, full permission
matrix rerun after its metadata correction, then the unchanged remaining recipe.
Backend type checks also pass on all 192 source files after the inventory update.

Verified: final make check, 225 browser cases, 30 additional dismissal repeats, live
PostgreSQL persistence, segmented network gate and local 0.8.46 readiness. Site
Chromium and VLAN WebKit mobile screenshots were visually inspected. Wiki contract
passes (37 pages, 25 contextual topics); no whitespace errors. No known regression
remains from this slice. The earlier intermittent post-save guard symptom is now
reproduced, corrected and covered by the unchanged browser assertions.

This bounded checkpoint is complete. Devices, racks, interfaces, DNS, circuits,
remaining network surfaces, technician walkthroughs and release acceptance stay open.
No production publication, domain-data migration or version bump was performed.

## Devices/racks collection prerequisite — 2026-09-13

Bounded Phase 3 (#80) API checkpoint, not a visible-surface migration. Added
strict full-collection search/status/site filters, role/rack device filters,
curated bidirectional ordering with entity-ID ties, SQL rack occupant counts,
and independent bounded browser collection/detail clients. Existing API routes,
response shapes, page default 50, legacy frontend helpers, writes and policies
remain compatible. Responsive clients explicitly request page size 25. No new
route permission inventory entry or database migration is necessary.

Verified so far: two focused Docker/Django/PostgreSQL collection tests pass with
31 real synthetic racks and 31 asset-backed devices, independent organizations,
off-page identifiers, paging, count/order/filter assertions and asset redaction.
Browser-client contract tests pass (3), including exact escaped URLs and abort
signals; frontend TypeScript passes. Backend type checks pass on 192 source files.
Two initial type-check failures identified Django's model narrowing in a shared
query helper; explicit QuerySet typing/casts corrected them without changing
query behavior or weakening tests. OpenAPI/generated types include only the
new supported query parameters. Wiki contract passes (37 pages/25 topics).

Full make check and network-validation outcomes follow below. No browser visual
acceptance is claimed: this checkpoint changes APIs/client methods only, and the
rack/device drawers, preferences, bounded assignment editors, interfaces and
technician walkthroughs remain open. See inventory-collections.md for the next
implementation contract.

Final verification: `make check` exits 0, including API schema/type agreement,
backend lint/types/migration drift, all 514 frontend tests in 108 files, coverage,
production build and bundle budgets. `make test-network-validation` exits 0 as
a complete invocation: network APIs, relationships, permission/IDOR, runtime RLS,
migration stabilization, high-volume network checks, then all 514 frontend tests.
The broad API invocation began before the final typing-only casts were added;
its runtime query behavior is identical, and the final rebuilt source passes
make check. Focused API and browser-client checks also pass as recorded above.
Logs: `/tmp/inventory-collections-focused.log`, `inventory-collections-client.log`,
`inventory-collections-check-passed.log`, `inventory-collections-network-gate.log`
and `inventory-collections-up.log` (all under `/tmp`).

Local `make up` exits 0 without removing data or volumes; readiness confirms
healthy database/renderer and version 0.8.46. Wiki and whitespace checks pass.
Verified: API prerequisite and local runtime. Not claimed: visible rack/device
migration, browser layout acceptance, technician validation or production release.
No known new runtime regression remains. The next slice is the rack register,
complete drawer and lazy Devices section described in inventory-collections.md.

## Rack register and complete drawer — 2026-09-13

Bounded Phase 3 (#80) visible checkpoint: Racks view, shared register/preferences,
full Overview/Devices/History drawer and optional direct full-page route. Added
required-site/optional-location editing with bounded name/code choices and explicit
location clearing on site change. Installed devices load only in their section;
selected-device facts reuse the current drawer and revalidate rack membership.
Existing mutation authorization, occupied-unit and placement constraints are retained.
No domain-data migration, new route, dependency or version change. Device editing,
standalone device registers/interfaces and other remaining surfaces stay open.

Initial validation: 22 focused component tests pass (rack/addressing/wireless),
including dirty failed drafts and unchanged assignments; one new test initially
matched both the Site results region and its select and was corrected to target
the combobox explicitly. Type checking identified a missing Site message and lint
identified untyped Playwright fixture payloads; both were corrected without changing
assertions or weakening gates. Backend location/personal-preference API test passes
with 31 synthetic locations, off-page code search, invalid/sibling parent rejection,
preference save/read/reset. Initial Chromium browser pass: 9 cases passed, including
all six widths, axe checks, record/history refresh, Back/Forward, touch, failed-save
guards, 200% zoom and outside-click dismissal. Additional child focus and preference
coverage is included in the final maintained-browser run.

Full check, network gate, live PostgreSQL journey and final browser outcomes follow.

Verified on September 14: final make check exits 0 (519 tests across 109 frontend
files, lint/types/schema agreement/migration drift, production build and bundle
budgets). The live isolated browser→Django→PostgreSQL journey exits 0, including
new rack create/edit/refresh and independent site/location/status/audit assertions.
Local make up succeeds with existing volumes/data retained; readiness reports
database/renderer healthy and version 0.8.46. Initial Chromium mobile screenshot
was visually inspected with long values and reachable save/cancel controls.
Final three-browser and broad network-gate outcomes follow below.

All 120 maintained-browser rack/addressing cases passed before the final mobile
density refinement. The review then limited mobile rack rows to name, site, status
and device count, retaining location/capacity in the drawer. This change is scoped
to the rack register; make check and all 30 rack browser cases are rerunning with
explicit mobile visibility assertions. The previously passed 90 addressing cases
are unaffected. No backend/live workflow code changed after its successful run.

Final mobile verification passes: make check exits 0 again, including all 519
frontend tests, production build and bundle limits. All 30 rack cases pass in
Chromium/Firefox/WebKit with the final mobile column priorities. Together with
the unaffected 90 addressing cases, all 120 scenarios pass; the additional full
rack rerun is recorded separately. Chromium and WebKit mobile screenshots were
visually inspected. Logs are under `/tmp/rack-layout-`: components-final, api,
check-mobile, browser-final, browser-mobile, live, network-gate and up-final.

Final closeout: full `make test-network-validation` exits 0, including network/API,
permission/IDOR, runtime RLS, migration stabilization, high-volume checks and all
519 frontend tests. Final local `make up` exits 0 after the mobile refinement;
readiness confirms healthy database/renderer at 0.8.46. Wiki (37 pages/25 topics)
and whitespace checks pass. Existing user/demo data and volumes were retained.

Verified: complete rack register/drawer, bounded assignment API/preferences,
maintained-browser scenarios, live save persistence and local rebuild. No known
new regression remains. Not claimed: standalone device editing, interface/DNS/
circuit migration, technician sign-off or full Phase 3/pre-1.0 release acceptance.
No production push/publication or version change. This bounded checkpoint closes
with the next device/interface work described in rack-register.md.

## Devices register and core editing — September 14, 2026

Phase 3 (#80), required pre-1.0 under #60/#75. The implemented boundary is
documented in device-register.md: Devices register, full Overview/Placement/History
drawer, bounded hardware selection for creation, independent ordinary/placement
edits, and rack-child navigation. Mobile rows prioritize name/role/status/rack.
Interfaces, device relationships, hardware rebinding, DNS/circuits and final
technician/release acceptance remain open. Version remains 0.8.46.

The additive hardware-choice API and device creation capability honor existing
asset permissions and exact workspace scope. Hidden asset bindings are neither
returned nor resent by ordinary editing. Preferences reuse existing ownership/RLS;
there is no migration, new permission grant, dependency or domain-data conversion.
OpenAPI and generated types are aligned. Failed mutations retain drafts and are
not automatically retried.

Verified: 10 focused component cases, two new Django/PostgreSQL API cases, and
10 initial Chromium browser cases pass. The API cases exercise 31 hardware choices,
off-page search, workspace isolation, claimed-asset removal, asset-denied editing
and preference persistence/reset. Main `make check` exits 0: 524 frontend tests
across 110 files, lint/types, schema agreement, migration drift, production build
and bundle budgets. No gate or assertion was weakened.

The isolated live browser→Django→PostgreSQL journey exits 0. It creates a device,
changes status, places it in a rack, reloads it and follows rack-to-device navigation
with Back restoration. Independent database assertions verify the hardware binding,
derived site/location, occupied units and exactly two update audit events. Chromium
mobile placement screenshot was visually inspected with reachable save/cancel.

Final maintained-browser, network-gate and local rebuild outcomes follow below.

Local `make up` exits 0; the rebuilt application readiness endpoint confirms
database/renderer healthy at 0.8.46, with existing data and volumes retained.
The repository Wiki manifest/help contract passes (37 pages/25 contextual topics).
The additional full-checkout check against `../TekDocs.wiki` fails because that
pre-existing checkout lacks 31 manifest pages. This is a documentation checkout
limitation, not an application test failure; the scoped Roadmap update is saved
there without publishing or committing its unrelated changes. Full Wiki checkout
validation remains unverified until the missing pages are restored/synchronized.

Final maintained-browser run exits 0: all 60 device/rack cases pass across
Chromium, Firefox and WebKit, including all six widths, touch/short heights,
200% zoom, accessibility scans, saved columns, navigation and dirty/failed saves.
Chromium and WebKit mobile placement screenshots were visually inspected.
Logs are under `/tmp/device-layout-`: components, api, check, live, browser-final,
network-gate and up. The network gate outcome follows at final closeout.

Final closeout: full `make test-network-validation` exits 0, including network/API,
permission/IDOR, runtime RLS, migration reversal/reapplication, high-volume
stabilization and all 524 frontend tests. No known new application regression
remains. Main checks, all 60 maintained-browser cases, live database assertions
and local rebuild are verified. Whitespace and route-inventory JSON checks pass.
The separate incomplete Wiki checkout remains the documentation limitation above;
no Wiki publication, production deployment or version change was performed.
This closes the bounded Devices/core-editing checkpoint, not Phase 3 or pre-1.0
acceptance. The next interface/API work is documented in device-register.md.

## Device interfaces — September 14, 2026

Phase 3 (#80), required pre-1.0 under #60/#75. The bounded scope is the Interfaces
section within Devices, parent-scoped collection APIs/preferences and focused
creation/ordinary editing. See device-interfaces.md for URL contracts, API
compatibility, accepted boundaries and IP/MAC/reassignment follow-ups. There is
no new model, migration, permission grant, dependency or version change.

Initial verification: 14 component cases across interfaces/devices/addresses pass,
including unchanged parent bindings, rejected mismatched children, permission
failures, draft protection and focus restoration. The new Django/PostgreSQL API
case passes with 31 parent interfaces, another device, sibling-workspace denial,
search/filter/sorting, summary versus legacy responses and preferences/reset.
Schema generation has no errors (the two existing operation-ID warnings remain);
generated client types are updated. Ten initial Chromium interface cases pass
across all six widths and the mobile screenshot was visually inspected.

The first new-creation guard assertion failed and was reproduced independently in
`/tmp/interface-layout-guard-repro.log`. The editor retained its values while the
lazy confirmation dialog had not rendered yet. The test now awaits the same Keep
editing control and retains the draft assertion; the final browser scenario also
checks creation-return protection. No application guard change or weakened
assertion. Initial type checking also rejected a Playwright-only selector option
in the component test, and lint caught one unused fixture binding; both were
corrected before final checks.

The repository Wiki manifest/help contract passes (37 pages/25 topics); the scoped
local Wiki Roadmap update remains unpublished. Its previously recorded missing-page
checkout limitation is unchanged. Main, live, final maintained-browser and full
network-gate outcomes follow below. Version remains 0.8.46 throughout.

Main `make check` exits 0: 529 frontend tests across 111 files, lint/type checks,
OpenAPI/generated agreement, migration drift, production build and bundle budgets.
The isolated live browser→Django→PostgreSQL journey exits 0, including interface
creation, partial status editing, refresh and child return focus. Independent
assertions confirm device/organization, kind/status, description and exactly one
interface update event. Final browser, local rebuild and network-gate results follow.

Local `make up` exits 0 and readiness reports healthy database/renderer at 0.8.46.
Existing user/demo data and volumes are retained. Networks → Devices → Interfaces
is available in the rebuilt local application; no production publication occurred.

Final maintained-browser run exits 0: all 87 interface/device/address cases pass
across Chromium, Firefox and WebKit. This includes the added new-creation return
guard, six widths, one-drawer behavior, direct/full-page navigation, saved columns,
read-only/foreign-parent handling, touch/short height, 200% zoom and address
regressions through the generalized parent handling. Chromium and WebKit mobile
screenshots were visually inspected. No application code changed after the successful
main/live runs. Logs are under `/tmp/interface-layout-`: components-final, api,
schema, check, live, browser-final, network-gate and up. Final network gate follows.

Final closeout: full `make test-network-validation` exits 0, including network/API,
permission/IDOR, runtime RLS, migration reversal/reapplication, high-volume
stabilization and all 529 frontend tests. Main checks, all 87 maintained-browser
cases, live database assertions and the local rebuild are verified. Whitespace and
route-inventory JSON checks pass. No known new application regression remains.
The pre-existing incomplete separate Wiki checkout remains the documented limitation;
its Roadmap update is saved locally and unpublished. No production deployment or
version change. This closes the interface collection/core-editing checkpoint, not
IP/MAC assignment, Phase 3, technician sign-off or pre-1.0 release acceptance.

## Interface IP/MAC records and assignment — September 14, 2026

Phase 3 (#80), required pre-1.0 under #60/#75. Implemented scope: bounded endpoint
collections inside interfaces, ordinary edits, assignment of existing unbound
records and confirmed removal. See interface-endpoints.md for route/query behavior,
expected-binding PATCH semantics, compatibility and remaining creation/transfer work.
No model, migration, permission grant, dependency or version change.

Initial verification: 16 focused interface/endpoint/address component cases pass;
11 Chromium cases pass across all six widths, including direct/full-page URLs,
foreign parents, read-only access, off-page assignment search, conflicts, confirmed
removal, touch/short heights and 200% zoom. The mobile assignment screenshot was
visually inspected. Final browser run adds explicit assignment-heading focus.

Reproduced server failures and fixes:
- Initial PostgreSQL assignment test reproduced MAC update's nullable outer-join
  row-lock error (`endpoint-layout-api-initial.log`). MAC updates now lock only the
  record and its entity.
- Concurrent MAC claims then reproduced a stale joined interface after waiting on
  another writer (`endpoint-layout-api-final.log`). The optional relation is read
  after acquiring the lock; the two-claim test now yields one winner/one conflict.
- A deterministic waiting-IP test reproduced an existing record reported missing
  after a concurrent subnet change (`endpoint-layout-namespace-repro.log`). IP
  updates likewise read the namespace after acquiring the row lock. The regression
  explicitly observes the waiting database lock before releasing the first writer.

The four assignment/claim API tests passed before the final IP namespace regression
was added. Main checking identified missing type annotations on the shared filter
helper and an optional relation; both were corrected. Component fixture typing and
one long test SQL string were corrected without weakening assertions or gates.
No guard or approval behavior was relaxed.

The first live browser→Django→PostgreSQL journey passes, independently verifying IP
binding, ordinary edits, retained MAC removal and its three update audit events.
The final server locking code is being verified with all five focused API cases,
the full network gate and another live run. The repository Wiki manifest/help check
passes (37 pages/25 topics); its separate checkout retains the previously documented
missing-page limitation. The scoped Roadmap update is saved locally and unpublished.
Version remains 0.8.46. Final outcomes follow below.

All five focused PostgreSQL cases now pass, including the waiting-subnet regression
and concurrent claims for both IP and MAC. The main check passes with 536 frontend
tests across 112 files, lint/types, schema/generated agreement, migration drift,
production build and bundle budgets. The live journey passes again with the final
server locking code and independent retained-record/audit assertions. Only the
assignment-heading focus improvement followed that live run; final browser and
main checks include it. Full network gate and local rebuild results follow.

The local `make up` succeeds with existing data/volumes retained. Readiness confirms
healthy database/renderer and version 0.8.46. No production push/publication or
version bump. The final browser run covers endpoints, interfaces, addresses and
wireless assignment regressions through the shared collection; results follow.

The final `make check` (including assignment-heading focus) exits 0: all 536 frontend
tests, lint/types/schema checks, migration drift, production build and bundle limits
pass. The final local rebuild already includes this code and remains at 0.8.46.
No domain data was migrated or replaced. Browser/network gate outcomes follow.

Final closeout: all 153 maintained-browser cases pass across Chromium, Firefox and
WebKit, including endpoints, interfaces, addresses and wireless assignment regressions.
Chromium/WebKit mobile assignment screenshots were visually inspected. Full
`make test-network-validation` exits 0: network/API, permission/IDOR, runtime RLS,
migration reversal/reapplication, high-volume stabilization and all 536 frontend
tests pass. The focused concurrency regressions, main check, final live workflow
and local rebuild are verified. No known new application regression remains.
Whitespace and route-inventory JSON checks pass. Logs are under
`/tmp/endpoint-layout-` (api-complete, check-complete, live-final, browser-final,
network-gate, up); earlier reproduction logs are named above.

The separate Wiki checkout remains incomplete as previously documented; the scoped
Roadmap update is saved there and unpublished. No production deployment or version
change. This closes the bounded interface endpoint collection/editing/assignment
checkpoint, not endpoint creation/transfers, technician sign-off, Phase 3 or full
pre-1.0 acceptance. Follow-up boundaries remain in interface-endpoints.md.

## DNS zone register and child records — implementation, runtime verification open

Phase 3 (#80), pre-1.0 under #60/#75, version 0.8.46. See dns-register.md.
Implemented DNS navigation, zone register and full drawers, parent-scoped DNS
records, guarded zone/record creation/editing, paged IP inventory choices, collection
APIs and personal preferences; removed the obsolete NetworkServices component.
OpenAPI/types and the local Wiki Roadmap are aligned, without publication.

Verified locally with Node 24.12 and Python 3.13 using pinned Python lock files:
- Eight focused component cases, including SRV zero values, zone/record dirty forms,
  failed writes, parent mismatch, read-only records, IP choices and lazy collections.
- 27 maintained-browser cases pass across Chromium, Firefox and WebKit, covering
  six widths, refresh/full page/Back, focus, no overflow, axe, empty/failed/denied/
  unavailable states, retry recovery, touch, short height and 200% CSS zoom.
- Initial full frontend run: 538 passing tests in 112 files. Final run adds the
  additional focused cases; its result is recorded below when available.
- Lint, TypeScript, frontend build and bundle budgets, backend Ruff and mypy
  (192 source files), generated API check, Wiki manifest, product-boundary and
  interface-language checks pass. Schema generation has zero errors and the two
  pre-existing simplified-network operation-ID warnings.

Reproduced test issues: the new browser failure-state test initially expected
"Retry" while the actual shared control and catalog say "Try again". Browser
snapshots confirmed the control exists. Corrected the exact name and strengthened
it to click the control and assert recovery; all 27 cases pass. The language gate
also rejected the old "Canonical zone name" wording brought into this new view;
changed it to "Zone name" and aligned component/live assertions, without changing
DNS validation.

Blocked runtime evidence: Docker Desktop's socket exists but /_ping times out,
Compose queries do not return, and localhost:3200 was offline before verification.
`make check` was attempted and stopped after 60 seconds waiting for its backend
image prerequisite. PostgreSQL collection/preference tests, the new live DNS
journey, full network validation and local `make up` have not passed on this change.
A temporary frontend served synthetic browser fixtures only; it is not a rebuilt
application. Restart approval was requested because restarting Docker interrupts
other local containers. No engine restart, production deployment, publication,
version change, or user/demo data changes are included.

This slice remains uncommitted pending required Docker evidence, in accordance
with AGENTS.md. Next: restore Docker; run make check and make test-network-validation
(including the new services tests); run the isolated live-workspace rehearsal;
verify DNS zone/record/TTL and audit persistence in its PostgreSQL database; rebuild
local TekDocs; record evidence and commit this bounded slice. Record-level history,
zone transfers, circuits/handoffs, broader inventory and Phase 3 acceptance remain
open. The pre-existing incomplete local Wiki checkout is still not published.

Final local verification: 542 frontend tests pass across 113 files; all 27 DNS
browser cases pass; final lint/typecheck, API generation check, build/bundle budget,
Wiki manifest, product-boundary and language checks pass. The isolated frontend and
stalled Docker CLI requests started for this task were stopped. Docker itself was
not restarted. The requested restart approval is still pending; no runtime closure
or local deployment is claimed.

## DNS record history and navigation follow-up — runtime evidence still open

Continued the existing Phase 3 DNS checkpoint at 0.8.46. Docker /_ping still times
out; no restart approval has been received and no engine restart was attempted.
This pass completes DNS record history within its parent zone drawer rather than
starting another unverified network register.

Implemented a View record history / Back to record details flow with direct
`dns_record_view=history` state and independent `dns_record_history_page` paging.
Existing zone history keeps `history_page`. Record selection clears child history
state; browser Back/Forward, refresh and full-page links retain the selected view.
History uses the existing entity-scoped activity endpoint and permission policy,
loads only on demand, and has readable DNS action labels. Dirty/busy navigation,
denied/failed reads and return-to-details are covered. No model/API change in this
follow-up; RecordActivity keeps its old default and accepts an optional page key.

Reproduction before editing: the new focus check showed the zone heading remained
focused after opening a DNS child record, and history links/views were absent.
Three focused checks failed. Selected child headings now receive focus, and the
new flow passes all 12 DNS component/IP-choice tests. Browser checks pass all 33
cases (11 per Chromium/Firefox/WebKit), including all six widths, history paging
isolation, retained direct links, denial/retry recovery and no extra overlay.
The initial run remains in /tmp/tekdocs-dns-history-before.log; passing evidence
is in /tmp/tekdocs-dns-history-components.log and the browser logs.

The isolated live browser rehearsal now reads created/updated DNS history after
creation and TTL editing. Its embedded PostgreSQL assertions independently verify
zone/record tenant and organization ownership, TXT value, TTL 600, no unexpected
IP link, and exactly the created/updated audit events. Shell syntax and embedded
Python syntax checks pass. This is prepared runtime coverage, not an executed
PostgreSQL or live-browser pass.

Full frontend gate result follows when finished. The prior Docker make-check
blocker still applies: network/database/live gates, local rebuild and the completed
slice commit remain open. Version, existing application data and publication status
are unchanged. Circuits/handoffs and the wider layout migration remain separate
follow-ups; DNS record history is no longer a missing implementation item.

Final history follow-up verification: frontend-gate check passes in full, including
API contract check, lint, TypeScript, 546 tests across 113 files, build and bundle
budgets. All 33 DNS browser cases and all 12 focused component cases pass. Wiki
manifest and language checks pass. The temporary browser-test frontend was stopped.
Runtime verification and local rebuilding remain blocked by Docker, so the DNS
slice is still not committed or declared complete. Final evidence:
/tmp/tekdocs-dns-history-frontend-gate.log,
/tmp/tekdocs-dns-history-browser.log (Chromium), and
/tmp/tekdocs-dns-history-browser-all.log (Firefox/WebKit).

## DNS runtime closure — Docker recovered

Resumed the DNS checkpoint after the user's continuation of the restart discussion.
The normal Docker Desktop restart failed after 45 seconds because its processes
would not exit. Docker's supported force-stop followed by start recovered the
engine; /_ping returns OK and the existing TekDocs services report healthy. No
Docker reset or container/volume deletion was used for recovery.

`make check` now passes with Docker backend checks and all 546 frontend tests.
All 14 network-service PostgreSQL cases pass, including the new DNS collection
and personal-column cases. Full network validation and the isolated live browser
rehearsal are running. The previous runtime blocker is resolved; this entry does
not yet claim completion of those remaining gates or the local rebuild.


### DNS runtime retry and long-name accessibility

The first combined runtime attempt did not close the checkpoint: the network
suite lost its Docker connection at 79% (unexpected EOF), while the live browser
rehearsal timed out on the DNS Type field. Docker subsequently reported healthy;
the full network gate was rerun separately and passed, including stabilization
and all 547 frontend tests. No existing application volumes were reset.

The browser failure was reproduced independently against the current frontend:
exact label lookup included nested select/textarea content, while the accessibility
tree correctly exposed combobox Type and textbox Value. The tests now use those
exact accessible roles and names. An added browser regression changes type and
value, saves both, and checks the retained result. All 36 DNS cases pass across
Chromium, Firefox and WebKit. This corrects the harness without relaxing assertions.

A failing component regression also reproduced that read-only users could not
access the full long zone name on Overview. Overview now exposes the complete
name in the existing wrapping record-facts layout. All 13 focused DNS component
checks pass. No CSS, schema, permission or version change was needed.

Evidence: /tmp/tekdocs-dns-network-retry.log,
/tmp/tekdocs-dns-type-before-current.log,
/tmp/tekdocs-dns-browser-final2.log,
/tmp/tekdocs-dns-long-name-before.log,
/tmp/tekdocs-dns-components-final.log. The corrected live rehearsal and final
make check are in progress; completion and local rebuild evidence follow below.


### DNS update runtime regression

The corrected live browser reached creation but exposed HTTP 500 on TXT-record
TTL updates. A new PostgreSQL regression reproduced the exception directly:
`FOR UPDATE cannot be applied to the nullable side of an outer join`. The DNS
update service had selected an optional IP relationship with an unrestricted row
lock. It now locks only the DNS record and its entity, matching the existing
wireless update pattern, while preserving scoped relationship validation and the
DNS advisory lock. The regression verifies a partial TTL update preserves all
other fields, parent/workspace ownership and the created/updated audit pair.
Evidence before the fix: /tmp/tekdocs-dns-live-retry.log and
/tmp/tekdocs-dns-update-before.log. This is a runtime bug fix within the DNS
migration acceptance boundary; no schema or API contract change is introduced.


### DNS checkpoint verified

Verified after the save fix: `make check` passes (547 frontend tests, API contract,
backend static checks, migration consistency, build/budgets); all 15 network-service
PostgreSQL tests pass; all 12 collection-preference tests pass. The broader
`make test-network-validation` passed before the one-line DNS locking correction;
the affected network-service suite and complete live journey were rerun afterward.
All 36 DNS browser cases and 13 component cases pass. `make test-e2e-live` completed
successfully, including the independent DNS retained-row/ownership/audit assertions.
Wiki manifest contract passes (37 pages, 25 topics). The local Wiki Roadmap is
updated; publication and repair of the preexisting incomplete Wiki checkout remain
separate from this local checkpoint.

Evidence: /tmp/tekdocs-dns-check-closure.log,
/tmp/tekdocs-dns-update-after.log,
/tmp/tekdocs-dns-preferences-final.log,
/tmp/tekdocs-dns-network-retry.log,
/tmp/tekdocs-dns-browser-final2.log,
/tmp/tekdocs-dns-components-final.log,
/tmp/tekdocs-dns-live-final.log.

This completes the bounded DNS migration, not Phase 3 or the overall interface
plan. Circuits/handoffs, endpoint creation/transfers, remaining network surfaces,
technician walkthroughs and release acceptance remain open. Version stays 0.8.46.


Local availability: `make up` completed successfully. Readiness at
http://localhost:3200/api/v1/health/ready reports status ok, database and diagram
renderer ready, version 0.8.46; frontend/backend and supporting health-checked
services report healthy. Existing database and application volumes were retained.
Test the migrated surface from Networks → DNS. Build evidence:
/tmp/tekdocs-dns-local-up.log. No production deployment, push or publication.


## Circuit register and service-detail checkpoint — implementation

Resumed Phase 3 (#80) after DNS commit 9f9f18a. The old circuit component was
unmounted, fetched every selected row's handoffs and filtered only its first 100
records. Replaced it with the shared collection/drawer, service-detail editor,
Overview lifecycle warnings, lazy handoff collection/details and circuit history.
Creation, provider/contract changes, status workflows and handoff editing/placement
are explicitly deferred to the next bounded slices; see circuit-register.md.

The focused PostgreSQL circuit/preference run passes 18 cases, including 31-record
collections, legacy array/detail compatibility, query bounds and scoped child reads.
Six new component cases pass. All 30 circuit browser cases pass across Chromium,
Firefox/WebKit, six widths, short-height touch, 200% zoom, focus and dirty forms.
Initial browser test errors were reproduced: Search matched the shell and collection
buttons, and an unavailable direct link expected a page-two row on page one. Tests
now scope Search to main and explicitly retain page two for that return scenario.
The component harness was corrected to use native-dialog backdrop events and the
activity client's existing workspace argument. No UI assertions were removed.

Build/type checks pass and the original bundle budgets remain unchanged. OpenAPI
now explicitly models legacy array versus paginated handoffs; a generation warning
revealed the required many=False on the response union, which was corrected before
regenerating types. The existing handoff list operation IDs are preserved.

Full network validation, final make check and the extended live rehearsal remain
in progress. No completion or local-rebuild claim yet. Evidence so far:
/tmp/tekdocs-circuit-api.log, /tmp/tekdocs-circuit-components2.log,
/tmp/tekdocs-circuit-browser2.log, /tmp/tekdocs-circuit-frontend-build.log.


### Circuit verification follow-up

All 33 circuit browser cases now pass, including failure/retry into an empty
collection, six widths, touch and 200% zoom. Main make check passed with 553 frontend
tests; final generated-contract, lint and type checks pass. Existing operation IDs
were compared before/after and none changed. The final serializer metadata retains
required nested contract dates and handoff descriptions; only summary-omittable
circuit fields are optional.

A review preserved the existing prefetch for legacy full circuit details while
explicitly skipping it for parent existence checks and the new detail/summary
forms. Added a regression comparing empty versus 31-handoff legacy detail query
counts so legacy callers do not acquire per-row identity queries.

Do not use /tmp/tekdocs-circuit-network.log or
/tmp/tekdocs-circuit-api-final.log as successful evidence: two temporary test-database
jobs overlapped during migration tests, producing existing-table errors. The invalid
run was stopped and all affected checks are rerunning serially from fresh test
setup in /tmp/tekdocs-circuit-network-serial.log. The application database is separate
and readiness remained healthy at 0.8.46; no application volume was reset.

The first isolated live circuit fixture submitted the vendor route's /overview
suffix instead of its UUID and correctly received 400. The fixture now uses the
existing organization-ID extraction pattern and validates that ID before creating
records. The corrected rehearsal is /tmp/tekdocs-circuit-live2.log. No product
validation was relaxed to make the fixture pass. Completion remains pending.


### Circuit live/runtime results

The corrected isolated live rehearsal passed end to end, including independent
PostgreSQL assertions for circuit and handoff tenant/workspace ownership, retained
provider/service ID/status, absent unintended contract/interface links and the
single expected circuit update event. Evidence: /tmp/tekdocs-circuit-live2.log.
All 33 circuit browser cases pass in /tmp/tekdocs-circuit-browser-final.log; all
553 frontend tests passed in the main project check. Final backend Ruff/mypy pass
(192 source files), and generated contract, TypeScript and lint checks pass.

The fresh serial network regression set reached 100% successfully, including
migration restoration, runtime/permission isolation and the legacy query-count
regression. This supersedes the discarded overlapping run. Its stabilization and
frontend sub-gates are finishing; final gate and local-delivery results follow.


### Circuit register/service-detail checkpoint verified

The complete serial `make test-network-validation` finished successfully, including
migration/isolation restoration, stabilization and 553 frontend tests. This is the
valid runtime result; the earlier overlapping jobs are discarded. The final test
set includes the legacy 31-handoff detail query-count regression. Main make check,
33 maintained-browser cases, six component cases, final contract/static checks and
the isolated live browser/database rehearsal all pass.

Evidence: /tmp/tekdocs-circuit-network-serial.log,
/tmp/tekdocs-circuit-check2.log,
/tmp/tekdocs-circuit-browser-final.log,
/tmp/tekdocs-circuit-components2.log,
/tmp/tekdocs-circuit-live2.log,
/tmp/tekdocs-circuit-final-contract.log,
/tmp/tekdocs-circuit-static-final.log,
/tmp/tekdocs-circuit-types-final.log,
/tmp/tekdocs-circuit-lint-final.log.

This closes circuit browsing, service-detail editing and handoff browsing only.
Creation, provider/contract assignment, lifecycle status operations and handoff
creation/editing/placement remain next slices, with their bounded-picker and
permission/confirmation requirements recorded in circuit-register.md. Broader
Phase 3, technician walkthroughs, production-image/release acceptance and other
pre-1.0 obligations remain open. Version remains 0.8.46. Wiki Roadmap changes are
local; publication is separate. The authorized local rebuild is running.


Local delivery: `make up` completed successfully. Readiness at
http://localhost:3200/api/v1/health/ready returns status ok, database/diagram renderer
ready and version 0.8.46; frontend/backend and health-checked dependencies are
healthy. Existing application/demo data and volumes were preserved. Test from
Networks → Circuits. Evidence: /tmp/tekdocs-circuit-local-up.log. No production
push, deployment, version bump or Wiki publication was performed.

### Circuit provider/contract choice prerequisite — implementation

Phase 3 #80 / #60 / #75: added opt-in paginated circuit provider/contract choices,
name search, deterministic ordering, provider filtering and separately resolved
retained selection. Legacy callers retain their response. Contract visibility
applies to requests, counts and selected values. The separate frontend adapter
and generated contract prepare creation/assignment without enabling unfinished UI.

Acceptance covers 101 providers (including the previous cutoff), equal-name
contract paging, retained selections outside search, provider mismatch, sibling
workspace and foreign tenant exclusion, denied contract access, invalid queries,
anonymous denial and legacy compatibility. Runtime/static verification is pending.
Creation/assignment drawers, status operations and handoff editing remain open.

Static verification: `make check` passes, including 554 frontend tests, API/type
consistency, backend Ruff/mypy, migration drift checks and unchanged build budgets.
The four focused network API-adapter cases pass from the frontend test environment.
Evidence: /tmp/tekdocs-choice-check-final.log and
/tmp/tekdocs-choice-adapter-final.log. Wiki contract passes (37 pages/25 topics).
Initial runs exposed a missing required contract kind in synthetic fixtures and
queryset typing errors; corrected without changing production business rules or
weakening assertions. An adapter invocation from the repository root lacked the
frontend browser-test environment; its result is discarded in favor of the
correct frontend invocation. Full serial network validation is still pending.

Full network run reached completion. Circuit choices, workspace/tenant isolation,
permission inventory and migration cases passed. One existing IPv4 property test
failed Hypothesis's input-generation speed health check (6 inputs in 1.06 seconds),
not its canonical-network assertion. The exact reported seed
140765790039409104343129155310579543983 passes on an unchanged isolated retry.
No health checks were suppressed and no assertions were weakened. Evidence:
/tmp/tekdocs-choice-network.log and /tmp/tekdocs-choice-ipv4-retry.log.
This is not a clean single-invocation `make test-network-validation` result;
downstream stabilization is being run separately. The next full release gate must
confirm a clean complete run. No presentation changed, so the prior circuit browser
and live-workflow evidence remains historical, not a new browser claim for this API
prerequisite. Existing API operation IDs were independently compared and preserved.

Downstream `make test-network-stabilization` passes unchanged after the exact-seed
retry. Frontend coverage was already completed by `make check` (554 tests).
Evidence: /tmp/tekdocs-choice-stabilization.log. The API prerequisite is verified
with the broader gate's timing caveat above; no migration, new permission, version
bump or visible creation/assignment UI is included. Local rebuild is in progress.

Local delivery: `make up` completed. Readiness at localhost:3200 reports status ok,
database and diagram renderer ready, version 0.8.46. Existing user/demo data and
volumes were preserved. Evidence: /tmp/tekdocs-choice-local-up.log. No push,
production deployment, release or Wiki publication occurred.

### Circuit creation and assignment drawers — implementation

Phase 3 #80 under #60/#75: New circuit now creates an Ordered service in the
existing overlay, with named identity, service identifier, kind, provider, optional
contract and notes. Successful creation opens Overview and releases the draft
guard. Provider/contract edits use a separate focused form, preserving service
fields and withholding restricted contract projections. Provider changes clear
the draft contract. Pickers use the previously verified bounded API and retain
selected labels outside search/pages. No new CSS, model, migration or API contract.

All 51 circuit browser cases pass across maintained engines, including all six
required widths, accessibility, provider change/contract clearing, dirty cancel,
creation, refresh and dismissal. Focused editor/register tests pass. Main checks
and the isolated live creation journey are running. The initial image build
exposed unsupported Testing Library selector options and untyped test mocks;
corrected test types/options without changing assertions or production behavior.
The limited focused coverage invocation is not a full coverage gate.

Handoff creation/editing, placement, status/kind transitions, technician acceptance
and the broader pre-1.0 release gate remain open. Version remains 0.8.46.

Main `make check` passes with 558 frontend tests in 115 files, backend/static/API
checks, migration drift checks and the existing build budgets. All 51 circuit
browser cases pass. Evidence: /tmp/tekdocs-circuit-create-check2.log and
/tmp/tekdocs-circuit-create-browser.log. No backend domain/API logic changed in
this slice; prior provider/contract isolation validation remains documented above.
The isolated live rehearsal is in progress and now creates through the drawer.

The isolated `make test-e2e-live` passes, including browser creation through New
circuit, saved Overview navigation, service editing/reload, handoff browsing and
history. Independent PostgreSQL assertions confirm exact workspace/tenant,
provider, service identifier, Ordered status, absent contract/interface linkage
and one service-update audit event. Evidence:
/tmp/tekdocs-circuit-create-live2.log. Fixtures use an isolated stack and preserve
existing user/demo data. The initial image build is discarded; corrected build
and live run pass. This closes creation and provider/contract editing, not circuit
status operations, handoff editing/placement or Phase 3 acceptance.

Local delivery: `make up` completed and readiness at localhost:3200 reports ok,
database/diagram renderer ready and version 0.8.46. Existing application/demo
volumes and data were preserved. Evidence:
/tmp/tekdocs-circuit-create-local-up.log. Test from Networks → Circuits → New circuit,
or a visible-contract circuit Overview → Edit provider and contract. No push,
production deployment, release version change or Wiki publication occurred.

### Handoff creation/details/placement — implementation

Phase 3 #80 under #60/#75: parent circuit Handoffs now supports New handoff,
separate guarded detail and placement forms, bounded site/location/device/interface
choices and focused save/return navigation. Details preserve placement; placement
preserves identity/service facts. Dependent draft selections clear on parent changes.
Read-only and server-conflict cases preserve authoritative permissions and rules.
The API types reflect existing partial PATCH and circuit_id responses; no backend
mutation/schema changes, new CSS, migration or dependency.

Eleven focused handoff/circuit component cases pass. Main checks, browser widths
and the isolated live creation/placement rehearsal are running. Focused PostgreSQL
circuit tests add partial-edit preservation, duplicate interface rejection, invalid
device/interface pairing and valid paired clearing. No main database test jobs
overlap. Remaining scope: handoff history, circuit lifecycle/status and wider
Phase 3/technician/release acceptance. Version remains 0.8.46.

Focused Docker PostgreSQL circuit tests pass (seven cases), including the new
partial handoff detail preservation, duplicate interface rejection, invalid
paired placement rollback and valid device/interface clearing. Evidence:
/tmp/tekdocs-handoff-api.log. Initial browser run reproduced three Firefox strict
selector failures: pending save briefly exposed both selected-location text and
an option with the same name. The test now waits for the saved view and checks its
exact `dd` location fact, strengthening persisted-state verification. No production
workaround or weakened assertion. An intermediate run captured the old selector;
only the final updated run counts as browser evidence. A fixture spread assertion
was also corrected for the existing lint rules. Main checks and live stack remain
in progress. Component evidence: /tmp/tekdocs-handoff-components.log.

All 72 maintained-browser cases pass after the exact saved-fact selector fix.
Evidence: /tmp/tekdocs-handoff-browser-final.log. Main checks exposed one obsolete
`as never` fixture cast when the handoff update type became partial; removed only
that cast, preserving the request assertion. The final main gate is rerunning.
No production mutation rules or database schema were altered.

The isolated `make test-e2e-live` passes. Circuit and handoff creation, placement
assignment and detail editing run through the browser, then reload/return/history.
Independent PostgreSQL assertions confirm exact ownership, site/location/device/
interface links, retained provider reference, saved notes and one handoff-created
plus two handoff-updated audit events. Evidence: /tmp/tekdocs-handoff-live.log.
Existing user/demo data and main volumes remain untouched by the isolated fixtures.

Final `make check` passes with 564 frontend tests in 116 files, backend Ruff/mypy,
API/generated-type consistency, migration drift and unchanged build budgets.
Evidence: /tmp/tekdocs-handoff-check-final.log. Final browser evidence is 72 cases,
focused PostgreSQL circuit evidence is seven cases, and the isolated live journey
passes. This closes handoff creation, detail editing and placement only. Circuit
status/kind workflows, handoff-specific history, technician acceptance and broader
pre-1.0 release gates remain open. Local rebuild is running at version 0.8.46.

Local delivery: `make up` completed. Readiness at localhost:3200 reports ok,
database/diagram renderer ready and version 0.8.46. Existing application/demo data
and volumes were preserved. Evidence: /tmp/tekdocs-handoff-local-up.log. Test from
Networks → Circuits → selected circuit → Handoffs: New handoff, Edit handoff details
or Edit handoff placement. No production push/deployment, release/version change
or Wiki publication occurred.


## 2026-09-15 — Phase 3 selected handoff history

Implemented the next #80 slice under #60/#75 at 0.8.46. Handoff history is now a
lazy focused reader inside the circuit drawer with direct section/page URLs,
25-event pages, explicit retry, denied/empty states and return heading focus.
No child drawer or tab bar. Parent and child return links clear selected child
history state, including mobile navigation. Existing dirty forms remain guarded.

The additive activity `handoff_id` filter requires its parent `entity_id`, validates
exact workspace/parent membership and requires activity-view plus network-view.
Existing circuit-owned audit rows are filtered without rewriting them or exposing
metadata. Legacy activity behavior, permission boundaries and deterministic paging
remain compatible. OpenAPI/generated types updated; no migration or CSS change.

Verified: focused components/API-client 27 cases; `make check` passed with 566
frontend tests in 116 files, Ruff/mypy, schema/type/migration checks and existing
bundle limits. PostgreSQL focused circuit/document activity 15 cases passed,
including 31-event paging, repeat ordering, isolated handoffs, malformed filters,
wrong parent, sibling workspace, foreign installation, denied reader and independent
network-view denial. Isolated live browser→Django→PostgreSQL rehearsal passed,
including real handoff creation, placement/detail edits, selected history and refresh.
Evidence: /tmp/tekdocs-handoff-history-components-final.log,
/tmp/tekdocs-handoff-history-api-current.log,
/tmp/tekdocs-handoff-history-check-final.log and
/tmp/tekdocs-handoff-history-live.log.

Test corrections: the first browser accessibility selector looked for an explicit
role attribute, while our drawer is a native dialog; changed to the established
collection-drawer selector without changing accessibility assertions. A child URL
cleanup assertion initially matched the valid parent section value `handoffs`;
corrected it to check the actual handoff/section/page parameter keys. A denial
component spy retained prior test calls; resetting that spy isolates the no-retry
assertion. The first reader-denial fixture lacked organization access; added an
explicit assignment and rebuilt the backend test image before the passing run.
No application permission or assertion was weakened.

Final browser sweep passed 90 cases across Chromium/Firefox/WebKit, all six widths,
refresh, URL paging, return links, browser Back, focus and axe checks. Evidence:
/tmp/tekdocs-handoff-history-browser-complete.log. The full `make test-network-validation` gate passed, including network APIs,
reconciliation/transfers, relationship/permission/RLS coverage, migration recovery,
scale/stabilization and the final 566-test frontend suite. The main suite includes
one skipped check; this does not close broader acceptance. Evidence:
/tmp/tekdocs-handoff-history-network-gate.log. Circuit kind/status
workflows, technician walkthroughs and broader Phase 3/pre-1.0 release gates remain
open. This checkpoint does not replace security, recovery or financial obligations.
Wiki Roadmap updated locally; publication/deployment/version changes remain separate.


Local delivery: built current backend/migrate/frontend images and restarted only
backend/frontend with no dependencies, since this slice requires no migration.
This avoids concurrent migration work while the network test database is active.
Readiness at localhost:3200 reports status ok, database/diagram renderer ready and
version 0.8.46. Existing application/demo data and volumes were preserved. Evidence:
/tmp/tekdocs-handoff-history-local-up.log. No production deployment, push, release
change or Wiki publication occurred.

## 2026-09-15 — Circuit kind and status workflows

Completed the next bounded Phase 3 #80 slice under #60/#75 at version 0.8.46.
Circuit Overview now has separate focused kind and status editors. Suspension and
disconnection require an in-page review step that states TekDocs records the value
without contacting the provider or changing carrier service. Mutations submit only
the selected field, retain failed drafts without automatic retry and use the shared
dirty-navigation guard. The same component serves drawer and full-page routes; a
status change that leaves the active list filter shows the existing out-of-filter
notice. Read-only users receive no mutation controls. No API, model, migration,
permission, dependency or CSS change.

Verified: the frontend check gate passed with 568 tests in 116 files, lint,
typecheck, API/generated-type consistency, production build and existing bundle
budgets. The maintained-browser circuit sweep passed 90 unaffected cases; after an
assertion was corrected to use the actual localized out-of-filter sentence, the new
kind/status case passed in Chromium, Firefox and WebKit, for effective coverage of
all 93 cases. The isolated live browser→Django→PostgreSQL journey passed and its
independent database assertions confirmed WAN kind, Suspended status and three
append-only circuit update audit events. The first live run reached the correct
history but its old single-event locator became ambiguous after the two added
updates; the corrected assertion requires exactly three events.

Broader Phase 3 acceptance, remaining network surfaces, technician/native zoom and
screen-reader walkthroughs, and pre-1.0 release gates remain open. Existing user and
demo data were preserved. No push, production deployment, release change or Wiki
publication occurred.

## 2026-09-15 — Direct interface endpoint creation

Completed the next bounded Phase 3 #80 slice under #60/#75 at version 0.8.46.
Selected interfaces now create IP and MAC records directly in the existing drawer.
IP creation uses a searchable, paged subnet choice; creating a new record and
assigning an existing unbound record are separate actions. Successful creates open
the saved detail, while failed creates retain the draft and never retry automatically.
No CSS, model, migration, permission grant or dependency changed.

The create API accepts an optional exact-workspace `interface_id` and writes the
record and binding atomically. Interface and hardware bindings are mutually exclusive;
network-edit and existing hardware-edit policies remain authoritative. Subnet lists
now support bounded search, stable name/CIDR ordering and summary responses. OpenAPI
and generated client types are aligned.

Verified: `make check` passes with 571 frontend tests in 116 files, Ruff/mypy,
schema/type/migration checks and existing bundle budgets. All 36 focused endpoint
browser cases pass across Chromium, Firefox and WebKit, including six maintained
widths. The full `make test-network-validation` gate passes its PostgreSQL API,
permissions, RLS, reconciliation, transfer, recovery and scale coverage, with its
one expected skip and repeated frontend suite.

The isolated `make test-e2e-live` browser→Django→PostgreSQL journey passes. It creates
an IP and MAC through the selected interface, edits and reloads them, then removes the
MAC binding. Independent database assertions confirm exact interface binding, retained
IP and removed-MAC history, plus one IP create/update and one MAC create/two update
audit events. Existing application/demo volumes were preserved. The first main check
found two overlong test assertions; the second exposed an asynchronous dialog query.
Formatting the assertions and waiting for the rendered dialog resolved both without
changing behavior or weakening coverage.

Endpoint transfers, device relationship/hardware rebinding, remaining network
surfaces, technician walkthroughs and broader Phase 3/pre-1.0 acceptance remain open.
No push, production deployment, release/version change or Wiki publication occurred.

## 2026-09-16 — Conflict-safe interface endpoint transfers

Completed the next bounded Phase 3 #80 slice under #60/#75 at version 0.8.46.
Selected IP and MAC records now offer a separate Move to another interface workflow.
The destination picker is bounded and searchable by interface or device name across
the exact workspace. It retains the explicit destination through searches and failed
writes, never retries an uncertain mutation, and returns to the original interface's
endpoint list after a successful move.

The existing assignment PATCH now permits interface-to-interface transfer while the
record is locked. It still requires the expected current interface, rejects stale or
same-interface requests, resolves the destination in the exact workspace and refuses
to replace a hardware binding. Ordinary endpoint edits continue to omit all binding
fields. No route, model, migration, permission grant, dependency or CSS changed.

Verified: the focused PostgreSQL API cases pass for IP and MAC transfer, device-name
search, same-interface/stale conflicts, workspace denial, hardware protection and
audit counts. The frontend check gate passes with 575 tests in 116 files, lint,
typecheck, API consistency, production build and bundle budgets. All 42 focused
endpoint browser cases pass in Chromium, Firefox and WebKit, including six maintained
widths. The isolated browser→Django→PostgreSQL journey passes; it creates two
interfaces, moves the IP between them and independently verifies the stored destination
and two append-only IP update events. The first live run completed the browser journey
but its prior database assertion expected the original binding; the corrected audit
now verifies the transfer rather than weakening coverage.

Moving interfaces between devices, device relationship/hardware rebinding, remaining
network surfaces, technician walkthroughs and broader Phase 3/pre-1.0 acceptance
remain open. No push, production deployment, release/version change or Wiki
publication occurred.

## 2026-09-16 — Conflict-safe interface device moves

Completed the next bounded Phase 3 #80 slice under #60/#75 at version 0.8.46.
Selected interface details now move the interface to another device through a
searchable, paged destination picker. The picker retains an explicit choice through
searches and failed writes, participates in the shared navigation guard and returns
to the source device's interface list after success. Existing IP and MAC records move
with the interface.

The focused PATCH accepts only the destination device and expected current device.
The service locks the interface, rejects stale and same-device requests, resolves the
destination in the exact workspace and applies destination interface-name uniqueness.
It refuses to move interfaces used by circuit handoffs or imported addresses that
still carry a hardware binding. Ordinary detail edits cannot replace the parent.
No route, model, migration, permission grant, dependency or CSS changed.

Final verification: focused PostgreSQL API tests cover success, stale/same-device and
workspace failures, retained endpoints, audit history, circuit handoff protection and
legacy hardware protection. Component/API-client tests pass for successful and failed
moves without retry. All 33 focused interface browser cases pass in Chromium, Firefox
and WebKit across the six maintained widths. `make check` exits 0 with backend
lint/types/migration drift, API schema agreement, all 577 frontend tests in 116 files,
coverage and the production bundle budget. `make test-network-validation` exits 0 for
the complete PostgreSQL network, stabilization and repeated frontend suites. The
isolated live browser-to-Django-to-PostgreSQL rehearsal also passes and independently
verifies the destination device, retained IP binding and interface update audit.

Device relationships and hardware rebinding, remaining network surfaces, technician
walkthroughs and broader Phase 3/pre-1.0 acceptance remain open. No push, production
deployment, release/version change or Wiki publication occurred.

## 2026-09-16 — Device relationships within device records

Completed the next bounded Phase 3 #80 slice under #60/#75 at version 0.8.46.
Authorized device records now include a Relationships section in the existing drawer
and full-page view. It supports direct URLs, permission-controlled visibility,
exact-workspace device search, typed link creation and relationship removal. Draft
searches and selections participate in the shared navigation guard, and failed reads
or writes remain visible without automatic retries.

Existing relationship endpoints, models and permissions remain authoritative. The
device collection exposes the existing view, create and archive capabilities so the
record can omit unavailable sections and actions before a request is attempted. New
workflow copy uses the shared translation catalog. No route, model, migration,
permission grant, dependency or CSS changed.

Final verification: `make check` exits 0 with backend lint, types, migration drift,
API schema agreement, all 579 frontend tests in 116 files, coverage and the production
bundle budget. All 33 focused device browser cases pass in Chromium, Firefox and
WebKit across the six maintained widths, including create, reload, archive,
navigation protection and accessibility. The isolated live
browser-to-Django-to-PostgreSQL rehearsal also passes and independently verifies the
exact `Connected to` link and its single creation audit event.

Hardware rebinding, remaining network surfaces, technician walkthroughs and broader
Phase 3/pre-1.0 acceptance remain open. Existing application and demo data were
preserved. No push, production deployment, release/version change or Wiki publication
occurred.

## 2026-09-16 — Conflict-safe device hardware replacement

Completed the next bounded Phase 3 #80 slice under #60/#75 at version 0.8.46.
Authorized device records now include a Hardware section in the existing drawer and
full-page view. It supports direct URLs and a bounded, paged search of unlinked
hardware assets in the exact workspace. The section requires both network-edit and
asset-view access. Search and selection drafts participate in the shared navigation
guard, remain visible after failed writes and are never retried automatically.

Replacement uses an isolated two-field PATCH containing the new asset and expected
current asset. The service locks only the device row, rejects stale, same, occupied
and cross-workspace choices, and preserves placement, interfaces, endpoints and typed
relationships. Ordinary device and placement edits cannot change the hardware
binding. No route, model, migration, permission grant, dependency or CSS changed.
OpenAPI and generated client types are aligned with the additive conflict response,
expected-binding field and combined capability.

Final verification: all 11 focused PostgreSQL inventory tests pass, covering success,
conflicts, scope, permission denial, separation from ordinary edits and audit history.
The frontend gate passes with 580 tests in 116 files, lint, typecheck, API agreement,
coverage, production build and existing bundle budgets. All 36 focused device browser
cases pass across Chromium, Firefox and WebKit at the six maintained widths, including
touch replacement, reload, navigation protection and accessibility. `make check` and
the complete `make test-network-validation` PostgreSQL, stabilization and repeated
frontend workflow both exit 0.

The isolated browser-to-Django-to-PostgreSQL journey passes. It replaces a device's
hardware after creating placement, interfaces, endpoints and a relationship;
independent database assertions confirm the replacement, released original asset,
retained connected records and three append-only device update events. The first live
run exposed a PostgreSQL nullable-join row-lock defect in ordinary device edits; the
lock now targets only the device row. A repeated full gate then exposed an immediate
capability assertion in the new component test; waiting for the asynchronously loaded
authorized section removed that timing sensitivity and passed three focused repeats
plus the complete target rerun.

Remaining network surfaces, technician walkthroughs and broader Phase 3/pre-1.0
acceptance remain open. Existing application and demo data were preserved. No push,
production deployment, release/version change or Wiki publication occurred.

## 2026-09-17 — Conflict-safe DNS record transfer

Completed the next bounded Phase 3 #80 slice under #60/#75 at version 0.8.46.
Selected DNS records now offer **Move to another zone** inside the existing record
view. The action searches exact-workspace zones in bounded pages and suggests the
corresponding owner name while keeping it editable. Search, selection and owner-name
drafts participate in the shared navigation guard; failed writes remain visible and
are not retried automatically.

Transfer uses an isolated three-field PATCH containing destination zone, expected
current zone and owner name. The locked service rejects stale, same-zone,
cross-workspace, mixed-edit and invalid-owner requests while retaining the record's
type, value, TTL, type-specific fields, IP link, description, identity and history.
No route, model, migration, permission, dependency or CSS changed. OpenAPI and the
generated client contract include the expected-zone field and conflict response.

Focused service, component, API-client and responsive browser coverage exercise the
bounded workflow and its failure protection. The live browser journey creates two
zones, moves an edited TXT record, reloads it from the destination and independently
checks exact ownership, retained TTL/value/IP state and three append-only audit
events in PostgreSQL. See [dns-record-transfer.md](dns-record-transfer.md) for the
implemented contract and final gate evidence.

Final verification: `make check` exits 0 with backend lint and types, migration and
API-schema agreement, all 581 frontend tests in 116 files, coverage, the production
build and existing bundle budgets. The focused move passes in Chromium, Firefox and
WebKit. The isolated live browser-to-Django-to-PostgreSQL journey and its independent
database assertions pass. The complete `make test-network-validation` PostgreSQL,
stabilization and repeated 581-test frontend workflow also exits 0.

Remaining network surfaces, technician walkthroughs and broader Phase 3/pre-1.0
acceptance remain open. Existing application and demo data were preserved. No push,
production deployment, release/version change or Wiki publication occurred.
