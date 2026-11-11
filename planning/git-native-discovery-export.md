# Native discovery and Markdown export completeness

Scope: the first bounded fix from the November 2 clean-start workflow audit.
Acceptance: list/search current authorized older, promoted and Git-native documents
exactly once; exclude fragments and archived legacy shadows; preserve filters,
facets, ranking and pagination; route native selection to the repository editor;
export through independent ordinary/repository inventories with exact content-ID
deduplication and visible incomplete/stale/error states. Preserve privacy and
existing export files. No document, schema, authority, publication, file custody,
portal permission or production operation is changed.

Reproductions before implementation:

- Docker `test_library_lists_legacy_and_native_documents_without_fragments`
  failed with count 1 instead of 2 against the real API (55.61 seconds).
- Exporter HTTP-boundary regression
  `test_graph_inventory_finds_native_document_missing_from_older_search`
  failed with 1 saved document instead of 2.

Implementation and contract:

- Existing ordinary list/search responses gain `repository_native` (false for
  legacy/promoted rows, true for native-only summaries). Native summary IDs are
  content UUIDs, not invented operational Entity or legacy Document records.
  Legacy lifecycle arrays are empty in these summaries; actual native files and
  publication evidence remain on repository APIs. Selection opens the existing
  repository editor rather than trying legacy controls.
- Exact-Workspace accepted/indexed document nodes supply current native metadata
  and composed search text. Legacy rows, including archived rows, are excluded
  from the native projection. Native discovery remains staff-only; it is not
  client publication. Stale indexes fail visibly rather than omitting content.
- Repository read-list items also identify native-only ownership, allowing the
  exporter to distinguish new documents from archived/shadow legacy copies.
  Both inventories are checked. Unknown ownership on an omitted older-server
  graph entry, pagination/count drift, stale indexes and HTTP failures prevent
  a complete-success report. Successful local files remain available.
- The export still covers current Markdown only. It does not migrate identities,
  reconstruct history or back up file bytes, signatures or publication records.

## Validation and review

Verified locally on November 2, 2026:

- Both named red reproductions above failed before their corrections.
- The `test-content-authoring` aggregate was run by `docker compose exec` with
  its module set plus the new discovery regression and existing canonical
  promoted-document search regression. It passed. The new final six-case
  discovery matrix passed again after the ordering review (69.23 seconds),
  including constrained runtime-role scope, portal/foreign denial, archived
  shadow exclusion, filters/facets/pagination and stable per-path modification
  ordering after an unrelated fragment change.
- Thirteen exporter HTTP-boundary cases passed in the existing Docker service,
  including older/native inventory reconciliation, promoted deduplication,
  duplicate titles, archived shadows, stale/partial inventories, failures,
  redirect refusal, empty documents, private files and overwrite refusal.
- 104 focused Documentation/repository-editor component cases passed. The added
  native-selection test also passed after its final mock-reference cleanup.
  Its initial URL-state leak caused subsequent test failures; restoring the
  original URL in `finally` corrected the harness without loosening assertions.
- `make test-publication-browser-live` passed all ten real browser/server
  journeys with zero retries, including the new UI-created native-document
  library/reopen journey. Server custody/rollback verification passed too.
  `artifacts/playwright-safe/publication-live.json` records `status: passed`
  and `server_verification: passed`. Existing signed publications, file/PDF
  histories, client workflows and cross-Workspace reuse journeys remain passing.
- `make test-automated-security-review-gate`: 158 cases, three optional skips.
  Backend lint/types, frontend lint/types, generated OpenAPI/TypeScript parity,
  migration drift check and Wiki links passed. Schema generation retains the
  four existing operation-ID warnings; no schema migration is needed.
- Both code-review axes completed: **Standards: zero findings. Spec: zero
  remaining findings.** The two initial Spec findings were resolved with a
  combined title sort and verified per-path Git dates rather than repository-wide
  modification timestamps. File-history reads use the existing shared lock and
  bounded runner with literal pathspecs and NUL framing; they perform no
  reconciliation write. Native dates describe the current path's retained
  history; a move establishes a new path, not a fabricated legacy creation row.

## Data, compatibility and remaining gates

No retained development or production document, authority, publication, file,
volume or schema was changed or deleted. All runtime tests used generated test
records/databases in the existing database service; the browser harness reused
and restored the existing development services. No production access or actual
user-document export was performed.

The response additions are additive. Reverting the application requires no data
rollback or backfill. Native lifecycle controls and configuration remain later
bounded slices; these discovery summaries do not pretend those controls exist.
The six deferred legacy-import gaps remain deferred. Version remains 0.9.18
development; this is not a new release, deployed fix or aggregate 1.0 acceptance.

Exact-source hosted Build/CodeQL/Extended checks remain required after an
explicitly authorized push. Unmodified Make targets that launch extra containers
were adapted to `exec`; full matrix, production-image, upgrade and independent
recovery rehearsals that provision additional environments remain hosted under
the repository's single-project rule. Previous HEAD's green CI is historical
and does not validate this changed runtime. Wiki edits are prepared locally,
not publicly published. No new risk waiver is requested or inferred.

## Hosted CI follow-up after `0a7c69dc`

Build 41551455933 failed live-workspace job 125642915846 at the supplier
publication list. The original backend log shows ordinary document search
returning 409. A fresh Docker public-API regression reproduced 409 instead of
200 for valid legacy-only Workspaces whose initialized repository contains only
manifests and has no index yet. The discovery guard was too broad.

The correction does not trust an empty index: a bounded, read-only accepted-Git
inventory must prove there are no Markdown files before legacy discovery can
proceed. Reconciliation recording is disabled. Missing/unreadable custody,
resource limits, stale content and the first unindexed native document remain
blocked. All nine focused discovery cases passed (71.64 seconds); the full
adapted authoring aggregate also passed, as did 158 tooling cases (three optional
skips), lint, types and both review axes. No schema, API shape, authority or retained data
changes are needed.

Extended 41551481488 separately failed WebKit job 125639887388 at
`document-operations.spec.ts:110`, waiting for Keep editing after browser Back.
Five serial and twenty concurrent unchanged replays passed locally with zero
retries; the surrounding eight-case operations suite also passed three times
(24 cases, 29.2 seconds). The original cause remains unknown. A failure-only, value-minimized history/dialog snapshot is retained if the
case recurs, without route identifiers, review text or response bodies. No
frontend assertion, timeout or retry setting is changed to conceal the failure. The failure ledger retains
both hosted failures. Corrected-source CI remains required.

## CI allocation correction

The initial Build also cancelled `core-a-2` job 125640023353 at its unchanged
30-minute deadline. Inserting the new discovery filename changed alphabetical
round-robin assignments for existing modules. A public selector regression
failed for all four groups before correction. Docker collection measured 393
cases in the failed allocation versus 298 in the restored allocation (19 modules
each), independently confirming the workload change rather than guessing from
the timeout. Collection did not provision a database or execute the tests.

The allocation fixture is captured from previously validated immutable source
`64bb580`, not generated from the modified selector. The new discovery module
is excluded before round-robin partitioning and appended to `core-a`/`core-a-1`
afterward. Existing modules keep their validated allocations; discovery executes
once in the split. All 11 planning/coverage checks and shell syntax pass; both
review axes are clear. No deadline, test assertion, retry policy, coverage
requirement, job or service was added or weakened. Hosted completion remains the
proof of capacity; no local parallel environment was created.

## Runtime headroom correction after `ddc7d4dd`

The allocation restoration alone was insufficient: Build 41556077294 cancelled
`core-a-2` job 125655990105 again at 30 minutes, with 144/298 cases reported.
Do not read the earlier restoration as a verified capacity closure. The sparse
progress log does not identify one causal slow test. The same source passed all
five browser configurations, CodeQL, performance, DAST, independent encrypted
recovery and the complete live application/publication journey; its remaining
Build failure is the database-group budget.

The third-group selector regression failed before implementation. The former
second branch is now divided into disjoint 10/9-module groups `core-a-2` and
`core-a-3`; `core-a-1` and its discovery tests stay unchanged. The independent
baseline fixture still proves the exact original family union. CI adds one
matrix entry and refuses combined coverage without all three outputs. The
80% aggregate requirement, per-test assertions/retries and 30-minute job deadline
remain unchanged. Existing module progress and duration diagnostics are retained
with increased verbosity. All twelve plan/coverage checks and both review axes
pass; full local selections and exact-source hosted completion establish runtime
headroom, not module counts alone. No application code, service configuration,
production system, retained data or local parallel environment changes are made
by this CI-only correction.

Full local execution of the new selectors, sequentially in the existing migrate
service with generated test databases and coverage, passed:

- `core-a-2`: 194 passed, two existing renderer-runtime skips, 393.64 seconds.
- `core-a-3`: 101 passed, one existing live-harness skip, 500.38 seconds.
- All 298 selected cases are retained across the disjoint groups.
- All 160 tooling cases passed (three optional tooling skips), as did POSIX shell
  syntax checks and both review axes. No full local matrix/parallel stack was
  provisioned. Hosted startup and execution still need to confirm headroom under
  the unchanged 30-minute job limit.

For application source `ddc7d4dd`, Extended validation 41556114578 and CodeQL
41556111917 both completed successfully on attempt 1. Upgrade and independent
recovery are green; backup receipt artifact 13196975710 was checked for exact
source/status/category, immutable identifier `41556114578:1:supported-recovery`,
and ZIP SHA-256 `94cc39769b1fa7b11571315d46db15bad65b3839fb00df54206b538a26d4206d`.
WebKit artifact 13195373116 reports all 415 cases passed with zero retries,
including the unchanged Back assertion. Its original failure cause remains
unknown. The following correction changes only CI selection/coverage collection
and diagnostics; the application code remains unchanged.


## Exact-source hosted closeout: November 2, 2026

Verified remote main is `b716026742e513c94dbaaf65a5c30a2cf8d2c3ce`.
Build 41562895300 and CodeQL 41562938749 passed attempt 1. All 20 database
groups passed; combined coverage is 89%. The split selections completed with
194 passed/two existing skips in 621.28 seconds and 101 passed/one existing skip
in 1185.70 seconds, under the unchanged 30-minute job deadline. Production
container builds and vulnerability scans passed; unchanged-version image
publication was correctly skipped.

Publication artifact 13198943550 reports all ten cases passed with zero retries,
including native library discovery/reopening; server verification passed. ZIP
SHA-256 is `9dff75a60e231271e4e8f006ca3d79ce78eb4be7e2558291973b974a56927ccb`.
Current WebKit artifact 13197214521 reports 411 passed, four existing skips and
zero retries; the unchanged Back assertion passed.

Extended 41562941477 passed on attempt 2. Preserve attempt 1: the diagram
upgrade fixture's first Git publication raised a generic required-render error.
Cause remains unknown because the underlying caught I/O/value/JSON detail and
renderer diagnostics were not retained. The unchanged exact fixture replay
passed in Docker (68.42 seconds), all 34 diagram-migration cases passed
(150.68 seconds), and 100 required renders of the three synthetic fixture variants
passed. Attempt 2 reran the failed hosted jobs on identical source; every upgrade
stage passed. This is a successful retest, not evidence of a renderer code fix.

Downloaded receipts all report passed and the exact source above:

- Recovery artifact 13199226082, `41562941477:1:supported-recovery`, ZIP SHA-256
  `43a2b599c5fb913dc7cad497342427068ffde2f0055fcd82cd262e3c514ea5bc`.
- Upgrade artifact 13201899400, `41562941477:2:supported-upgrades`, ZIP SHA-256
  `0e80cf60b8a6878baacd088db1861f1a17698b50118452f421a7f6523b959cf4`.
- Diagram artifact 13202308307, `41562941477:2:diagram-upgrade+restore`, ZIP SHA-256
  `7ffc0338bb6b966e9342fc4c140d6d33568423a08632317b91bf305f937a686b`.

No production inspection/deployment, actual document export, retained data or
schema change occurred. Earlier user-owned planning changes remain local.
These closeout evidence updates are local and do not change validated source.
The original diagram and WebKit failure causes remain unknown; all required
hosted gates are now verified passing. No aggregate 1.0 acceptance is claimed.
