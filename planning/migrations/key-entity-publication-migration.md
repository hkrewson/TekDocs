# Key and entity-reference publication migration

Bounded #105/#106 continuation from `802d484`, authorized October 31, 2026.
The template runtime `4bb6bdd` has complete matched hosted validation. This
slice preserves document bindings and permission-aware record references through
Git authority, immutable publishing, rollback and recovery.

Acceptance and agreed testing interfaces:

- Existing migration prepare/apply/authority operations preserve binding identity,
  source expressions, typed references, signed history, files and retained PDFs.
- Live reads resolve permitted current values; a new publication freezes exactly
  the values and entity cards it renders, with signed provenance. Later edits,
  archival or loss of live source custody do not rewrite retained publications.
- Publication readiness and creation reject missing, denied, foreign or stale
  binding/reference inputs without partial SQL, Git or artifact changes.
- Existing publication/read/download HTTP interfaces and real browser workflows
  exercise successful and denied operation. Runtime-role, cross-client and
  cross-tenant checks retain central policy and exact Workspace boundaries.
- Fresh/upgraded migration, normal reversible Django migrations, rollback and
  encrypted recovery agree with offline signature and retained-byte verification.
- API contracts, architecture/roadmap, development notes, Wiki draft and recurring
  risk ownership agree before source review and the authorized direct-main push.

First vertical: field keys and exact-Workspace entity mentions on documents with
retained internal/permanent publication history. Content-key block substitution
remains separate under the recommended field-key scope; broader scope was not
authorized. General cross-Workspace reuse,
client delivery, diagrams and monitored sources are separate slices. No version
bump, release publication, Wiki push, production deployment or live migration is
included.

Use only the existing local `tekdocs` services with a separate test database;
independent-stack gates remain hosted-only. Tests cross the migration operations,
publication/read/download HTTP interfaces, real browser journey and supported
upgrade/recovery fixtures. Source review compares with starting commit `802d484`.

Status: the bounded slice is validated at exact runtime source
`6ce9519eed92ff216a30582207692762ab503fd0`. Implementation, source review, local
Docker/browser validation and all required hosted gates passed. The final receipt
below supersedes earlier preparation status; no production acceptance is inferred.


Reproduced failures during acceptance (before source review):

- New-client manifest synchronization advanced a previously indexed MSP Git HEAD
  without updating its content projection. The real browser lost the migrated
  reader; the focused cross-Workspace fixture reproduced `RepositoryContentNotIndexed`.
  Metadata-only synchronization now reindexes only repositories that were current
  before the change; an already stale index remains blocked. Focused reader and
  current-key HTTP readiness checks passed (four cases).
- The new independent browser test had no confirmation-dialog handler, so its
  publication click was dismissed and no request was sent. It now accepts the
  existing user confirmation like the original journey; no timeout or assertion
  was weakened. Both complete journeys and server verification subsequently passed.


Source review used the code-review skill's independent Standards and Spec axes
against `802d484`, including untracked files. Both reviewers found the binding
handoff race. Four two-connection cases reproduced archive/insert crossing an
uncommitted promotion (MSP/client). The SQL guard now locks old/new owners in
identity order; API mutation transactions lock the owner before checking authority.
The same four cases passed after correction. A proposed missing/null-kind SQL
bypass did not reproduce: inherited v3 guards already require the key and string
type; four passing negatives remain, with no speculative 0207 change. Final
Standards and Spec re-reviews report zero remaining findings.

Verified locally: both real-browser journeys plus constrained HTTP role,
server-side immutable-byte verification and authority rollback/re-promotion;
18 responsive keyboard/retry/axe cases across Chromium/Firefox/WebKit at six
widths; 778 frontend tests; lint/types/build and compressed budgets; 288 backend
sources pass mypy, Ruff and schema drift; 128 script tests pass (three opt-in
checks skipped). OpenAPI generated with four preexisting operation-ID warnings,
zero errors. Frontend audit has six existing low findings, no moderate/high/
critical findings; dependency license policy passes. No new dependency added.

The complete local migration regression passed (311 cases). Independent fresh/0.8.46 upgrade
and encrypted backup/restore remain hosted-only under the single-project rule.
The final hosted receipt below supplies the independent-stack evidence. No
production change is claimed.


Additional risk disposition: the pinned application requirements audit is clean
and Bandit reports no issues. The installed development environment audit found
preexisting filelock/msgpack/setuptools advisories; the [tooling observation](../releases/key-entity-tooling-audit.md)
records the open follow-up, distinct from runtime scanning. It is not an accepted
exception or a clean-toolchain claim. Independent local image/secret scanner
containers were not started under the single-project rule; the final hosted
source/image gates passed at the exact source recorded below.


The complete Docker `test-document-migration-inventory` selection, adapted from
`compose run` to `compose exec` on the existing migrate service, passed all
**311 cases**. The final API/evidence selection initially had one new negative
fixture failure: it used an Organization's directory Entity as a foreign record.
A dedicated ownership assertion reproduced that this anchor belongs to the MSP
Workspace, as `create_organization` specifies. The fixture now creates a Site
inside another client Workspace and asserts that ownership before testing denial.
No production behavior or rejection assertion was weakened. The focused API,
key and repository-evidence selection passed all 95 cases with that corrected fixture.


## Final local validation and source preparation

- **Verified:** 311 migration-gate cases; 95 key/API/evidence cases; 778 frontend
  tests; 18 new Keys browser cases plus 69 publication/template browser regressions
  across three engines; both final real-browser journeys and server verification.
  These establish preserved signed publications/PDFs/file versions, current-value
  versus frozen-value behavior, offline verification, guarded rollback/re-promotion,
  concurrent binding serialization and fail-closed scope/permission behavior.
- **Verified:** Ruff, mypy (288 sources), schema drift, validated OpenAPI/generated
  client, frontend lint/types/build/budgets, 128 script tests (three opt-in skips),
  Compose contracts, Wiki links, version/pin/product/language/responsive contracts,
  Bandit, runtime requirements audit and frontend dependency/license policy.
- **Verified:** shared hosted mode adapters reject mismatched fingerprints and
  verify exact retained data locally; corrupted retained PDF is rejected and exact
  repair restores verification. Schema guards reverse and reapply to migration head.
- **Blocked locally by repository policy:** independent fresh/0.8.46 upgrade and
  encrypted source/restore stacks, independent image and secret-scanner containers.
  Final Build and Extended validation supplied those results at the exact source
  recorded below.
- **Inferred only:** local results support the bounded development contract; they
  do not establish production acceptance, a new release or aggregate 1.0 readiness.

Named reproductions: `test_addressed_fixture_cannot_revert_another_promoted_document`
(index coherence), `test_binding_writer_cannot_cross_an_uncommitted_authority_handoff`
(two-connection binding race), `test_sql_rejects_unbound_or_mismatched_addressed_proof`
(SQL negatives), and `test_migration_rejects_missing_or_foreign_record_mentions_without_partial_import`
(corrected exact-Workspace negative fixture). The browser confirmation omission
was in the new independent live test; its correction preserves existing checks
and time limits. [Source review](../releases/key-entity-source-review.md) records
zero remaining findings on both axes.

Version remains 0.9.16. The Wiki draft is local and unpublished; unrelated Wiki
edits and ignored AGENTS instructions are preserved. No branch/PR, release tag,
image publication, SSH, deployment or live-data migration is part of this slice.

## Hosted source attempt `3ae5ed8`

Runtime source: `3ae5ed8abae015ccbf83df4d9f771048148a7f44`, pushed directly to
main after the complete local validation and both source-review axes passed.
[Build 41181865875](https://github.com/hkrewson/TekDocs/actions/runs/41181865875),
[CodeQL 41181874058](https://github.com/hkrewson/TekDocs/actions/runs/41181874058)
and [Extended 41181875866](https://github.com/hkrewson/TekDocs/actions/runs/41181875866)
all name that exact source.

The completed Build verified all fourteen PostgreSQL partitions, **70 key/entity cases**,
**89% merged backend coverage**, frontend tests, runtime/RLS, code/dependency/
secret policy, diagram exports and the hosted real browser/server journeys.
CodeQL and its downloaded commit-bound receipt passed. The complete recovery
and image gates passed. Extended later failed during the
document-migration rehearsal as recorded below; this attempt is not a passing
aggregate receipt.

Extended attempt 1 failed one existing WebKit document-settings draft-protection
case at 1024px (missing unsaved-changes dialog). Its other **410 cases passed**,
including all six new Keys cases; four opt-in cases were skipped. Cause remains
**unknown**. The unchanged case passed 40 development-server repetitions and 30
repetitions against a fresh production bundle using the CI browser configuration.
A complete unchanged production-build WebKit run subsequently passed 410 cases;
its separate backend-health limitation is recorded below.
No behavior, selector, assertion, timeout or retry setting changed. GitHub
rejected a job rerun while the parent workflow was running. The subsequent MFA
fixture correction required a new exact-source replay instead. The original run and observation remain in
`planning/releases/validation-failures.json`; passing a retry must not be called
a demonstrated fix or a known cause.


## Corrective validation-fixture preparation

Source `3ae5ed8` completed Build and CodeQL successfully, including all fourteen
PostgreSQL partitions, **70 key/entity cases**, **89% coverage**, real browser/
server verification and production image/SBOM/vulnerability policy. Extended
verified exact addressed-document encrypted recovery and its remaining recovery
checks, all eight historical upgrade paths, performance, DAST and four browser
groups. It is **not** an aggregate pass: WebKit failed as recorded above, and the
subsequent fresh/0.8.46 document-migration step hit duplicate owner MFA enrollment.

The actual original `create` fixture, addressed seed, and original `exercise`
entrypoint reproduced the same `unique_authenticator_type` error in the existing
Docker test database. Both stages now call one test-only `ensure_fixture_mfa`
operation, creating TOTP only when absent. Existing factor identity and data are
preserved by two database regressions. The complete original exercise followed
by addressed promotion passed in **36.47 seconds**. The successful local probe
explicitly loaded bound source via `PYTHONPATH=/app`; an earlier probe had loaded
the installed image's older helper. No application MFA policy or validation
threshold changed. The candidate-only exercise import leaves baseline seeding
compatible with 0.8.46. Both source-review axes found no code issue in this delta.

The full unchanged local production WebKit run passed **410 cases**, including
the originally failing case. Its only failure was the real backend-health probe:
HTTP502 from the preview proxy, with the backend service verified stopped. It is
an explicitly limited reproduction, not a complete passing browser receipt.
All **70** unchanged targeted repetitions also passed. The original hosted
unsaved-dialog cause remains **unknown**; no UI behavior, selector, assertion,
timeout or retry setting changed. The final exact-source hosted replay covered
both the corrected fixture and the unchanged WebKit journey. Earlier receipts
remain supporting evidence and cannot validate the corrective source by themselves.


## Corrective exact-source replay `6ce9519` (completed)

Source `6ce9519eed92ff216a30582207692762ab503fd0` contains the test-only MFA
preparation correction. The fresh [Build](https://github.com/hkrewson/TekDocs/actions/runs/41185521728),
[CodeQL](https://github.com/hkrewson/TekDocs/actions/runs/41185526785) and
[Extended](https://github.com/hkrewson/TekDocs/actions/runs/41185528840) runs all
name this exact commit. CodeQL and its downloaded receipt passed; the key/entity
partition passed **72 cases**. Hosted WebKit passed **411 cases** with four opt-in
skips. Frontend source and the draft-protection assertion are unchanged from
`3ae5ed8`, so this is a successful retest, not evidence that MFA preparation
explains or fixes the original UI failure. Its cause remains unknown in the ledger.
All Build and Extended data/image gates subsequently passed; the complete
receipt follows.


## Final validation and closeout — October 31, 2026

**Verified:** exact runtime source `6ce9519eed92ff216a30582207692762ab503fd0`
passed all required hosted workflows:

| Gate | Exact-source receipt | Result |
| --- | --- | --- |
| Build, test, and secure | [41185521728](https://github.com/hkrewson/TekDocs/actions/runs/41185521728) | All fourteen PostgreSQL partitions, 72 key/entity cases, 89% merged backend coverage, frontend, constrained HTTP/browser acceptance, diagram exports and production images/SBOM/vulnerability policy passed. |
| CodeQL | [41185526785](https://github.com/hkrewson/TekDocs/actions/runs/41185526785) | Both languages and downloaded commit-bound evidence passed. |
| Extended validation | [41185528840](https://github.com/hkrewson/TekDocs/actions/runs/41185528840) | All five browser groups, DAST, performance, eight supported historical upgrade paths, fresh/0.8.46 migration, versioned diagram upgrade, independent encrypted recovery and evidence delivery passed. |

The final upgrade logs confirm addressed Git, bindings, every fixture file version,
signatures and PDFs on both fresh and 0.8.46-upgraded data. The recovery logs
confirm these same retained inputs recovered exactly. The shared owner MFA factor
is preserved rather than duplicated. The real hosted publication journeys passed
with server-side custody verification and authority rollback/re-promotion; the
template apply acknowledgement was 8590 ms. CodeQL, browser and upgrade evidence
JSON files were downloaded and their `scope_commit` and passed status verified.

**Inferred only:** this validates the bounded development contract, not production
operator acceptance, a production deployment, client delivery, a new release or
aggregate 1.0 readiness. Version remains **0.9.16**.

**Blocked locally:** independent-stack gates remain prohibited by the single local
Compose-project rule. Hosted exact-source runs above supplied those results; no
required hosted gate remains pending for this runtime.

Both source-review axes reported zero remaining findings. Original failures,
reproductions and the MFA correction remain in the failure ledger. The earlier
WebKit draft-dialog cause remains **unknown**, despite the later unchanged
frontend/test passing all 411 hosted cases. No assertion, selector, timeout or retry
was weakened. The existing development/build-tool advisories remain an open
follow-up before final 1.0 validation; no exception is accepted or extended here.

The required Wiki draft is local and unpublished in the separate checkout, with
pre-existing edits preserved. Ignored AGENTS instructions remain private. Later
evidence-only commits bind this receipt to runtime `6ce9519` and make no new
runtime claim.
