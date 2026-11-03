# Native field/content keys and entity references

Bounded 1.0 native configuration slice after primary files at `61908a2c`.
The maintainer authorizes implementation, publication freezing, browser/isolation/
recovery validation, and direct-main commit/push after validation. Existing data
must not change. Version remains 0.9.18 development; no deployment, export of real
documents, automatic migration, template enrollment or monitored-source setup.

Acceptance:

- A freshly authored Git-only document can declare and retire field/content
  bindings and insert entity references through the interface without a legacy
  Document or Block row being created to unlock the workflow.
- Git frontmatter is authoritative. Protected authoring uses the existing exact
  base commit/blob comparison; drafts survive denials/conflicts. Existing promoted
  legacy binding configuration remains read-only.
- Reuse central authorization, exact Workspace boundaries, field sensitivity,
  inert scalar substitution, nested content expansion/cycle/size limits and
  explicit unavailable/withheld states. Native content keys target accepted Git
  native fragments; cross-Workspace bindings are refused. Legacy Block-backed
  fragment and entity identities are excluded from new native bindings, including
  copied, promoted, rolled-back and archived sources. Existing legacy workflows
  retain their own authorization and remain unchanged.
- Signed publications retain exact frozen values, entity cards and fragment
  source proof, PDFs and files. Later record, fragment or binding edits cannot
  alter earlier signed output. Older evidence and publication formats stay valid.
- Prove allow/deny/cross-client/cross-tenant and portal boundaries, malformed,
  missing, archived, cyclic and stale-index behavior; publication fails closed.
- Exercise new documents and fragments through real browser controls and carry
  the fixture through maintained independent recovery. Preserve populated-schema
  rollback guards. Use the single existing tekdocs Compose project locally with
  separate synthetic test databases; isolated upgrade/restore stacks stay in CI.
- Align OpenAPI, types, architecture, Wiki draft, roadmap/release status and both
  source reviews. Preserve unrelated planning edits and commit only this slice.

Source audit findings are hypotheses until targeted Docker reproductions run.
Existing intermittent template-read/WebKit timing failures remain recorded;
this slice does not claim to have diagnosed or fixed them.

## Verification record

Verified locally in the existing Docker project:

- Initial exact service tests reproduced rejected native binding metadata and
  unavailable native publication keys before implementation. The corresponding
  native authoring/publication cases now pass, including v3 evidence verification.
- A nested-content DOCX reproduction omitted expanded text; the reader/PDF/DOCX
  adapter now shares the expanded saved body and the exact DOCX regression passes.
- The new interface-control reproduction initially lacked Keys and references.
  Final frontend validation passes 868 tests, coverage, lint/types, API types and
  production bundle budgets. The 42 editor cases include denied/conflicting saves,
  guarded reload, unfinished names, read-only state, retries and binding retirement.
- Static Python checks and migration-state generation pass; Bandit reports zero
  findings. Language/responsive/product-boundary, version/pin, Wiki and 160
  tooling cases (three opt-in skips) pass. Existing OpenAPI warnings remain four.
- Initial source reviews were clear; subsequent focused review found the legacy
  fragment identity bypass described below. Final review also identified a
  browser setup omission: retained-publication PDF download requires an explicit
  publication decision after snapshot retention. That decision was added without
  changing selectors, assertions, retries or time budgets.
- The exact populated rollback test passes and preserves FORCE RLS, signed
  manifests/PDFs and file versions. The maintained independent recovery fixture now
  includes current retargeted Git bindings/fragment source as well as older signed
  field/content values and entity references. Full isolated restore is hosted-only.

- The first combined backend run passed 329 cases and exposed one changed error
  contract (`repository.key.unavailable`). Restoring that contract passed its
  exact regression plus six negative/native cases. The subsequent authoring gate
  passed 189 cases before the final permissions fix.
- The first full browser run passed 12 of 14 journeys. Exact-label reproduction
  showed nested select-option text contaminating the field-key label. Explicit
  label/control association fixes the product; selectors, retries and budgets
  remain unchanged. The 42 editor regressions pass after that correction.
- `test_native_publication_cannot_bypass_legacy_block_policy[fragment-copied]`
  reproduced a copied staff-private legacy Block frozen into client evidence.
  New native bindings now reject legacy Block IDs and their Entity IDs in
  discovery, protected writes, live expansion and publication. Eight publication/
  live-read cases and four discovery/write cases cover copied, promoted,
  rolled-back and archived sources. Genuine native fragments remain supported.
- `test_native_key_database_guard_rejects_a_legacy_fragment_disguised_as_native`
  reproduced acceptance by the old SQL guard with only the Python identity
  adapter bypassed. Migration 0220 now independently rejects these identities.
  The final fresh-schema authoring gate passes all 202 cases, including all 13
  legacy-identity regressions. The populated rollback/custody regression passes.
  Both final source-review axes report zero unresolved findings.

All 14 real-browser journeys and server verification passed without retries.
Local validation and both source reviews are complete; exact-source hosted
Build, CodeQL and Extended validation (including independent restore and supported
upgrade evidence) remain required after the authorized direct-main push. No existing-data migration has occurred. Test logs use
synthetic records; private session IPC is not retained or uploaded.

The full source-secret scan reproduced four stale exact-line exclusions for
unchanged permission-route metadata. Updating only those four reviewed line
fingerprints preserves the narrow exclusions. Both full-source and changed-file
scans pass after this correction.
The first frontend command mistakenly requested a nonexistent `test:coverage`
script; the corrected existing `npm test` command passed all 868 tests and coverage,
followed by production build/bundle checks. This was a command error, not a product
or test failure. Local scans, static checks and runtime tests use the existing
services; the first source-scan wrapper invoked its ephemeral scanner container
before its implementation was inspected. Subsequent scans were adapted to the
existing migrate service; no additional data volume or database was created.
