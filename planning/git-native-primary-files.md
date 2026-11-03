# Git-native primary-file version controls

Bounded 1.0 daily-work slice following native publication at `a598cf00`.
The maintainer authorizes primary-file controls for newly created Git documents,
retaining every file version and signed publication, browser/recovery validation,
and direct-main delivery after validation. Existing data must remain unchanged.
No legacy migration, keys/templates/monitoring setup, release bump or deployment
is included.

Acceptance:

- A UI-created Git-only MSP or client document can upload its first primary file,
  replace it explicitly, list paged current/history versions, and download exact
  retained bytes without creating a legacy Document.
- Reuse existing scanned intake, exact-Workspace authorization, compare-and-swap,
  immutable version lineage and download integrity checks. Do not duplicate
  custody or introduce another file authority.
- Stale-current replacement never overwrites a version or retries automatically.
  A chosen file and Markdown drafts survive denial/conflict; refresh requires
  explicit review of any changed replacement target. Navigation and in-flight
  operations are protected; fragments/unsaved/stale source cannot upload.
- Signed evidence/PDFs and file-version sets frozen before replacement remain
  intact. Browser acceptance verifies original and replacement bytes, conflicts,
  authorization and publication preservation on freshly authored Git documents.
- Recovery retains live versions and independently copied signed publication
  artifacts, including an upload after a publication. Existing immutable history
  and populated-schema rollback safeguards remain unchanged.
- Validate in the single existing tekdocs Docker project with generated separate
  test databases. Leave isolated stack-based upgrade/restore gates to hosted CI.
  Required source reviews, API/schema alignment, architecture/release notes and
  Wiki draft accompany the slice. Preserve unrelated planning edits.

Version remains 0.9.18 development. No existing data, production access or
operator exports are authorized. Exact-source CI supplies final upgrade and
independent recovery evidence after the approved push.

Review found a compatibility defect in the pre-existing primary history route:
it returned zero for a promoted, legacy-owned two-version chain even though the
append service correctly saw the current predecessor. The existing file-backed
rollback test reproduced `count == 0`, expected 2, before runtime correction.
The route now includes exact authorized promoted owners; a shared read/append
authority guard refuses legacy-authoritative shadows with 409. Regression covers
history/current flags, native append against the retained predecessor, signed
publication files and downloads across repository/legacy rollback. This is a
bounded compatibility correction, not another migration project or data rewrite.

## Reproduction and current validation

- Existing Docker UI regression `offers primary-file version controls for a saved
  Git-only document` failed before implementation: no Primary file versions
  button (1.04 seconds). The same test now passes.
- Existing Docker API checks passed five primary-file/CAS/scope/signed-portal
  cases before connecting the interface. The compatibility regression later
  reproduced a promoted two-version history reported as zero, before correction.
- The corrected compatibility case plus native MSP/client primary API cases passed.
  The native scanner rejection check confirms no added version and an unchanged
  current pointer. Compatibility coverage adds the third version against its
  retained predecessor, verifies publication files, and downloads it after both
  authority rollback directions while retaining the original signature/PDF.
- Three extended recovery/concurrency cases passed locally: three live native
  versions, independently retained signed publication copies, post-publication
  upload, later-head independence, corruption detection and concurrent correction.
- Full Docker frontend lint, 849 tests, coverage, types and bundle limits passed.
  Coverage: 78.34% statements, 73.88% branches, 72.73% functions, 85.17% lines.
  Ten privacy-diagnostics cases passed on the updated script, including primary
  intake/download phases without filenames, IDs, request bodies or credentials.
- Full backend Ruff and mypy across 302 files passed. No migration changes are
  detected. OpenAPI regeneration has zero errors and four existing operation-ID
  warnings; existing conflict outcomes are documented and generated types updated.
- Both Spec and Standards reviews report zero remaining findings after correction.
  The final combined Docker authoring gate passed all 196 cases, including the
  complete file-backed publication migration module. The final clean real
  browser/server gate passed all thirteen journeys in 4.2 minutes, zero retries,
  plus retained-byte/authority verification and artifact hygiene.

The isolated full upgrade/restore stacks remain hosted-only under the single
local project rule. The maintained encrypted-recovery fixture now fingerprints
all three native versions as well as signed publication files/PDFs and decision
history. No retained development database migration has been applied, no real
documents exported, no production access performed and no existing data changed.

## Browser failure reproduction and correction

The first new-document browser run passed all file/CAS/download/denial steps but
waited for primary controls after reload. A pre-fix boolean route assertion then
reproduced the cause: the current creation URL had no repository selection even
though its editor was open. The journey now navigates to the returned canonical
selection path, verifies its selection and saved Markdown, then keeps the
original reload/history assertions. No runtime route behavior was changed.

The next full run passed reload and failed its immediate 390-pixel overflow
check. A diagnostic run measured the existing sidebar transition: an immediate
244-pixel margin gave 523-pixel scroll width; settled margin zero gave 390-pixel
scroll width. All thirteen journeys and server verification passed that probe.
The final journey uses the existing shell margin-zero condition before the same
no-overflow assertion. Temporary metrics were removed. No CSS, selector, timeout,
retry budget or acceptance comparison was weakened. Unsuccessful logs are
retained locally as `tekdocs-primary-browser-final.log`,
`tekdocs-primary-browser-selection-red.log`,
`tekdocs-primary-browser-complete.log` and
`tekdocs-primary-browser-layout-probe.log` under `/tmp/`.

Final frontend lint, types and ten privacy diagnostics passed after the contract
and fixed diagnostic phase labels were updated. Both final review axes remain
clear. Existing security risk/remediation records remain unchanged; this is
bounded development delivery, not a new release candidate or risk acceptance.

Verified locally: the clean final browser gate is recorded at
`/tmp/tekdocs-primary-browser-clean-final.log`; its safe summary reports all
thirteen tests passed, every retry zero and server verification passed. The
single-project Docker checks establish this bounded workflow; full independent
encrypted restore and supported upgrades remain hosted-only gates after push.
Inferred: no further causal claim is made for timing behavior outside the
reproduced route-selection and measured sidebar-transition failures above.
Blocked: no local blocker remains; exact-source hosted validation is outstanding.
The public Wiki change is a local Documentation draft, not separately published.
