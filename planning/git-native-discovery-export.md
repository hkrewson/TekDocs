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
