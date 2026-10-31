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
remains separate, following the recommended field-key scope in the clarification; no broader scope was authorized. General cross-Workspace reuse,
client delivery, diagrams and monitored sources are separate slices. No version
bump, release publication, Wiki push, production deployment or live migration is
included.

Use only the existing local `tekdocs` services with a separate test database;
independent-stack gates remain hosted-only. Tests cross the migration operations,
publication/read/download HTTP interfaces, real browser journey and supported
upgrade/recovery fixtures. Source review compares with starting commit `802d484`.

Status: implementation, source review and local validation complete. Exact-source
hosted validation is pending. Earlier template receipts do not validate this source.


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

Verified locally so far: both real-browser journeys plus constrained HTTP role,
server-side immutable-byte verification and authority rollback/re-promotion;
18 responsive keyboard/retry/axe cases across Chromium/Firefox/WebKit at six
widths; 778 frontend tests; lint/types/build and compressed budgets; 288 backend
sources pass mypy, Ruff and schema drift; 128 script tests pass (three opt-in
checks skipped). OpenAPI generated with four preexisting operation-ID warnings,
zero errors. Frontend audit has six existing low findings, no moderate/high/
critical findings; dependency license policy passes. No new dependency added.

The complete local migration regression passed (311 cases). Independent fresh/0.8.46 upgrade
and encrypted backup/restore remain hosted-only under the single-project rule.
No exact-source hosted pass or production change is claimed yet.


Additional risk disposition: the pinned application requirements audit is clean
and Bandit reports no issues. The installed development environment audit found
preexisting filelock/msgpack/setuptools advisories; the [tooling observation](../releases/key-entity-tooling-audit.md)
records the open follow-up, distinct from runtime scanning. It is not an accepted
exception or a clean-toolchain claim. Independent local image/secret scanner
containers are not started under the single-project rule; hosted gates must
confirm source/image scanning at the exact pushed commit.


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
  Build and Extended validation must establish those at the exact pushed source.
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

Verified so far: all fourteen PostgreSQL partitions, **70 key/entity cases**,
**89% merged backend coverage**, frontend tests, runtime/RLS, code/dependency/
secret policy, diagram exports and the hosted real browser/server journeys passed.
CodeQL and its downloaded commit-bound receipt passed. The encrypted-recovery
rehearsal step passed; broader recovery, supported upgrades and final image gates
are still in progress. This is not yet a passing aggregate receipt.

Extended attempt 1 failed one existing WebKit document-settings draft-protection
case at 1024px (missing unsaved-changes dialog). Its other **410 cases passed**,
including all six new Keys cases; four opt-in cases were skipped. Cause remains
**unknown**. The unchanged case passed 40 development-server repetitions and 30
repetitions against a fresh production bundle using the CI browser configuration.
A complete unchanged production-build WebKit run is also in progress locally.
No behavior, selector, assertion, timeout or retry setting changed. GitHub rejects
a job rerun while the parent workflow is running; retry the failed job once the
remaining workflow jobs finish. The original run and observation remain in
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
timeout or retry setting changed. The new exact-source hosted replay must cover
both the corrected fixture and the unchanged WebKit journey. Earlier receipts
remain supporting evidence and cannot validate the corrective source by themselves.
