# 0.9.8 security closeout checklist

Snapshot: 2026-10-12. Owner: maintainer. Local review is in progress; nothing here dismisses hosted alerts or certifies the final candidate.

## Candidate rescan reconciliation — 2026-10-13

### Closeout refresh — 2026-10-14

The operator accepted the current state; this is not a claim that every manual
profile was executed. Candidate `74e62db` passed Build, both CodeQL languages,
and the entire Extended workflow. All nine hosted security-category artifacts
are collected locally. The browser-recovery follow-up changes the candidate,
so S5/S6 remain open until that exact commit has fresh evidence and source review.

Read-only scanner inspection found 282 open alerts, all observed on
`74e62dba72a640bce986f2617076acaa10114135`: 7 high, 127 medium, 148 unrated.
The high-rated source paths are unchanged from the previously reviewed candidate;
#313 remains the controlled NetBox domain-error branch, and #314 remains the
test-only lambda. These are scanner classifications, not 282 confirmed exploits.
No alert was dismissed and no scanner was suppressed.

Reviewed the intervening runtime delta: asset and revision paging retain the
same scoped query for both ID selection and row hydration; migration 0181's
named trigger suspension remains transaction-locked with rollback and runtime
immutability tests; offline restore preflight uses the invoking UID, while
runtime restore receives only the read-only repository archive, never the
decrypted-secret directory. The private host directory remains 0700. The new
router fallback does not change authorization, CSP, cookies, or network policy,
and never renders the thrown diagnostic or stack.

Hosted DAST on `74e62db` reports 62 PASS, 0 FAIL, 5 WARN, 0 IGNORE: suspicious
comments, public caching, inline-style CSP, modern application, and missing
COEP. Rechecked that the documented CSP/COEP compatibility posture is unchanged;
the existing operator-approved residual-risk dispositions under #38 still apply.
Their November 12 / next-candidate review boundary remains in force, including
fresh DAST and generated-bundle checks for the recovery-fix candidate. Passing
this scan does not close findings or replace the final security record.

### Approved, time-bounded release exceptions

On 2026-10-13 the sole operator explicitly approved retaining the existing
inline-style CSP allowance (`style-src 'unsafe-inline'`) and missing COEP header
as documented release exceptions under issue #38. Owner: maintainer. Review is
due **2026-11-12 or before the next candidate, whichever comes first**. Preserve
the scope and risk analysis in `phase-8-security-review.md`, recheck the repaired
candidate, and carry both exceptions into the final security record. This
approval accepts the documented residual risks; it does not eliminate them,
dismiss scanner alerts, waive other acceptance gates, or authorize deployment.

### Rescan observations

Read-only GitHub review of candidate `31daa14125a60dc3cbea86583abb1340fc3ecaee`
found **282 open alerts**, all observed on that commit: 7 high, 127 medium,
148 unrated. The unchanged count does not mean an unchanged set:

- **#198 fixed by CodeQL:** the broad NetBox `ValueError` disclosure is no longer
  reported. Its replacement **#313** flags the deliberately narrower
  `NetBoxReferenceError` branch at `integrations.py:1190`. Reviewed all constructors
  in `netbox_reconciliation.py`: messages are fixed domain guidance, with no SQL,
  transport body or interpolated provider identity. The existing three-case
  `test_netbox_adoption_error_boundary` verifies preservation of domain guidance
  and suppression of both malformed-identity and arbitrary internal `ValueError`
  diagnostics. Local disposition: retain the controlled domain branch; no
  demonstrated disclosure and no hosted dismissal.
- **#302 fixed by CodeQL:** the retained-attachment empty fallback was removed.
  Preserve its valid-empty-file control and three read-failure cases.
- **#314 new, unrated:** `test_remote_document_egress.py:26` wraps `SimpleNamespace`
  in a keyword-forwarding lambda for a mocked observation constructor. This is a
  test-only readability finding, not runtime exposure. Leave it as non-blocking
  maintenance rather than broaden the release fix into unrelated cleanup.
- The other **280 open alert identities** are the previously reviewed baseline
  identities. Existing detailed dispositions below remain applicable to their
  unchanged source paths. Counts describe scanner classifications, not 282
  confirmed vulnerabilities or completed fixes.

Extended run `38344716336` on this candidate passed all five browser projects
and passive DAST (62 pass, 5 warnings, 0 failures). The five warning categories
are unchanged: comments, public caching, inline-style CSP, modern application,
and missing COEP. The detailed scope and limitations remain in
`phase-8-security-review.md`; CSP/COEP residual-risk follow-ups are not silently
closed by a green scan. Recheck against the repaired candidate and include their
owner/review date in S6.

Seven hosted evidence fragments were downloaded and checked locally. The
assembler rejects closure because `upgrade`, `backup_and_restore`, and
`source_review` are missing. Repair work changes the candidate: evidence for
`31daa14` must not be relabeled as evidence for the subsequent fix commit.
See [candidate notes](0.9.8-candidate.md) and the
[operator acceptance workflow](0.9.8-operator-acceptance.md).

The older entries below are dated worktree/baseline history; statements that
hosted evidence is still on 0.9.7 describe those earlier checkpoints, not this
rescan. S5/S6 remain open.

## Fixed remaining work packages

- [x] S1 — Complete scoped egress/import/provider source review and local regressions: 77 import, 176 shared integration and 47 provider-specific checks pass. Live-provider assurance is not claimed; final-candidate reruns remain in S5.
- [x] S2 — Complete outbox, notification-email, webhook and remote-source dispatch/service review; run the combined operational regression gate. Local scope complete; final-candidate rerun remains in S5.
- [x] S3 — Complete scoped restore preflight review: secret and media archive structure, repository validation, and authentication/preflight-before-destruction ordering. Final whole-stack recovery remains in S5.
- [x] S4a — Inventory all open GitHub CodeQL alerts by rule and scanned commit.
- [x] S4b — Complete local dispositions for all 134 security-rated alerts, distinguishing fixture/domain messages from reproduced runtime disclosures and verifying fixes. Hosted rescan and final-candidate evidence remain in S5.
- [x] S4c — Locally classify all 148 quality alerts; fix and verify the retained-file defect and record intentional patterns and non-blocking cleanup below. Hosted rescan remains in S5.
- [ ] S5 — Select the final candidate commit, rerun required CI/scans/browser/production-image/upgrade/encrypted-recovery checks, and assemble all ten evidence categories.
- [ ] S6 — Complete the final security record with findings, retests and time-bounded exceptions. Existing CSP/COEP follow-ups must be rechecked; SQL hardening remains approved 1.x work.

No new feature work belongs in these packages. New concrete defects discovered inside them remain in scope. Hosted evidence currently describes v0.9.7, not the uncommitted 0.9.8 worktree. Publishing, deployment and alert dismissal remain separate actions.

## S5 execution order — 2026-10-12

Candidate preparation is now versioned `0.9.8`. Frontend verification and the
remaining readiness gates were rerun after the metadata change and pass; all
59 script tests and the full unpublished Wiki inventory pass. The staged
candidate secret scan is clean. See [candidate notes](0.9.8-candidate.md) for
the reviewed broader-directory scan matches and outstanding release gates.
Preparing this local commit does not authorize push, tag, Wiki publication or
deployment; S5/S6 and human acceptance remain open.

1. Run local readiness checks before freezing the candidate. These are worktree
   checks, not evidence for the current HEAD (`b987fe7`, version `0.9.7`).
2. Reconcile the intended candidate files and version metadata; exclude the
   unrelated `.ecc/` directory. Obtain explicit commit/push authorization before
   selecting and publishing the candidate. Do not tag it complete at this step.
3. On that exact commit, collect Build workflow evidence for
   `authorization_and_rls`, `dependency_license_secret`, `image_scan`, and
   `production_images_sbom_provenance`; collect both-language CodeQL evidence.
4. Run Extended validation on the same commit for `browser_security`, `dast`,
   `upgrade`, and `backup_and_restore`. This workflow is manual/scheduled, not
   triggered by an ordinary push. Avoid pushing another candidate during these
   runs: workflow concurrency cancels runs on the same ref.
5. Reconcile fresh scanner findings and final production configuration with the
   completed local review. Record commit-bound `source_review` evidence only
   after that review, then assemble the ten categories and complete S6. Passing
   CodeQL execution is not itself a disposition of its findings.

Documentation inventory reconciled locally: the unpublished Wiki checkout at
`/tmp/tekdocs-security-wiki.knUbQ8` preserves its four earlier edited pages and
now includes the 32 missing required guides, updated navigation, current
graphical-export guidance and historical migration/version caveats. A read-only
remote check confirmed `75ceee0f9705fb4189491f8593489737218fc061` remains the
remote HEAD; the expanded manual is not published. The full local check passes
for 37 required pages and 45 total guide pages (plus the sidebar).

Reproduced a validator defect: existing supplemental setup pages were rejected
as link destinations, while broken links inside those pages were not inspected.
The validator now accepts existing safe-named guide destinations and checks all
such pages without relaxing the required 37-page manifest. Six new regression
tests cover required inventory, valid supplemental links, broken supplemental
links, missing required pages, unknown/traversing targets, and extension/anchor
links; all 59 script tests pass. The application publication flag stays false.
This proves local inventory/link consistency, not a human walkthrough or final
release acceptance. Wiki publication remains a separately authorized action.

Local readiness result: `make check` passed the 758 frontend tests, API-client
drift, lint, types and production bundle, then reproduced a stale release-plan
assertion (expected two standalone performance runs, observed three). The
additional run is the intentional Git-content performance suite. The test now
requires the exact three performance commands, including latency enforcement,
while retaining the single sharded backend boundary and no duplicate full-suite
checks. All 53 script tests pass. `make -o check-frontend check` then passed the
remaining readiness gates without repeating the unchanged frontend run: policy,
manifest-only Wiki, responsive contracts, production Compose, workflow syntax,
backend lint/types, migration drift and OpenAPI drift. Schema generation reports
four operation-ID collision warnings and zero errors. This is a split local
readiness pass, not a hosted/full release or final security-record pass. Logs:
`/tmp/tekdocs-final-prep-check.log` and
`/tmp/tekdocs-final-prep-check-resume.log`. No runtime code changed in this fix.

## GitHub scanning inventory

Read-only API snapshot: **282 open alerts**, all last observed at `b987fe738b47097654ffffad01d27357e18fa9cb`: **7 high**, **127 medium**, **148 without a security-severity rating**. Counts are scanner classifications, not confirmed vulnerabilities.

| Rule | Security severity | Count | Alert numbers |
| --- | --- | ---: | --- |
| js/automatic-semicolon-insertion | not rated | 4 | #193, #194, #195, #196 |
| js/clear-text-cookie | medium | 1 | #123 |
| js/incomplete-hostname-regexp | high | 1 | #128 |
| js/incomplete-sanitization | high | 1 | #167 |
| js/regex/missing-regexp-anchor | high | 2 | #130, #161 |
| js/trivial-conditional | not rated | 1 | #197 |
| js/unused-local-variable | not rated | 1 | #168 |
| py/clear-text-storage-sensitive-data | high | 1 | #258 |
| py/conflicting-attributes | not rated | 2 | #191, #192 |
| py/empty-except | not rated | 7 | #106, #107, #180, #277, #301, #302, #303 |
| py/import-and-import-from | not rated | 2 | #108, #305 |
| py/ineffectual-statement | not rated | 7 | #83, #84, #85, #86, #87, #88, #89 |
| py/multiple-definition | not rated | 1 | #120 |
| py/polluting-import | not rated | 3 | #79, #80, #81 |
| py/side-effect-in-assert | not rated | 41 | #90, #91, #93, #94, #95, #96, #97, #98, #99, #100, #101, #102, #103, #104, #121, #149, #181, #182, #183, #184, #185, #186, #187, #188, #189, #190, #255, #288, #289, #290, #291, #292, #293, #296, #297, #298, #299, #309, #310, #311, #312 |
| py/stack-trace-exposure | medium | 126 | #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #49, #50, #51, #52, #53, #55, #56, #57, #59, #60, #63, #64, #65, #66, #67, #68, #69, #70, #71, #72, #73, #74, #75, #112, #113, #118, #119, #127, #134, #135, #136, #137, #138, #139, #140, #141, #142, #143, #144, #145, #146, #147, #148, #153, #155, #156, #157, #158, #159, #160, #162, #163, #164, #165, #169, #170, #171, #172, #173, #174, #175, #176, #177, #178, #179, #198, #199, #200, #201, #256, #257, #259, #260, #278, #279, #280, #281, #282, #283, #284, #304 |
| py/uninitialized-local-variable | not rated | 2 | #166, #287 |
| py/unnecessary-pass | not rated | 1 | #105 |
| py/unreachable-statement | not rated | 2 | #82, #300 |
| py/unsafe-cyclic-import | not rated | 2 | #77, #78 |
| py/unused-import | not rated | 69 | #203, #204, #205, #206, #207, #208, #209, #210, #211, #212, #213, #214, #215, #216, #217, #218, #219, #220, #221, #222, #223, #224, #225, #226, #227, #228, #229, #230, #231, #232, #233, #234, #235, #236, #237, #238, #239, #240, #241, #242, #243, #244, #245, #246, #247, #248, #249, #250, #251, #252, #253, #254, #262, #263, #264, #265, #266, #267, #268, #269, #270, #271, #272, #273, #274, #275, #306, #307, #308 |
| py/unused-local-variable | not rated | 3 | #76, #261, #286 |
| py/weak-sensitive-data-hashing | high | 2 | #202, #285 |

## Priority triage notes (not hosted dismissals)

- #285: test verifies Git's SHA-1 object identity and separately verifies SHA-256 source integrity; not password hashing. Preserve Git compatibility; document this context in final disposition.
- #202: runtime `_fingerprint` hashes provider records for change detection, not authentication. Review sensitive fields in provider inputs before disposition; do not replace this with password hashing merely to silence the rule.
- #258: recovery rehearsal writes a synthetic fixture manifest, not a production secret store. Verify every snapshot field and artifact retention before final disposition.
- #167: a fixture's single-newline replacement constructs an expected test result; it is not a sanitizer. Confirm runtime sanitization separately.
- #128/#130: test uses a regex for an accessible link label, not destination validation. Tighten the fixture assertion where useful without claiming a runtime security fix.
- #161: browser test checks a help-link URL by substring. Strengthen the assertion to the intended URL; this is test precision, not a demonstrated outbound-policy bypass.
- #123: synthetic cookie jar in an API-client unit test. Production cookie settings are separately enforced; avoid treating a fixture cookie as evidence of production cleartext transmission.
- 126 `py/stack-trace-exposure` alerts require an explicit per-path review of exception provenance. Some inspected examples use deliberate domain-validation messages; that observation does not disposition the whole group. An AST inventory against the scanned commit groups the alerts by enclosing exception handler. Priority remediation candidates include mixed `IntegrityError` handlers that return `str(exc)` in catalog, inventory and invoice views; database diagnostic disclosure must be reproduced and fixed rather than classifying this whole family as a false positive. Domain-only handlers need separate provenance review.

## Local review progress

### S1 provider and remaining import source review — 2026-10-12

Source review now covers the remaining normalization/domain-dispatch branches
and the provider credential/transport/adapter boundaries:

- Import normalization allowlists record fields/types, bounds text and rejects
  secret-shaped columns and spreadsheet formulas in scalar fields. UUID/CIDR
  failures become validation codes; domain dispatch uses scoped external-key
  mappings and existing model/service validation. Apply remains transactional,
  with exact-scope operator match confirmation and staging erased on success or
  cancellation. Rich Markdown is content, not a promise of secret detection.
- Connection creation/rotation requires a recent interactive session and
  management permission; API tokens cannot set credentials. Non-secret provider
  configuration is separated from encrypted secret material. AES-GCM associated
  data binds tenant, connection and generation; serializer output exposes
  configuration identifiers/status, not secret envelopes or plaintext.
- Shared HTTPS egress checks public DNS addresses, pins the selected address
  while preserving TLS hostname verification, forbids redirect following and
  cross-origin pagination, and bounds timeouts/response reads. Response/pool
  cleanup and capped Retry-After are covered by earlier fixes and regressions.
- NetBox, UniFi, Graph, HaloPSA and NinjaOne adapters use selected scalar
  projections and bounded page contracts rather than persisting full responses.
  Graph checks tenant/application/audience/issuer/role metadata from the token
  returned by its fixed HTTPS token endpoint; this is not an independent JWT
  signature verifier or a user authentication boundary. Provider traffic is
  replaced in tests; live-provider assurance is not claimed.
- Sync failures retain allowlisted codes and numeric metrics, not arbitrary
  exception text or request/response payloads. NetBox writes use a separate
  configured write credential, exact-workspace source/target lookup, and a
  freshly recomputed proposal digest; read-only providers do not gain implicit
  write authority. The remote write is not a distributed transaction with the
  local audit/database, and these checks do not claim otherwise.

No additional release-blocking defect was demonstrated in this source pass.
The shared integration-security gate passed **176 checks** again. A separate
`test-provider-security` target now covers provider-specific suites without
frontend or upgrade reruns. All **47 provider-specific checks pass**; combined
with the 77-check import gate, S1 is locally complete. The integration and
provider reruns used backend image
`sha256:e5bc473e1d32bc6707a1c6553ab3eabcdb4c3df1872a9b629e8a1379a4d870ae`.
Diff whitespace checks pass. S5 and S6 remain open; no hosted scan, alert
dismissal, commit, publication or deployment occurred.
No runtime behavior, schema or permission policy changed in this slice.

### S1 import upload boundary follow-up — 2026-10-12

Reviewed upload byte/row/column bounds, ZIP member and manifest validation,
preview staging, API workspace/permission resolution, apply/cancel state checks,
exact-scope match confirmation, transactional apply and result-report escaping.
Found a CSV shape defect: `DictReader` stores surplus cells under a `None` key,
which the normalization comprehension silently discarded. Non-empty and empty
extra cells both reproduced acceptance before the fix. The decoder now rejects
either with a row-number-only validation message before batch staging.

Three decoder cases cover both failures and a valid quoted-comma/blank-cell
control; a fourth API case checks HTTP 400 and absence of staged batches, rows
and sites. The first control fixture used an unsupported column and was corrected
to the supported `code` column before reproducing the two failures; its corrected
form passed before the runtime change. Existing short-row behavior is unchanged.
README and the unpublished Wiki draft describe the column-count requirement.
No schema or permission change is involved. S1 remains open for completion of
provider adapter/credential and remaining normalization/domain-apply review;
the shared egress helper was inspected but no live provider validation is claimed.
Verified: rebuilt `make test-imports` passes all **77 checks**, including the
four new cases and existing import/permission/runtime-isolation coverage.
Ruff, import-service types and diff whitespace checks pass. This is local
worktree evidence, not a final-candidate scan or release gate.

Verified combined result: `make test-operations-security` passed all 126 checks
on 2026-10-12 after the remote-document cleanup fix. S2's scoped source review
and local regression work are complete; live transport and final-candidate
release assurance are not implied by this result.

- S2: inspected outbox allowlisted payloads, transactional receipts, bounded retry/dead-letter handling; email claim-time membership/notification/preference reauthorization and fixed error codes; webhook tenant-scoped claims, endpoint activity, replay signing and claim-matched outcome writes; remote document public-HTTPS fetch and explicit apply boundary. Combined regression gate is the runtime evidence, not a claim of live transport testing. Remote-document response cleanup on read failure was subsequently reproduced and fixed; its focused transport regression passes.
- S4b: reproduced raw database diagnostic disclosure through the authenticated catalog API and fixed 29 mixed `IntegrityError` handlers across five view modules. The bounded database-error gate passed 123 checks; domain messages and existing status codes are preserved. This is a confirmed local fix, not a disposition of all 126 exception-exposure alerts or a hosted rescan.
- S3: secret and media validation now pass 49 archive checks; the actual pinned backup tar producer's output also passes media validation. The previously missing media-before-destruction contract was reproduced and fixed; all three restore contract tests pass. Restore project selection and handled Git-init cleanup were fixed in earlier slices. This is local preflight evidence, not a full final-candidate restore rehearsal.

### Security-rated fixture and hashing dispositions — 2026-10-12

These are local source-review dispositions of the baseline inventory, not GitHub
dismissals or fresh scan results. The seven high-rated alerts do not establish
seven exploitable runtime vulnerabilities:

- #285: not a password-hashing weakness. A composition test computes the required
  Git SHA-1 blob identity and separately checks SHA-256 source integrity.
- #202: not password storage. `_fingerprint` SHA-256 hashes deterministic provider
  records for change detection; `integrations.py` compares/persists these as
  observed/remote fingerprints. The provider credential travels separately to the
  approved transport, not as the credential verifier. Full remote records can
  contribute to this digest while only allowlisted projections are retained;
  this disposition is specific to the weak-password-hash finding, not a claim
  that record digests anonymize arbitrary provider data.
- #258: intentional synthetic recovery evidence. The fixture serializes the
  listed billing models plus value-minimized audit snapshots into `expected.json`
  to compare restored identities/values. The harness bootstraps a fresh uniquely
  named project with synthetic billing contacts and a generated fixture password;
  the snapshot model list excludes users/authenticators/credential stores.
  Its manifest lives under the per-run temporary directory, removed by the exit
  trap; the workflow uploads the security-evidence JSON, not that manifest.
  Never run this fixture against a populated installation. This is source
  verification of isolation/retention, not a new recovery rehearsal.
- #167: fixture normalization, not runtime sanitization. The test replaces its
  single newline to construct an expected result; runtime `safeText` uses
  `replaceAll` for the escaping and newline conversions. Existing rendering
  security evidence remains separate.
- #128/#130: accessible-link-name test regex, not a hostname authorization check.
  The same assertion checks the exact relative href. No runtime hostname bypass
  is demonstrated; assertion precision can be handled with quality triage.
- #161: test-only partial matching of the fixture's NinjaOne help URL, not a
  runtime destination policy. Tightening that expectation is quality work, not
  a demonstrated security remediation.
- #123 (medium): synthetic browser cookie-jar setup, not production session
  creation. It verifies CSRF-token parsing; it does not establish that deployed
  session cookies are sent in cleartext.

S4b remains open for the 126 exception-exposure paths and final fix mapping;
S4c remains open for the unrated quality findings. No suppression was added.

### Network exception provenance — 2026-10-12

Local source review dispositions for 17 more baseline alerts:

| View family | Alerts | Disposition and provenance |
| --- | --- | --- |
| NetBox reconciliation | #51, #52 | Operational-owner denial is a fixed `InventoryError`; `_error` maps `IntegrityError` to a fixed message, while callers otherwise pass `NetBoxReferenceError` or Django validation messages. |
| Network addressing | #53, #169 | Same fixed owner denial/database boundary. Service errors are validation guidance; overlap queries use the selected data scope and canonical-address guidance derives from the submitted value. |
| Network circuits | #55, #56 | Same fixed owner denial/database boundary. Circuit errors are scoped-reference checks or model `full_clean` validation, not raw database or transport exceptions. |
| Network endpoints | #57, #170, #171, #172, #173 | Same fixed owner denial/database boundary. Assignment conflicts have literal guidance; address messages use canonical submitted addresses and selected-scope subnet/namespace checks. |
| Network inventory | #59, #60, #174 | Owner denial and assignment conflicts are literal guidance. `_service_error` callers catch only `NetworkInventoryError`; service-level database conflicts are translated into fixed asset-link messages. |
| Network services | #175, #176, #177 | Same fixed owner denial/database boundary. DNS validation produces controlled guidance and canonical submitted values; reassignment conflicts have fixed text. |

These are intentional validation/conflict responses, not demonstrated stack or
database diagnostic exposure. The broad `Exception` annotation on some helpers
does not mean arbitrary exceptions currently reach them: the catch types at
each call site were reviewed. No production behavior changed for this group.
The new `test-network-error-security` gate retains existing network and runtime
RLS regressions plus 15 direct tests across the five database-error translators.
The direct tests distinguish database diagnostics from permitted domain and
Django validation messages; they do not fault-inject every API route.
Verified result: all 98 checks in that rebuilt Docker gate pass, including the
15 new translation cases. Ruff and diff whitespace checks also pass.

Four additional literal-message paths were source-reviewed: #67/#68 catch only
`SiteHierarchyError` (fixed parent-location/cycle messages, with database errors
handled separately); #66 catches only `ReminderError` (fixed input/owner/source
validation messages); #65 catches only `EntityRelationshipError` (fixed type,
classification, self-link and duplicate-link messages). The relationship service
translates its database conflict into a literal message. No raw nested exception
text is propagated by those constructors. This is source-review evidence;
their broader service suites were not rerun in this network-only gate.

After the network pass, **105 of the 126 exception-exposure alerts lacked a complete local
disposition**. Those 105 included the 29 previously fixed database branches:
their remaining domain-message provenance still needs explicit mapping. This
count does not claim 105 vulnerabilities or alter hosted alert state.

### Catalog, inventory and billing exception provenance — 2026-10-12

An additional 56 baseline alerts now have complete local dispositions:

| Family | Alerts | Disposition and provenance |
| --- | --- | --- |
| Catalog | #4–#11 | #5/#6/#8–#11 included raw database diagnostics, fixed earlier. Remaining messages are supplier/archived-record rules, fixed stale-revision guidance, or bounded JSON-schema validation of submitted specifications. Schema failures use a fixed message; value-validation errors intentionally retain the field path and validation explanation. |
| Hardware inventory/CSV | #40–#49, #199/#200 | #44/#45/#199/#200 database branches were fixed earlier. Other messages are fixed lifecycle/scope/assignment rules, model field validation, controlled CSV-parser errors, or row-number-prefixed inventory/software domain messages. Network endpoint validation was traced in the previous pass. #50 is publication-related and remains open. |
| Software inventory | #69–#75 | Fixed owner denial and lifecycle/license/seat rules, plus model `full_clean` field validation. The domain wrapper does not catch database exceptions. |
| Commercial | #13–#19 | Fixed owner/provider/retained-cost rules and model field validation. `CommercialError` does not wrap database or transport diagnostics. |
| Stock | #162–#165 | Three database branches were fixed earlier. Other text comes from model field validation, fixed archive/quantity rules, or the selected stock item's available quantity/unit. |
| Invoices | #137–#148, #155–#157, #201, #256/#257 | Eleven database branches were fixed earlier. All `InvoiceError` construction sites are in `invoicing.py`: fixed issuance/lifecycle/origin/integrity rules, model field validation, or the reviewed `StockError` wrapper. Delivery's Django validation comes from controlled input/model validation; unexpected transport errors use a fixed failure response. Service-rate validation is separate from its fixed database-failure response. |

This separates two outcomes: the previously confirmed database disclosure was
fixed, while intentional domain/field validation is retained. Standard field
validation can include submitted values and model constraint labels; it is not
being certified as value-free or described as a stack trace. No new runtime
change or scanner suppression was made in this pass.

The database-error gate now also includes commercial and inventory stabilization
coverage and eight direct tests of the commercial/hardware/software/stock
validation wrappers. They verify that field validation is converted while a
database exception is not mislabeled as a public domain error. API/database
regressions remain distinct from these direct wrapper checks.
Verified result: the rebuilt `make test-database-error-security` gate passed
all 141 checks. The new test file passes Ruff; diff whitespace checks pass.

**After this pass: 77 locally dispositioned, 49 remaining.**
The 49 include five previously fixed publication database branches whose domain
provenance is still pending. Hosted alerts have not been dismissed or rescanned.

### Document/publication and remaining domain provenance — 2026-10-12

Forty-eight additional local dispositions:

| Family | Alerts | Message provenance |
| --- | --- | --- |
| Repository publication | #279–#284 | Five earlier database fixes now have complete domain review: package, authorization, STATIC, control and delivery exceptions have literal workflow messages. Evidence errors use fixed preflight codes, including wrapped primary-file errors; source/Git command errors replace underlying failures with fixed text. |
| Authoring/index/source exports | #259/#260/#278/#304 | Authoring/input/index errors have fixed guidance. Source/export/bundle failures translate parser, storage and integrity failures into fixed messages. Primary-file conflict text is literal. |
| Legacy document operations | #134–#136 | Fixed owner/review/metadata rules, plus a `TaxonomyError` wrapper whose terms are handled below. |
| Placement/revision | #35/#36/#112/#153 | Placement errors use fixed rules or bounded position/count information; restructure blockers originate in controlled findings. Revision conflict text is fixed; the response's separately authorized revision data is not an exception traceback. |
| Publication/export/download | #32–#34/#50/#63/#113/#118/#119 | Fixed lifecycle/integrity/retained-file rules. Wrappers trace to controlled placement/key-freeze messages, preflight finding-catalog summaries, and renderer errors. Renderer raw OS/JSON failures are normalized; retained-file reads replace OS diagnostics with fixed integrity/unavailable messages. |
| Taxonomy | #158–#160 | Fixed governance rules and bounded submitted term/key/alias validation. Document-term assignment uses fixed unavailable/retired/version guidance. These messages are intentionally not value-free. |
| Compliance | #12/#20–#26 | Fixed audience/record limits, source/owner/control availability, review state and risk-policy rules; catalog size text interpolates a constant limit. |
| Domain/hostname/certificate | #30/#31/#37–#39 | Controlled name/provenance/lifecycle/owner/monitoring validation. Unicode and missing-record exceptions are replaced with fixed messages, not collector diagnostics. |
| Custom fields | #27–#29 | Invalid generated schemas/configuration use fixed messages. Value failures intentionally expose only the JSON-schema validation explanation, not its verbose exception/traceback. |
| Data flows and recycle bin | #127/#64 | Data-flow helper callers catch controlled domain/Django validation; labels and endpoint-side names in domain errors are fixed. Recovery conflicts are literal dependency-restoration instructions. |
| Recurring invoices | #178/#179 | Controlled schedule/date/preview/terms rules, model field validation, previously reviewed invoice/stock messages and fixed money-validation guidance. Invalid signed previews and date overflows are normalized. Database conflicts already have their own fixed response. |

The five publication workflow classes now have source regression guards requiring
literal public messages at their current construction sites. The new bounded
`test-document-error-security` gate exercises documents, repository composition,
authoring and database-message guards. It intentionally excludes upgrade tests:
there is no schema change, and final upgrade evidence remains mandatory in S5.
The additional compliance/domain/custom-field/recurrence dispositions are source
review, not fresh full-suite runtime evidence for those subsystems.

**Before the integration fix: 125 local dispositions; #198 alone remained open in the
126-alert exception family.** Its integration-link handler catches both
`NetBoxReferenceError` and broad `ValueError`; the latter can originate in
`int(conflict.remote_id)` and echo a malformed identifier. Normal provider
ingestion expects integer identities, but that is not sufficient evidence to
waive the broad fallback without checking the error path. No hosted dismissal
or scanner suppression occurred.

The document gate passed all **218 checks**. For #198, two direct service tests
then reproduced the broad `ValueError` disclosure; controlled domain guidance
already passed. The handler now catches `NetBoxReferenceError` separately and
uses a fixed public message for other `ValueError` failures. All three focused
cases pass with the fix and are included in the integration-security gate.
The rebuilt `make test-integration-security` passed all **176 checks**, including
the three new cases, existing integration behavior/authorization and runtime
isolation. Ruff, integration service types and diff whitespace checks pass.
This completes local dispositions for all **126 exception alerts** and therefore
all **134 security-rated baseline alerts** (7 high, 127 medium). S4b is locally
complete; no hosted alert was dismissed and no fresh CodeQL scan is claimed.
The 148 unrated quality findings, S1 review and final-candidate evidence remain.

### Quality triage, first bounded group — 2026-10-12

Reviewed **26 of 148 unrated findings**; 122 remain untriaged. This is source
triage, with runtime evidence limited to the retained-file fix described below.
No hosted alert is dismissed and no scanner suppression is added.

| Alerts | Local disposition |
| --- | --- |
| #302 | Confirmed retained-attachment read defect. A failed storage read after evidence verification left `b""` as the fallback; a zero-byte descriptor could therefore produce HTTP 200 despite the failure. Use `None` for unavailable content and require a successful read before byte/hash checks. Three direct fault cases reproduced HTTP 200 before the fix; the valid empty-file control passed. |
| #303/#301 | Intentional fail-closed verification. STATIC PDF download leaves `content=None` unless verification succeeds; evidence signature checking leaves a required validity flag false on decoding/signature errors. |
| #277 | Intentional directory-creation race handling: after `FileExistsError`, ownership/path checks still run before permissions are applied. |
| #107 | Missing temporary-file cleanup is benign; the original decryption failure is re-raised, not converted into successful restore. |
| #106 | Certificate verification failure leaves `trust_valid=False` in the returned monitoring evidence; this reports an untrusted certificate rather than approving it. |
| #180 | Test harness retries readiness errors for a bounded 50 attempts, then raises. Not an unbounded or successful fallback. |
| #83–#89 | Ellipsis bodies declare seven Protocol methods for scanner/storage/credential/provider contracts; they are not attempted runtime implementations. Retain these typing contracts. |
| #79–#81 | Intentional layered Django settings imports, explicitly lint-annotated. Production, development and test settings override the shared base; do not replace these with partial settings copies. |
| #77/#78 | User-manager/model import cycle is guarded by `TYPE_CHECKING` in the manager; the runtime does not import the model back through that branch. |
| #166 | `argparse.ArgumentParser.error` exits on the contract failure path before `contract` is used. No reachable uninitialized variable in the ordinary CLI. |
| #287 | Fixture variables are assigned and read under the same unchanged `change == "unrelated_historical"` condition. No uninitialized path demonstrated. |
| #191/#192 | Update serializers intentionally prioritize compare-and-set interface validation over create validation. Mixed interface/record updates are rejected; services also reject combined interface/hardware changes and protect existing hardware bindings. Existing network gate evidence is separate; no new network runtime change or rerun in this slice. |
| #82/#300 | Intentional exceptions inside rollback-test context managers. The context managers must unwind; assertions after `pytest.raises` verify the rollback. |
| #105 | Redundant `pass` before a serializer field has no behavior. Cosmetic removal may accompany future network serializer maintenance; not a release defect. |

The retained-file regression replaces authorization, lookup and initial
verification to isolate storage failure **after** successful verification.
It proves handler behavior, not a live storage outage, signature bypass or
cross-workspace access. Four cases cover valid empty content and each caught
storage error type, including unchanged private/no-store response headers.
They are now part of `make test-document-error-security`.
All four focused cases, Ruff and view-module types pass in the rebuilt image.
The first broader run was blocked during test-database creation by Docker disk
exhaustion. Removing dangling TekDocs images under existing approval reclaimed
0 bytes; no volumes or containers were removed. The operator then approved
unused build-cache cleanup: 7.586 GB reclaimed from the `desktop-linux` builder,
with about 8.8 GiB free inside Docker. The broader gate was retried on the same
image and passed all **222 checks**, including the four new retained-file
regressions. The disk blocker is cleared and this local fix is verified;
final-candidate release evidence remains separate.

### Remaining quality dispositions — 2026-10-12

The remaining **122 findings** now have local source dispositions, completing
all **148 unrated baseline findings**. No additional runtime defect was
demonstrated in this group. These are not 148 code fixes or hosted closures.

| Alerts | Disposition |
| --- | --- |
| #203–#254, #262–#275, #306–#308 (69) | Explicit same-name compatibility reexports: 23 model names, 43 serializers and 3 document-key view exports. Removing these as unused imports would change module interfaces. New tests verify each exported object is identical to its defining-module object. All 69 pass in Docker. Retain the exports. |
| #90/#91/#93–#104/#121/#149/#181–#190/#255/#288–#293/#296–#299/#309–#312 (41) | Test actions inside assertions: test-client DELETE requests and two outbox dispatch calls. Every flagged site is in a pytest test module, not a runtime authorization or mutation boundary. The supported pytest configuration uses assertion rewriting, not plain optimized Python execution. Keep these tests enabled; optional extraction of actions into local variables is follow-up readability work, not a demonstrated production security defect. |
| #108/#305 | Test modules intentionally import both individual helpers and a module namespace for CLI/constant access or monkeypatching. Retain both forms; this does not load separate copies of the module. |
| #120 | The attachment response helper uses a local numeric `status` variable, shadowing the module's REST-framework status import. It is initialized before use, changes to 206 only for a valid range, and is passed as the response status. No conflicting runtime definition demonstrated. Optional rename to `response_status` belongs to cleanup. |
| #76/#261/#286 | Dead assignments, not skipped operations: clearing the quarantine-key local after promotion, initializing create-only `current_source`, and naming an unused test commit result. The scanner result is used as `scan.engine`; the commit operation and cleanup/error paths must be preserved if these assignments are simplified. No runtime change required for closeout. |
| #193–#196 | Four adjacent arrow-function declarations in Documentation use JavaScript's automatic semicolon insertion at declaration boundaries. Each initializer ends before the next `const`; no accidental continuation or changed return value was found. Formatting cleanup, not a reproduced navigation defect. |
| #197 | The contextual-help branch follows the constant `WIKI_PUBLISHED` switch. This is a deliberate publication gate, not a permission check. Changing publication policy is outside scanner cleanup; do not enable links merely to remove a constant-condition warning. |
| #168 | Unused Node filesystem `constants` import in the renderer worker. No side effect is lost because the same filesystem module remains required for its other imports. Cosmetic removal can accompany renderer maintenance. |

Follow-up scope (maintainer-owned, next relevant 1.x maintenance slice):
extract mutation/dispatch calls from test assertions for readability; rename
the local response status; remove dead assignments, redundant serializer
`pass`, and the unused renderer import without dropping required calls; apply
declaration formatting and tighten the previously reviewed test-only help-link
assertions (#128/#130/#161) where useful. These are non-blocking maintenance
items, not accepted security vulnerabilities. Compatibility exports and the
help publication switch are intentionally retained, not cleanup targets.

Verification: 69 compatibility identity checks pass using the current backend
image with the new test file mounted read-only; Ruff and diff whitespace checks
pass. Normal full pytest discovery includes the new file. No production code
changed in this slice, so the broader runtime suites were not rerun; the prior
222-check document gate remains the retained-file fix evidence. No Wiki/API,
schema or permission behavior changed. S1 and S5/S6 remain open.

The detailed dated worktree evidence remains in [phase-8-security-review.md](phase-8-security-review.md).
