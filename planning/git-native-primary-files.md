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

## Hosted service-contract regression and correction

Initial main push `dbd55ae2ffd3b833233fd0908569045597bcf474` failed Build
41672338029, core-b job 126044144090. Its existing
`test_copied_legacy_document_cannot_acquire_native_file_owner` expected the
service's DRF ValidationError contract, while the new authority guard raised a
plain RepositoryPrimaryFileConflict. The exact existing Docker test reproduced
that failure before correction (`/tmp/tekdocs-primary-owner-red.log`). The guard
still denied ownership; the regression was its exception compatibility, not a
permitted upload. The focused initial local suite had omitted this owner module.

RepositoryPrimaryFileConflict now specializes the existing ValidationError
contract; HTTP adapters still catch that specific class and return 409. A first
corrected run passed all 62 ownership/authoring/file-migration cases. Review then
identified the changed DRF string representation. New exact HTTP-detail
assertions reproduced both list-style conflict messages before their correction
(`/tmp/tekdocs-primary-message-red.log`). The specialized exception now retains
plain message formatting. Neither the original owner assertion nor authority,
CAS, scanner, storage or recovery checks were relaxed. The final full three-module
run passed all 62 cases, including exact plain conflict messages and the original
owner denial. Ruff and mypy passed; both final review axes have zero findings.
Final-source hosted validation remains required after the correction push.

## Final exact-source delivery — November 3, 2026

Verified: remote main is `61908a2c7679b42c044bd75e0050094b10f2be23` (feature `dbd55ae2`,
service-contract correction `61908a2c`).
[Build 41677910926](https://github.com/hkrewson/TekDocs/actions/runs/41677910926)
passed attempt 2, [CodeQL 41677944767](https://github.com/hkrewson/TekDocs/actions/runs/41677944767)
passed attempt 1 and [Extended 41677948851](https://github.com/hkrewson/TekDocs/actions/runs/41677948851)
passed attempt 2. All twenty PostgreSQL groups and combined coverage passed,
including the previously failing owner contract in core-b. Production images,
diagram path, SBOM and vulnerability checks passed. Supported upgrades and
independent encrypted restore passed on final source; the restore log explicitly
confirms native publication lineage, signatures, PDFs and primary-file versions
restored exactly. These test fixtures contain three live native primary versions
and independently retained publication copies.

The final hosted browser artifact has thirteen passed cases, every retry zero
and server verification passed. The unchanged final-source local replay also
passed all thirteen cases in 4.2 minutes, zero retries, plus server retained-byte
and authority verification (`/tmp/tekdocs-primary-hosted-live-replay.log`). Final
WebKit has 411 passed, four existing skips and zero retries, including the original
1280px draft-protection case. Both source-review axes have zero remaining findings.

Build attempt 1's existing template-copy case timed out with a Git document read
pending for 2,954 ms. The new native staff/client/primary cases and twelve of
thirteen browser cases passed in that unsuccessful attempt. Extended attempt 1
failed the existing WebKit discard dialog at 1280px (410 passed, one failed, four
existing skips). Exact unchanged WebKit replay passed in 6.2s; twenty four-worker
replays passed in 45.3s and all eighteen surrounding cases passed in 20.7s, without
retries. No selector, assertion, timeout, retry budget or source was changed for
either hosted retry. Their causes remain unknown. The original failed artifacts
13253698105 (SHA-256 702f20a2d0649d51edae0c115cb2d927c6be6983350dc39c75d6ad9484723ae7)
and 13251819531 (SHA-256 2ea314de76da6d95fd2550ecb4118c238c7ee39618fea782f28d2c3f1243ff0c)
are retained locally and verified. The failure ledger retains each attempt.

Inferred: passing unchanged replays establish their tested outcome, not a causal
fix for the recurring template read latency or WebKit dialog absence. Investigate
these timings before aggregate 1.0 acceptance; they are not silently declared
fixed by this bounded feature slice.
Blocked: no remaining validation blocker for primary-file controls. Native
configuration and aggregate clean-start/operator acceptance remain separate.
The earlier dbd55ae2 Build/Extended runs were cancelled as superseded after the
contract correction; their whole workflows are not reported as passing.

Downloaded evidence, source scope, status and GitHub ZIP digests were verified:

| Evidence | Artifact ID | SHA-256 |
| --- | --- | --- |
| CodeQL | 13252550422 | dd6f45816b4b7db0abd6210c4092888cd621d8726ff5ff1ad03cc2152c060f8a |
| Publication browser, Build attempt 2 | 13257196697 | 63749a36fcadff314b3c8be1cf228ae54a5cdb578e8bf0e06727fef3a5183bde |
| Independent restore | 13254502068 | bf2eda89f79db96f21c854f9b8d910113286d95816f65f92fc9454659ffdcfd5 |
| Supported upgrades | 13255417785 | dddd5953f66d4d03a93eeab7d9665cf76600451cb272090d5bb7762114bd5409 |
| Diagram upgrade/restore | 13255442509 | 430ba789a6165e0cfa138deb836a82264cd2f7474b9ac3967d323663538fe6ab |
| WebKit, Extended attempt 2 | 13256797126 | da40b9a44b3e72ea2d103c54a51cb0bc0f70eee7b5a9048d8750827de385b620 |

Immutable receipt identifiers match final source:
`41677944767:1:python+javascript-typescript`,
`41677948851:1:supported-recovery`, `41677948851:1:supported-upgrades`,
`41677948851:1:diagram-upgrade+restore`. Browser summaries bind to Build attempt 2
and Extended's unchanged WebKit attempt 2. Existing security risk/remediation
records remain unchanged; no new release candidate or risk acceptance is claimed.

Version remains 0.9.18 development. No deployment, production access, actual
document export, retained-data change or release/tag publication occurred. No
migration was applied to retained development records. The six optional migration
gaps stay deferred. Existing unrelated planning edits were preserved. Wiki edits
remain a local draft. This evidence addendum and status closeout remain local
post-push records; immutable hosted artifacts bind the delivered source without
creating another source-validation loop.
