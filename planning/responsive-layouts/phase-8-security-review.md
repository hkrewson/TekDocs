# Phase 8 candidate security acceptance

Review date: 2026-10-12. Source scope:
`b987fe738b47097654ffffad01d27357e18fa9cb` (`v0.9.7`, the input to 0.9.8
acceptance). Owner: project maintainer, [issue #38](https://github.com/hkrewson/TekDocs/issues/38).
Status: in progress. This is automated/AI-assisted acceptance evidence; no
independent human security assessment is required or claimed.

Remaining work is now enumerated in the [security closeout checklist](security-closeout-checklist.md),
including the dated complete GitHub CodeQL inventory. Use its fixed work packages
to track closure rather than treating each new regression as release completion.

## Verified hosted evidence

The following five value-minimized evidence fragments were downloaded and
checked with `validate_evidence_entry` against the exact source commit above.
All have passing status and valid completion metadata. They remain available
in the referenced hosted runs; local copies are ignored under
`artifacts/security-evidence/b987fe738b47097654ffffad01d27357e18fa9cb/`.

| Category | Run and immutable result identifier |
| --- | --- |
| Authorization and forced RLS | [Build run 38215167641](https://github.com/hkrewson/TekDocs/actions/runs/38215167641), `38215167641:1:runtime+postgres-shards` |
| CodeQL | [CodeQL run 38211029544](https://github.com/hkrewson/TekDocs/actions/runs/38211029544), `38211029544:1:python+javascript-typescript` |
| Dependency, license, and repository secrets | Build run 38215167641, `38215167641:1:security` |
| Production image vulnerability scans | Build run 38215167641, `38215167641:1:backend+frontend+renderer+mailpit` |
| Production image digests, SBOMs, and provenance | Build run 38215167641, artifact `11733131789`; artifact digest `sha256:a1fb91048d55796f4f73d7818761e5e412b179c9f0ab80313c1cd4396d64a26f` |

This is a partial evidence set. Supported upgrade, encrypted
backup/restore, complete source review, and the final DAST evidence record still
need to be assembled before the complete security gate can pass. Local DAST
execution and bounded source-review results are recorded below and in the
[production-image acceptance record](phase-8-production-image-acceptance.md).

## Passive DAST warning dispositions

`make dast` passed again on 2026-10-12: 12 URLs, 62 PASS, 0 configured FAIL,
5 WARN, 0 IGNORE. The pinned scanner was
`zaproxy/zap-stable@sha256:781a2bdaea47324e7bab583e2263f21d257b0aee61ed51521a5be45f5f5081ef`.
The disposable production stack also passed its migration, repository
persistence, ClamAV, renderer, secret-file, and runtime-isolation checks.
No rule was suppressed or downgraded; no raw report was retained.

| Finding | Disposition and evidence |
| --- | --- |
| `TD-DAST-COMMENTS`, ZAP 10027, Informational | Scanner parsing false positive in `/assets/index-osWp5l5x.js`. The exact generated entry bundle parsed successfully with Acorn's ECMAScript module parser and contained zero comment tokens. No source-map files were present in the production frontend. No comment-based disclosure was identified; keep the rule enabled and recheck when the bundle changes. |
| `TD-DAST-PUBLIC-CACHE`, ZAP 10049, Informational | Expected caching of public application resources in the unauthenticated scan. Reported examples are content-hashed JavaScript, the application icon, and web manifest. Nginx sets a one-year lifetime for hashed assets and requires entry-document revalidation. This disposition applies to public frontend resources only; it does not accept caching authenticated document or API data. |
| `TD-DAST-INLINE-STYLE`, ZAP 10055-6, Medium | Retain the existing compatibility allowance with a bounded follow-up. Nginx and backend CSP allow inline styles; application layout and generated Mermaid SVG use them. Authored Markdown disallows author CSS/style attributes, rendered content is sanitized, Mermaid runs in strict mode with external CSS references rejected, and `script-src` remains same-origin without inline/eval allowances. Residual style-injection risk remains if those controls fail. Owner: maintainer/#38. Review by 2026-11-12 or the next release candidate, whichever is earlier; investigate narrower generated-style nonces/hashes with editor, diagram, PDF, and browser compatibility checks. |
| `TD-DAST-SPA`, ZAP 10109, Informational | Expected single-page application detection and a scan-coverage limitation. The baseline does not execute the authenticated application workflows. The maintained browser matrix, live backend journey, and authorization/hostile-input suites provide separate evidence; the passive result alone cannot close those checks. |
| `TD-DAST-COEP`, ZAP 90004-2, Low | Retain the existing omission with a bounded follow-up. COEP is absent; the current same-origin CSP and frame restrictions do not provide equivalent browser process/side-channel isolation. No cross-origin-isolation guarantee is claimed. Owner: maintainer/#38. Review by 2026-11-12 or the next release candidate, whichever is earlier; test `require-corp` across login/OIDC navigation, PDF workers, diagrams, fonts, and maintained browsers before changing the header policy. |

ZAP's rule documentation supplies the severity and purpose of
[10027](https://www.zaproxy.org/docs/alerts/10027/),
[10055-6](https://www.zaproxy.org/docs/alerts/10055-6/), and
[90004-2](https://www.zaproxy.org/docs/alerts/90004-2/).
The dispositions above are specific to the inspected candidate and do not waive
new findings, broader authenticated scope, or expired follow-ups.

The comment check used Acorn 8.18.0 with module parsing and comment collection on
the 458,183-byte production entry bundle. Its SHA-256 was
`9f947a19cdc7bfb1771df7445b4117151920d29414cdf5f49011cc79dde5c9d0`.
The locally rebuilt frontend image used for that inspection was
`sha256:d5293468b266afee5bc1392901910b46fe8ff17de2fbb6e6d2d8c20c9c5af2d0`;
this local image is not substituted for the hosted production digests above.

## Additional source review

The managed Git storage and command paths were checked in
`repository_storage.py`, `repository_service.py`, and the workspace/permission
entry points in `content_authoring_views.py`. Paths reject traversal, control
characters, option prefixes, and reserved Git components. Filesystem custody
rejects symlinks and unexpected ownership; Git runs through a fixed executable
and argument list with an isolated environment and a restricted configuration.
Historical reads require a retained commit belonging to the selected repository.
Writes compare the accepted base under repository/database locks, and reject
unreconciled heads. No new concrete issue was identified in this bounded slice.

Existing `test_repository_storage.py` and `test_repository_service.py` cover
hostile paths/refs/configuration, concurrent writes, bounded lock/command waits,
interruption recovery, missing objects, and value-free command failures. The
passing candidate PostgreSQL workflow is the runtime evidence; those suites
were not rerun solely for this source read. Host administrators and hostile SQL
through the trusted application role remain outside the claimed boundary;
`TD-RISK-073` retains its approved 1.x priority.

## Browser acceptance

The maintained desktop/mobile matrix passed on 2026-10-12 in Docker:
1,181 passed and three intentional performance-only skips (9.2 minutes).
Chromium, Firefox, and WebKit each passed 391 checks; mobile Chromium and
WebKit each passed four. The skipped performance checks require their dedicated
rehearsal and are not counted as performance acceptance.
The artifact-hygiene gate passed for `artifacts/playwright-safe/all.json`, SHA-256
`43d0462c348d6ea74a5885bfb1deb2969a5aa82b46469b4dc3758469227c983f`.
A local `browser_security` evidence fragment records that exact summary.

The new live Git authoring journey initially reproduced a real API defect:
the Markdown input serializer trimmed leading/trailing whitespace. The
worktree fix disables trimming for authored Markdown only, preserving indented
code and final newlines. All 29 `test_content_authoring.py` tests passed in
Docker with the revised source mounted read-only, including exact
create/update/read assertions. The live journey checks the same contract
through the editor. This changes the candidate source: hosted
evidence above remains baseline evidence, not proof of the eventual revised
release commit. Final frozen-candidate checks must cover the fix.

The focused saved-editor layout fixture reproduced an accessibility defect:
the file section skipped from an `h1` to an `h3`. It now uses an `h2`.
All 12 layout/accessibility cases passed across Chromium, Firefox, and WebKit
at 320, 390, 768, and 1440 pixels, including expanded portable metadata and a
retained attachment. All 23 repository-editor component tests also passed.
The live resize check now waits for the shell's existing 150ms margin transition
before checking the unchanged page-overflow limit; its initial overflow report
was a transitional measurement, not a retained mobile layout defect.
Frontend/backend lint, TypeScript configuration checks, and the exact OpenAPI
comparison passed. The schema retains four pre-existing operation-ID warnings
and no generation errors. Host-generated ignored package metadata carried an
old version, so the schema comparison used a fresh image without mounting that
metadata; the actual built application version is 0.9.7.

The final `rehearse-live-workspace-e2e.sh` run passed with zero retries
(169,235ms browser time), including its post-browser retained-record checks.
The real session/API/database/Git journey verifies saved content after reload,
two-tab conflict rejection and explicit rebase, attachment upload followed by
an explicit link commit, export of the saved revision rather than an unsaved
draft, wrong-workspace rejection, and phone-width accessibility.
The value-free `artifacts/playwright-safe/live-workspace.json` passed artifact
hygiene; SHA-256:
`f154d5f618748906492a94a6aa46228b42ec3eb0877690d7b06899a890773ff7`.
Screenshots, traces, videos, and downloaded document bytes are not retained.
The rebuilt-image `make test-content-authoring` gate also passed, covering
content profiles, indexing, composition, reads, authoring, source validation,
runtime RLS, and API contracts. No database schema or API shape changed.

## Recovery and upgrade recurrence

On 2026-10-12, `make supported-recovery-rehearsal` passed against the current
worktree. Scope is baseline `b987fe738b47097654ffffad01d27357e18fa9cb` plus
the recorded authoring/accessibility fixes. SHA-256 of
`git diff -- backend frontend/src` at execution:
`40f8b2036c9731e1a10abb40f8757b36621e9805ba19f558ceea0e99dcb90d97`.
The production-target backend image was
`sha256:c1efe1a0e24c9d5ef215b7b592089acf6bacbeb85fb57345e3b247e168ffcfa5`.
This is local worktree evidence, not a hosted final-candidate attestation.

The rehearsal restored two managed repositories, six retained managed files,
one legacy publication, and three repository publications into independent,
network-isolated custody. It verified Markdown and Git history, pinned content,
MSP/client separation, Git-authoritative reads, exact editable bundles, legacy
and Git-only primary-file history, and signed publication evidence. It also
passed refusal checks for bounded write failure, missing or corrupt files,
database/Git head mismatch, the wrong recovery key, truncated repository data,
and missing destructive confirmation. Post-restore corruption was rejected by
the custody verifiers and client routes. Disposable stacks and recovery keys
were removed by the rehearsal; no operator data was targeted.

Recovery script SHA-256:
`22d6df21e2fdbc56e1f010802c748d4f142ea930d0222a575ad2e7ec811b53a5`.
`make repository-foundation-acceptance` also passed on the same worktree:
three workspace repositories retained deterministic manifests and exact accepted
heads through interrupted-write recovery, container recreation, encrypted
backup, and a clean network-isolated restore. This separate fixture has no
retained files or publications; those are exercised by the supported-recovery
fixture above. Neither pass substitutes for upgrade or performance acceptance.

`sh tests/rehearsals/rehearse-document-migration-upgrade.sh` passed: documents
retained their identities across the 0.8.46 upgrade, and the migrated and fresh
installations produced matching results for the same Git migration workflow.

The supported-minor matrix exposed an outdated portal/notification fixture at
the 0.5.9 boundary: its verification query used an implicit principal in MSP
scope and could no longer see the retained organization. The fixture now binds
the actual installation owner as a USER principal for authorized organization
discovery and exact-organization verification. It additionally asserts that
organization reads fail closed before that binding. No application permission,
RLS policy, or migration was weakened. The complete 0.5.9 rehearsal passed on
rerun with retained notification state, preferences, outbox evidence, signed
publication manifest, and PDF verified.

The 0.7.13 compliance fixture initially failed before creating baseline data
because it imported the later `RLSPrincipalMode` API unconditionally. Its
version-compatible helper now retains the historical scope binding on old
sources and explicitly binds the owner USER principal on current code. The
0.7.13-to-current upgrade then passed without schema changes or policy changes.

The recurring-invoice rehearsal reproduced a separate incomplete-backup
problem: its database/media-only fixture omitted the managed repositories.
Restore startup correctly raised `Accepted repository content is unavailable`.
The rehearsal now stops its only running writer, captures verified repository
bundles, restores them before startup, and verifies them against restored
database authority. It reuses the supported repository recovery commands;
the production encrypted-backup implementation was already repository-inclusive
and passed above. Failure diagnostics are retained in the command output before
the disposable stack is cleaned up.

The corrected recurring-invoice rehearsal passed: four repositories were
restored and verified, followed by exact invoice restoration, amendments,
withdrawal retention, stopped-schedule history, invoice corrections, signed
artifacts, forced RLS, safe retries, and active continuation.

All eight supported upgrade cases passed against the same application worktree:
`0.1.3` (`147d00c`), `0.2.9` (`58520f1`), `0.3.12` (`e11743f`),
`0.4.9` (`2f15710`), `0.5.9` (`f15b6a7`), `0.6.9` (`fc8aec7`),
`0.7.13` (`8fdde2d`), and `0.8.0` (`557a976`). The initial matrix invocation
stopped at the portal fixture defect; remaining cases and corrected cases were
run directly with the matrix's exact source/version parameters. This records
eight successful cases across targeted invocations, not a claim that the initial
matrix command exited successfully. Final hosted acceptance must rerun the
complete matrix on the frozen commit. Fixture lint (allowing test assertions),
shell syntax, diff whitespace, route inventory, and acceptance-ledger checks
also passed. Performance was not measured during these concurrent rehearsals.

## Local performance follow-through

The [dedicated performance record](phase-8-performance-acceptance.md) captures
the next worktree slice. It added real-Git source-read coverage, reproduced an
all-files scan on single-document entry, and reduced warmed source p95 from
1,902.8 ms to 47.4 ms without using projected Markdown as authority. The locator
checks the accepted revision under the Git read lock and verifies source
identity/digest; drift falls back and unavailable Git fails closed. All 158
authoring-gate checks and the repository-service regression selection passed.
Four constrained browser profiles passed after separating their test timeouts.
This bounded security/performance review does not replace the full source audit
or convert earlier worktree evidence into final commit-matched evidence.

## Publication authorization and portal source review

On 2026-10-12, reviewed the package authorization, signed STATIC publication,
release/supersession, delivery authorization, and client portal paths in
`repository_package_authorization.py`, `repository_publication_packages.py`,
`repository_static_publications.py`, `repository_static_controls.py`,
`repository_static_delivery.py`, and `repository_portal_views.py`, with the
corresponding decision/scope entry points in `repository_publication_views.py`
and central permission policy. This is a bounded review, not the complete
application source audit.

Verified source properties and matching regression coverage:

- Packaging and signing alone confer no client delivery authority. Positive
  review, package authorization, release, and delivery remain separate records;
  actor-separation checks reject self-approval at the applicable transitions.
- Portal lookup is exact-tenant/client/workspace scoped and excludes unreleased,
  withdrawn, and superseded records. Readiness verifies the retained signature
  chain, artifacts, and current visibility of referenced entity cards.
- Download handlers reread bounded retained bytes and verify the actual response
  bytes, including a tested change between initial verification and download.
  Private responses are no-store; attachments are forced downloads with nosniff.
- Existing regressions exercise MFA-enrollment denial, read-only and portal
  mutation denial, sibling-client and foreign-tenant denial, missing artifacts,
  signed-manifest tampering, immutable records, and explicit supersession.

`make test-content-composition` passed in Docker (exit 0), running content
profile, index, composition/publication, and runtime-RLS suites. Backend image:
`sha256:f28278c0ed3b17d25270682fb2c40acf1e430795b435177cb786d57c89894f79`;
migration/test image:
`sha256:c5d177a24b8c6f26412648056cec7f083c3f611515d97407ef1cd610b3aa0cda`.
The application diff fingerprint remains the performance record's
`4ddf9231c243eb1b5448d52d69d61939e7099ba8f7f706638efd495b8e2db12d`.
No application behavior or assertions were changed in this review slice.

**Authentication-contract finding (owner: maintainer/#38):** central
`require_permission` verifies TOTP enrollment;
the inspected repository approval entry points do not themselves check recent
reauthentication. The existing end-to-end service tests use forced sessions plus
enrollment. They therefore prove neither a fresh authentication ceremony nor the
threat model's stronger “MFA-reauthenticated” approval wording. Trace the full
session boundary and reproduce a stale-session approval before deciding the
required enforcement and client reauthentication flow. Do not count enrollment
tests as proof of recent reauthentication, or silently weaken the documented
contract. This review does not claim an unauthenticated approval bypass.

### Final delivery authentication correction

The follow-up reproduced a concrete stale-session delivery authorization in
Docker: `test_repository_evidence_decision_is_separate_from_distribution[native]`
gave an authorized, TOTP-enrolled approver an allauth authentication timestamp
one day old. Allauth reported the session was not recently authenticated, but
the final delivery POST returned `201` and `permits_distribution: true` instead
of `403`. This was an authenticated-session freshness gap, not a cross-client
or unauthenticated access bypass.

The delivery POST now invokes central
`require_recent_interactive_authentication` after scoped permission/resource
checks and before creating authorization, audit, or availability records. It
rejects bearer authentication even when accompanied by session cookies and uses
allauth's existing freshness check; stale sessions receive the stable
`recent_authentication_required` error. OpenAPI and generated client types
describe reauthentication followed by an explicit retry. No new authentication
protocol, database schema, or publication state was introduced.

Verified locally: `make test-content-composition` passed all 97 collected checks
in Docker; both bearer-marker policy tests passed. The combined account-MFA
and API-contract suites also passed in Docker (exit 0). Changed-file Ruff and mypy
checks passed, generated API types match the schema, and diff/route/acceptance
ledger checks passed. Schema generation reported zero errors and the existing
four operation-ID collision warnings. Test images were backend
`sha256:31dba6cce725c3ab4eb0beb366126c1cfb04259865255351e4eea95ba4faacda`
and migration/test
`sha256:fefcc7ecd7e18a80013ab0e5f52c8b599b958dc0943209512b00217a243598d2`.
The subsequent view-only edit wrapped a schema-description line for lint;
runtime behavior is unchanged. The policy/view diff SHA-256 is
`e5665ab2ac4345c121638fe88f1cff7c79db912e8476b799cbeb92d050132471`.
These are worktree results, not final commit-matched release evidence.

The regression now covers stale and absent authentication records, no delivery
or notification on denial, an actual browser password-reauthentication request,
and successful retry, plus missing-CSRF denial. Existing actor separation,
artifact integrity, cross-client/tenant, supersession, and withdrawal assertions
remain. Focused policy tests cover both token markers before session checking.
The resulting contract is recent password **or** MFA authentication on an
MFA-enrolled account, not mandatory fresh TOTP for every workflow stage.

This bounded fix applies to final client delivery. Internal review, package
authorization, release and emergency withdrawal retain their existing policy;
the broader wording/behavior question was left open at this point and is
dispositioned in the follow-up below.
The older threat-model file is ignored local guidance, not a tracked release
contract; it has been clarified locally without claiming a published Wiki update.
There is no repository-delivery control in the current frontend panel to retrofit;
the supported authentication API retry is exercised directly. The public Wiki
was read at `75ceee0f9705fb4189491f8593489737218fc061`; its linked Security-model
page is absent. A Documentation-page update is drafted locally in
`/tmp/tekdocs-security-wiki.knUbQ8/Documentation.md`, not published.

## Publication boundary disposition and rendering review

Follow-up on 2026-10-12 resolves the repository approval-stage question without
adding freshness prompts to every internal operation. The delivery service has
one non-test application caller: the scoped, recently authenticated delivery
POST. The state machine never transfers a predecessor's delivery authorization
to its replacement and does not allow a withdrawn/superseded record to be
released again.

| Stage | Client-access effect | Authentication boundary |
| --- | --- | --- |
| Evidence review, package authorization, signing, internal release | None without a distinct delivery authorization | Existing scoped permissions, TOTP enrollment where required, actor separation |
| Final delivery authorization | Enables the exact released, intact record | Scoped approval permission, TOTP enrollment, recent interactive authentication |
| Withdrawal or supersession | Removes access to the old record; replacement still needs its own delivery approval | Existing scoped approval permission; withdrawal is not delayed by the new freshness check |

This documents the implemented Git-backed boundary, not a claim that every
legacy review operation already performs recent MFA. The previous local
threat-model wording must not be used as evidence of such a universal guarantee.
`make test-content-read` passed in Docker, including the publication lifecycle,
scope/portal denials, retained-file checks, content reads, forced RLS, and entity
projection upgrade regression. No additional authority change was needed here.

The rendering review covered `rendering.py`, `repository_publication_render.py`,
`content_composition.py`, `content_read.py`, the scoped read entry points,
`SanitizedMarkdown.tsx`, `sanitize.ts`, and `MermaidDiagram.tsx`. Markdown disables
authored HTML and sanitizes the result; reference cards use escaped authorized
projections, and retained cards introduce no download authority. Composition
bounds depth, node count, and expanded bytes and rejects audience widening.
Ten new regression cases verify hostile entity/file labels in paragraphs,
callouts, tables and footnotes for live and retained HTML, plus missing-projection
redaction. All ten passed without production renderer changes.

### TD-SOURCE-SVG-REFERENCES — resolved locally

Severity: Medium (output-filtering weakness). Owner: maintainer/#38.
The browser SVG filter scanned explicit schemes and CSS URLs but did not reject
relative `href`/`xlink:href` resources. Four failing component regressions
reproduced acceptance of protocol-relative, root-relative, relative, and
HTML-entity-encoded image references in simulated renderer output. The SVG
remained displayable/downloadable rather than falling back safely. This is a
filter-boundary reproduction, not evidence of an end-to-end exploit through
authored Mermaid source or observed data disclosure.

After DOMPurify, the filter now parses inert SVG XML, rejects invalid/non-SVG
output, and permits only fragment-local `href`/`src` attributes, including
namespaced href. Existing scheme/CSS checks remain. Unsafe output keeps the
existing source fallback and cannot be downloaded. A positive regression proves
local links and paint references still work. No dependency or API change.

Verification:

- `make test-markdown` passed in Docker: 752 existing frontend checks and all
  31 backend rendering checks, including the ten new reference cases. The
  frontend snapshot preceded the SVG change; do not count those 752 as its retest.
- Final changed frontend: 13 focused Mermaid/sanitized-Markdown component checks
  passed; API generation consistency, ESLint, TypeScript, production build and
  bundle budgets passed.
- Real Mermaid author/edit/save/download/accessibility journey passed in
  Chromium, Firefox and WebKit, three checks in 21.3 seconds with zero retries.
  It ran in a network-isolated Docker browser image with mocked application APIs,
  not against production. Image:
  `sha256:b9fae9e22b3abaf9123b0defd38c6942c0f8dcf527293ffac7521ae3180ef399`.
- Changed renderer/test diff SHA-256:
  `120da2efb8f7dcb3bfe42049ed618e062a512b012a3bd02be847258c3149645d`.
  Backend rendering-test image:
  `sha256:e7807f71e26819fc54ab31a492fea18c39061a6e2d89bba3e2c90fd1315449fb`.

The first host-Node test attempt failed before tests because its installed native
runner binding was incompatible. The maintained Docker fallback passed without
changing dependencies or assertions. Final frozen-candidate aggregate checks
remain required after this new frontend change.

## Account/token boundary review — 2026-10-12

Reviewed bearer parsing and middleware binding, token issuance/rotation/revocation,
current subject checks, central token permission/workspace intersection, RLS request
binding, account adapters, session settings, and existing session/password-reset
regressions. The security-review checklist guided this bounded source pass; it is
not a claim that every account lifecycle path has been reviewed.

Eight new PostgreSQL/API regressions passed without production-code changes:

- Four malformed bearer headers return 401 even when the same browser has a
  valid owner session. A subsequent request without the bad header still works.
- Both personal and service tokens stop authenticating after their subject is
  disabled; these requests use a separate, cookie-free client.
- Both token kinds lose their scoped document access after the organization is
  archived and cannot fall back to MSP document access.

Verified: Docker `make test-auth-abuse` passed the complete account suite,
including the new cases and existing session, MFA, invitation, password-reset,
and access-control checks. Changed-test Ruff and `git diff --check` passed.
Test image: `sha256:5f9334f6b640e3342d80a60385c8d8979e5d39af7f569888b450ae9703f5ba3c`.
Changed-test diff checksum (SHA-256):
`faf66f598a252caa6263e6cacc21a937c1f4a4bb23d48e89c23f2cfd3c779e66`.

No new defect was reproduced in these eight cases; no schema, API, or public
operator behavior changed, so no Wiki change is required for this test-only slice.
Further source review still includes non-DRF/allauth credential interactions,
OIDC/invitation lifecycle and live membership/role changes. Passing the account
suite does not substitute for that review or final candidate-matched evidence.

## Browser/API credential separation — 2026-10-12

Finding `TD-SOURCE-BEARER-BROWSER`, Medium: the API-token middleware replaced
`request.user` for all routes, including maintained allauth browser routes that
do not apply TekDocs token permission scopes. Six failing Docker regressions
reproduced a document-read-only personal token receiving HTTP 200 from current
session, session-list, and enrolled-TOTP information endpoints, both with and
without session cookies. This demonstrates out-of-scope account information
access, not proven account takeover or disclosure of an enrolled TOTP secret.

Bearer headers are now rejected outside `/api/v1/` before token lookup or user
replacement. The rejection also covers malformed/mixed-case headers and mixed
browser/token credentials; the response is non-cacheable and contains no account
data. Normal browser requests without bearer headers and scoped API-token
requests retain their existing authentication paths. No schema migration or
dependency change is required. These non-DRF routes are outside the generated
OpenAPI surface; README records the restriction and a matching Wiki Home draft
is prepared locally in `/tmp/tekdocs-security-wiki.knUbQ8`, not published.

Added 25 cases: twelve personal/service-token browser read combinations, a
CSRF-valid attempted session revocation that leaves sessions/audit unchanged,
and twelve malformed-header/route cases proving rejection before token lookup
or downstream dispatch. The first full account run passed these cases but
failed eight later fixture logins with HTTP 429: the expanded tests shared the
test profile's in-memory rate-limit cache across rolled-back databases. A
module-local, per-test autouse fixture now clears that test-only cache before/after each
case. No rate-limit setting or assertion was weakened.

Verified after cache isolation: `make test-auth-abuse` passed all 131 account
checks in Docker, including the existing scoped-token, CSRF, MFA, session,
password-reset, invitation, and OIDC checks. Changed-file Ruff, authentication
module mypy, and `git diff --check` passed. Final test image:
`sha256:4104f43644306721867b8cb48f2ad66d92b343ebd6cf45b558869c0859ebf133`.
Authentication regression diff checksum (SHA-256):
`55772d6af0eeaaa55857a4bcc0a20d1e59e0704c8e210398382c8e77b428534a`.
The fix is verified in the worktree, not deployed or bound to a release commit.
Wiki publication remains pending authorization.

Further API account/profile permission review, OIDC/invitation source checks,
and live membership/role changes remain open. This fix does not complete the
entire account-family source review.

## Profile mutation authorization — 2026-10-12

Finding `TD-SOURCE-TOKEN-PROFILE`, Medium: four failing Docker regressions
reproduced a personal or service token with only `documents.view` changing its
subject's display name through `PATCH /api/v1/auth/profile`, both without
cookies and with an owner browser session. The endpoint checked installation
membership but did not exclude bearer authentication. This is an out-of-scope
profile mutation, not evidence of password, role, or email changes.

The endpoint now uses session authentication (including CSRF enforcement),
then the central `require_profile_edit` policy rejects token markers and bearer
headers before validation or mutation. No new permission, role, MFA-enrollment,
or reauthentication requirement is introduced for ordinary profile edits.
Seven new regressions cover the four token/session combinations and three
malformed bearer headers; denied requests leave display names and profile audit
events unchanged. Existing positive, missing-CSRF, invalid-input and unrelated-
user cases remain in the complete account suite.

OpenAPI and generated frontend types now describe the session-only profile
contract. README and the local unpublished Wiki Home draft agree. No migration
or dependency change is required. OIDC/invitation source review and live role/
membership-change checks remain next in the account workstream; external egress/
integration and operational/recovery source review follow before inventorying
GitHub code-scanning alerts, as agreed with the maintainer.

Verified: `make test-auth-abuse` passed all 138 account checks in Docker.
Changed-file Ruff and policy/view mypy passed; schema validation completed with
zero errors (four existing operation-ID collision warnings), generated API
consistency and frontend type checks passed, and `git diff --check` passed.
Test image:
`sha256:fb28b919261fdbb34865eec6ed58d1c78a61acf31426028ce30601bf51786bba`.
Policy/view/token-test worktree diff SHA-256:
`ebb35e2df0002fa34b6cd751c4beda21f21cc9dd103739cb879da5fb7d441b7c`.
These are worktree results, not deployment or final candidate acceptance.

## Existing-token access transitions — 2026-10-12

Added five cases for already-issued credentials: personal/service tokens after
membership deletion; personal/service tokens after removal of their assigned-only
organization grant; and a personal token's effective permission context after
administrator-to-read-only demotion. Each starts with a successful request and
uses the same token in a fresh cookie-free request after the change. Organization
cases also deny fallback to another client or the MSP workspace. The demotion
case checks that `costs.view` disappears while permitted document reads remain;
it is not a new cost-resource endpoint test.

The initial complete suite reproduced three fixture-login failures (HTTP 401):
the new staff fixture lacked the verified email identity that real invitation
redemption creates. The fixture now creates that identity, signs in through the
real password endpoint, and enrolls TOTP through the maintained library. No
authentication setting, production policy, or test assertion was weakened.

Source inspection also covered invitation issue/resend/revoke/redemption and
their scoped views: token digests, rotation, expiry, transactional one-time
redemption, password validation, and verified membership creation. Existing
invitation tests cover replay, concurrency, CSRF, unrelated/cross-tenant access,
and mail failure. OIDC settings/adapters still delegate to maintained allauth;
deeper verified-identity linking and mixed-credential token-management checks
remain explicit follow-ups before closing the account-family review.

This slice changes tests and review evidence only: no migration, API contract,
or public operator instructions change, so no new Wiki update is required.

Verified: final Docker `make test-auth-abuse` passed all 143 account checks,
including all five new transition cases. Changed-test Ruff and `git diff --check`
passed. Test image:
`sha256:6c7a41336fa05c9ff0025ab1dbcd89c10c36b006dab32242f654274e1561b76d`.
Token-test worktree diff SHA-256:
`e664cfc148e0b42899bf5994038f4db9c48965766ad63ce747f8834dc5a5d593`.
No production defect was reproduced in these five cases; this is worktree
evidence, not final commit-matched acceptance or deployment evidence.

## Mixed-credential token management and OIDC matching — 2026-10-12

Finding `TD-SOURCE-TOKEN-HEADER`, Low: eight failing Docker regressions
reproduced token list/create/rotate/revoke accepting a bare `Bearer` header or
a tab-separated mixed-case variant when accompanied by an otherwise authorized
browser session. The guard used a literal `bearer ` prefix while authentication
used whitespace splitting. Login, recent authentication/TOTP where required,
and CSRF remained enforced; this was ambiguous-credential fallback, not a
standalone authentication or privilege-escalation bypass.

The common management guard now splits the authorization scheme consistently
and rejects every bearer scheme before token management. Twelve cases cover
four operations and three malformed headers, requiring unchanged token records
and token-management audit counts on rejection. Existing valid browser-session
and scoped-token tests remain. No API shape, schema migration, or dependency
change is needed; the existing session-only contract is enforced more precisely.
README and the unpublished local Wiki Home draft clarify the restriction.

The OIDC follow-up inspects the installed maintained provider's claim extraction
and local identity lookup. Three new tests pass actual provider-extracted claims
into lookup: false/missing `email_verified` must not match the existing owner,
while true can match; lookup alone must not persist a social-account link.
These are synthetic provider-claim tests, not live discovery/TLS/JWT/callback
validation. The configured issuer remains trusted for verified email assertions.
Existing state-redirect and enrolled-TOTP-stage checks remain in the account
suite. External OIDC transport/configuration belongs in the upcoming egress and
production-configuration review rather than being claimed complete here.

Verified: `make test-auth-abuse` passed all 158 account checks in Docker,
including twelve malformed-header management cases and three OIDC identity
matching cases. Changed-file Ruff, token-service mypy, and `git diff --check`
passed. Final test image:
`sha256:8f8c272f2515e185a5db45f05f5257780fbe8d10ce44bad5cd556489034fbffa`.
Token-service/token-tests/OIDC-tests worktree diff SHA-256:
`b883e46fb8818a451e62331cbc525b528b9d99dcbc2ab326529db64aa13e9eac`.
The locally scoped account follow-ups are now verified; this does not imply a
live identity-provider test, a frozen-candidate security pass, or deployment.

## Remaining acceptance

### OIDC outbound boundary — 2026-10-12

Finding `TD-SOURCE-OIDC-EGRESS`: the configured allauth adapter used Requests'
default network path rather than approved egress. Three failing Docker tests
reproduced HTTP, an IP literal, and a hostname resolving to loopback reaching
the unguarded transport (network mocked; no private service contacted). This
requires operator-supplied configuration or provider-controlled endpoints; no
arbitrary unauthenticated destination control or credential theft was demonstrated.

The social-account adapter now supplies a Requests-compatible transport using
the existing approved URL/address validation and pinned HTTPS pool. Discovery,
token exchange, user-info and JWKS share this allauth session hook. Redirects,
non-success statuses, compression and bodies over 1 MiB fail closed; pools and
responses close on success and failure. Errors omit provider response bodies,
request objects and chained transport details. Maintained allauth identity and
signature logic are unchanged. No dependency, database or API-shape change.

The README and unpublished local Wiki draft state the compatibility boundary:
public DNS/HTTPS port 443 only, direct endpoints, no private-address provider,
proxy or compressed response. Tests use mocked DNS/HTTPS responses and cover
safe reads, form and Basic-auth token exchange, mixed public/private DNS,
redirect/error rejection, response bounds and failed-read cleanup. They do not
claim live provider TLS, discovery/callback or end-to-end SSO validation.

Verified: rebuilt `make test-auth-abuse` passed all 175 account checks in
Docker, including the 17 new transport cases. Focused transport tests, changed
file Ruff, adapter/transport mypy and `git diff --check` passed. Test image:
`sha256:66072b87d6e843d9f1630138c705615b1e5055abbeb9208eaa2aa32059851c95`.
Transport file SHA-256:
`2eeca1c6175b30a84c05a15468399fa297a60574cc3b5ab32b9d0278b563a4dd`;
test file SHA-256:
`e46d54b13fac0b84b9bc74af014c88d866a508da53c610935c5c2b079bfe13db`.
This is worktree evidence, not frozen-candidate or production SSO acceptance.

### Import parser rejection — 2026-10-12

Finding `TD-SOURCE-IMPORT-PARSER`, Low: four failing Docker decoder tests
reproduced uncaught CSV field-limit and ZIP manifest/record checksum exceptions,
and acceptance of duplicate bundle filenames. The upload route requires
integration-management permission; no authorization bypass or data disclosure
was demonstrated. ZIPs are read in memory, not extracted to the filesystem.

CSV parser errors now become value-free validation errors. ZIP readers are
closed deterministically and malformed/unsupported archive exceptions become
validation errors; duplicate member names are rejected before records are read.
Eight new checks include four decoder regressions and four API cases requiring
400 with no ImportBatch, ImportRow or Site created. Existing valid preview,
idempotence, exact-workspace isolation, cancellation and atomic rollback tests
remain unchanged. No schema, dependency or API response-shape change.

The new `make test-imports` gate rebuilds images and combines import tests with
import-route permission cases, route inventory and runtime RLS tests. Its initial
all-route run was deliberately stopped without observed failures to avoid
rerunning 1,631 unrelated/shared permission cases for a parser-only change.
Full-suite/CI discovery is
unchanged. README and the unpublished local Wiki import page are updated.
Verified: `make test-imports` passed all 67 selected checks in Docker (13
import tests, 41 permission/inventory cases and 13 runtime RLS tests). Four
decoder reproductions failed before the fix and pass afterward. Changed-file
Ruff, import-service mypy and `git diff --check` passed. Test image:
`sha256:07dbe2f0bf1a922171aa764d787219b3c10ad70d67b239b0cd126b47f29349ca`.
Import-service/test worktree diff SHA-256:
`b74edb459ba6828177414b00bbc8fa44d017643ffeadf6fb91e1277abe71c794`.
The interrupted all-route run is not counted as passing evidence. This is
worktree acceptance for the bounded parser fix, not release acceptance.

Integration source inspection found encrypted credentials bound to tenant,
connection and generation; write-only input fields and allowlisted response
fields; and allowlisted job error codes. This is inspection, not fresh runtime
acceptance. The credentialed-endpoint follow-up identified during inspection is
reproduced and addressed in the next entry.

### Credentialed destination changes — 2026-10-12

Finding `TD-SOURCE-INTEGRATION-DESTINATION`, Medium: a failing Docker regression
reproduced an authorized MFA-enrolled browser session with no recent interactive
authentication changing a NetBox connection's base URL (200 instead of 403).
Source inspection shows subsequent provider sync uses that destination and its
stored credential. No external request or credential theft was performed.
API tokens cannot receive the MFA-required integration-management permission;
this finding does not claim a token authorization bypass.

Destination changes now call the central recent-interactive-authentication
policy after exact-workspace permission and URL checks, before saving. Existing
name/schedule/pause edits and unchanged URLs retain their permission behavior.
The editor now handles the existing recent-authentication error by retaining
the draft and offering the established password-confirmation/retry flow. A
failing frontend regression reproduced the missing edit confirmation first.
The existing successful URL-edit fixture now explicitly has a recent MFA record;
new missing/stale-session cases exercise actual password reauthentication and
CSRF, with unchanged encrypted credential and no update audit on denial.
Cross-client/cross-tenant tests require 404 despite a fresh session.
The new cross-tenant fixture initially violated the existing creator-membership
guard, then the membership-role constraint. The fixture was corrected to use
its own user with a tenant-administrator membership; neither database constraint
nor application authorization was changed to accommodate the test.

No dependency, schema or response-shape change. README and unpublished Wiki
Home draft document the behavior. The bounded `make test-integration-security`
combines integration/stabilization tests, integration route permissions, route
inventory and runtime RLS without changing full-suite discovery.
Verified: the final rebuilt `make test-integration-security` passed all 162
selected checks, including all six new backend cases. `make check-frontend`
passed all 758 tests in 125 files, coverage thresholds, API consistency, lint,
types, production build and bundle budgets. Changed backend Ruff, service mypy
and `git diff --check` passed. The earlier focused frontend command passed its
test assertions but failed the global coverage floor; the full gate above
supersedes it without lowering thresholds.
Final Docker test image:
`sha256:e97e79088c8c4a2851984ef87e8137b58f12831ecf4a42b50a70fa19069beed0`.
Integration service/tests and frontend component/tests worktree diff SHA-256:
`a1873c4ec8cc5ab7f7c8012b26f4e609ffd75742bedffd6f28522b475a949b66`.
This is local worktree evidence, not frozen-candidate or live-provider evidence.

### Outstanding review

### Rejected import identity and credential binding — 2026-10-12

Finding `TD-SOURCE-IMPORT-REJECTION`, Low: six failing Docker API regressions
reproduced nested objects, spreadsheet formulas and oversized values in either
`record_type` or `external_key` escaping as ValueError. The rejected-row path
revalidated the same invalid identifier without handling the second failure.
The authorized import preview failed; no authorization bypass was demonstrated.

The rejection path now validates each display identity independently and uses
`unknown`/`row-<number>` when necessary. It retains no normalized content for
that row. Tests require a rejected row with the original safe reason code, a
valid companion row still classified for creation, and an apply attempt denied
without any Site created. Existing valid import and isolation cases remain.
No schema, dependency or API response-shape changes. README and the unpublished
Wiki import draft describe the safe labels and correcting/re-uploading the source.

Nine additional integration-credential tests exercise successful decryption and
then rejection after changing tenant UUID, connection UUID, generation,
ciphertext, either nonce, wrapped key, algorithm or provider marker. All passed
against the existing maintained envelope-encryption implementation with no
runtime change. This is synthetic local boundary evidence, not a cryptographic
audit, live provider validation, or backup-key rotation rehearsal.

Verified: rebuilt `make test-imports` passed all 73 import/permission/isolation
checks, including the six previously failing API regressions. All nine credential
binding/tampering checks also passed in the rebuilt image. Changed-file Ruff,
import-service mypy and `git diff --check` passed. Test image:
`sha256:385c6948122d4bb00a1706c49421fea59b6feacba76e75ed2d11a67e09cff675`.
Import service, import tests and integration tests worktree diff SHA-256:
`e8bb2fc84c76479878defd0d29cc3712f06ae036f4afbccf7643f568dc88fc68`.
No full integration-suite rerun is claimed for the test-only credential addition;
the preceding 162-check gate remains the prior integration runtime evidence.

### Provider response lifecycle — 2026-10-12

Finding `TD-SOURCE-INTEGRATION-RESPONSE`, Low: two failing Docker regressions
reproduced a 100-digit numeric Retry-After value overflowing before the existing
one-hour cap, and a provider read timeout leaving its response unclosed. These
are local transport robustness findings; no credential disclosure, authorization
bypass, or measured production resource exhaustion was demonstrated.

Numeric retry delays are now capped before constructing the time delta. Response
cleanup is centralized in a finally block, with pool cleanup retained even if
response cleanup raises. Tests retain the safe public error and response-body
redaction assertions. No API shape, schema, configuration, or dependency changes.
This is an internal correction to the existing bounded transport contract, not
a new operator procedure or live-provider validation.

Verified: rebuilt `make test-integration-security` passed all 173 selected
integration, permission and runtime-isolation checks, including both reproduced
failures and the nine credential-binding checks from the preceding slice.
Changed-file Ruff, transport mypy and `git diff --check` passed. Test image:
`sha256:17a5449e8ed89b1ced12061d824de69ce795705c65930fe463f54f303d05ccf7`.
Transport and stabilization-test worktree diff SHA-256:
`d38198588262605355a82aca4aa5d6f941f62e351c4763e17ffd01efd55a8369`.
These results supersede the earlier 162-check integration gate for the current
local worktree, not for a frozen release candidate.

### Recovery archive authentication and cleanup — 2026-10-12

Reviewed `tekdocs/recovery_archive.py` against the backup/restore call sites:
artifact labels are authenticated additional data, decryption finalizes the GCM
authentication before replacing the destination, private temporary output is
removed on failure, and manifest verification uses constant-time comparison.
This is a bounded implementation review, not an independent cryptographic audit.

Eighteen new Docker cases exercise wrong keys, a swapped artifact label, changed
nonce/ciphertext/tag, a truncated artifact and invalid magic, each with absent and
existing destinations; plus valid and altered manifest/key/MAC CLI verification.
Rejected decryptions must leave the output directory empty or preserve exactly
the existing destination bytes, with no temporary plaintext. Manifest failures
must return the static authentication error and no standard output.

Verified: rebuilt `make test-recovery-archive` passed all 23 checks. Changed-test
Ruff and `git diff --check` passed. The tests passed against the existing runtime;
no vulnerability or runtime fix is claimed. The new make gate avoids database
startup and does not replace the supported encrypted-restore rehearsal. No API,
schema, dependency, operator procedure or Wiki behavior changed; README documents
the developer gate. Restore orchestration, jobs and production configuration
remain distinct review work, as does final commit-matched recovery evidence.
Test image:
`sha256:2dafec9b28b9c0d09be7d5e37d3e96612680ffbf14e17a030970111ea43a75f6`.
Makefile and recovery-archive-test worktree diff SHA-256:
`7642a84ffed30035966702128a67b8762c2586a1f8ce02dd019fa0a141296840`.

### Repository restore failure cleanup — 2026-10-12

Finding `TD-SOURCE-RESTORE-CLEANUP`, Low: a Docker fault-injection regression
reproduced a handled Git-init failure leaving the newly created repository
directory behind. The next restore would fail its nonempty-destination guard.
Faults after bundle fetch and accepted-head update already cleaned up correctly.
This demonstrates retry obstruction, not overwritten production data or a
permission bypass. The fault is injected after real Git operations in disposable
directories; it does not simulate process kill, whole-host failure or failed
filesystem cleanup.

The restore now registers its new destination for cleanup before invoking Git
init. Three regressions require an empty destination after each handled failure,
then retry and verify the exact database-accepted Git head. The new
`make test-repository-recovery` includes the existing repository custody,
corruption, storage-exhaustion and nonempty-destination checks plus archive
authentication tests. No API, schema, dependency or operator command changes.

Verified: rebuilt `make test-repository-recovery` passed all 36 checks, including
the previously failing init-cleanup case and successful retries at all three
fault points. Changed-file Ruff, recovery-service mypy and `git diff --check`
passed. Image:
`sha256:9f25c50beb49ee69bf9797ab90e55a033b2ec8b9c66804f69dc2d8962c0c2329`.
Recovery service/test worktree diff SHA-256:
`c8aaf549ef41ad9a5eda9a62fddd423734302ae9c9d7ea8a422d556a0f77470b`.
This focused Docker gate does not rerun the whole-stack encrypted restore or
close its final-candidate requirement. README documents the developer shortcut;
no public Wiki procedure changes are needed for this internal cleanup correction.

### Restore confirmed-project binding — 2026-10-12

Finding `TD-SOURCE-RESTORE-PROJECT`, Medium: read-only Docker Compose configuration
tests reproduced an inherited `COMPOSE_PROJECT_NAME` overriding the project read
from the restore environment file and checked by `--confirm-destroy`. Both the
normal and isolated restore wrappers selected the unconfirmed project. Since
the same wrapper performs `down --volumes`, wrong-project destruction was a
source-inferred consequence; no destructive operation was run or data loss
demonstrated.

Both wrappers now set `COMPOSE_PROJECT_NAME` to the confirmed value and pass an
explicit `--project-name`, binding resource interpolation as well as project
selection. The regression executes the actual checked-in wrapper with disposable
Compose fixtures and only `config --format json`; it checks project and volume
names with/without an inherited override in both isolation modes. This is real
Compose configuration evidence, not a mocked CLI or whole-stack restore.

Verified: all four combinations pass in `make test-restore-project` using Docker
Compose 5.5.1. The complete `scripts/check-compose-config.sh` passes production
setup and Traefik/image-overlay contracts and now runs this regression in the
existing CI configuration job. Shell syntax, changed-test Ruff and diff checks
pass. A first lint-container invocation encountered the local runtime database's
missing forced-RLS table before lint started; the database-free lint invocation
passed without changing database state or startup enforcement. README and the
unpublished Wiki Scripts Reference draft describe the binding. No API, schema,
dependency or restore CLI changes. Full candidate restore evidence remains open.

### Worker scope and production-setting boundaries — 2026-10-12

Reviewed `apps/core/tasks.py`, the Celery configuration, production settings and
the production Compose overlay. Integration/domain/certificate worker entry
points reconstruct UUID scopes and enter the shared system RLS context before
calling their services. Task payloads at these dispatch sites carry identifiers,
not provider credentials. Source configuration selects JSON task/result
serialization and JSON-only accepted content, with a 300-second task limit.
The production web/worker/scheduler overlay uses read-only roots, dropped
capabilities, no-new-privileges and process limits. These are source observations,
not proof of the currently deployed production configuration or broker security.

Twenty-one new tests cover those three worker entry points: exact MSP/client
scope and system-principal binding, scope cleanup after success and injected
service failure, and invalid tenant/workspace/organization UUID rejection before
database/service access. Scope binding uses real PostgreSQL transactions; the
service callbacks are replaced to prevent provider requests. These tests do not
claim that arbitrary well-formed queue payloads are authorized, exercise every
task, or validate broker transport, dispatch races or provider behavior.

Verified: rebuilt `make test-worker-boundaries` passed all 93 checks, including
the 21 new cases and existing runtime-RLS, secret-file and production-setting
validation. No runtime correction was needed. Image:
`sha256:ac4fefeafe68dea2d27ed3650e378036f7b6899ff437329232bdc0b215020d65`.
Final test-file lint passes after import/line-layout cleanup; that cleanup
followed the image build and did not change test assertions. Diff checks pass.
README documents the bounded developer gate. No API, schema, dependency or
operator/Wiki behavior changed. Remaining operations review includes the other
dispatch/service boundaries and restore preflight; final candidate production
and recovery rehearsals remain separate requirements.

### Deployment-secret restore preflight — 2026-10-12

Finding `TD-SOURCE-RESTORE-SECRET-MEMBERS`, Medium: a Docker reproduction executed
the existing shell preflight against a synthetic archive containing every
required filename, with one required entry represented as a symlink. Validation
returned success. Nothing was extracted. The old checks validated member names
but not types or duplicates; extraction followed by chmod could follow an
unexpected link. A modified recovery set still needs valid recovery-key
authentication, so this is authenticated recovery-content hardening, not an
unauthenticated remote exploit.

A network-disabled, read-only helper now validates unique allowlisted regular
files, required names, non-sparse entries, readable member bytes and the existing
1–4096-byte secret-file bound before secret extraction or volume replacement.
No cryptography, schema, API or dependency changed. README and the unpublished
Wiki draft describe the accepted archive contract. The original CLI is retained.

Rebuilt `make test-recovery-archive` passed 34 checks, including 11 new valid,
link, special-entry, duplicate, missing-name, traversal, empty, oversized and
truncated archive cases. The fixtures leave only the input archive, with no
extracted files. Whole-stack encrypted restore still needs final-candidate
verification; this is not evidence that every restore preflight path is closed.
Final rebuilt image:
`sha256:dcec549364b67c26c9bf7f5306b57178f237e2a72780ddec65eb6b14bdc9b8b3`;
all 34 archive checks also passed again in that image after test formatting.
Helper/test Ruff, helper mypy, shell syntax and the production Compose gate pass.
The Compose contract now also checks authentication-before-preflight and
preflight-before-extraction/destruction ordering in the checked-in script.
This ordering check inspects source; it is not a destructive restore rehearsal.

### Combined operational regression review — 2026-10-12

`make test-operations-security` passed 125 checks in the final image above:
outbox, webhooks, notification email/scheduling, documents including remote-source
review/apply, worker boundaries and runtime RLS. Source review confirmed outbox
allowlisted payloads and transactional receipts, claim-time email reauthorization,
tenant-scoped webhook claims and claim-matched delivery outcomes. External delivery
is stubbed in these suites; no live provider, SMTP or broker assurance is claimed.
The first attempt selected a nonexistent standalone document-source test file
and exited at collection; the corrected gate uses the existing documents suite
without dropping its assertions. The full corrected gate is the evidence above.

The fixed closeout checklist records remaining concrete follow-ups, including
remote-document response cleanup and media archive preflight. This combined
regression pass does not waive those unverified paths or the CodeQL review.

### Database diagnostic boundaries and remote-document cleanup — 2026-10-12

`TD-SOURCE-DATABASE-DIAGNOSTICS` (Medium): an authenticated catalog API
regression reproduced raw `IntegrityError` text in both response detail and
field errors. The synthetic diagnostic represents database constraint/row
information, not an observed production disclosure. The paired domain-error
case passed before the fix. An AST regression separately reproduced 29 mixed
handlers formatting database exceptions in catalog (6), inventory (4), invoice
(11), stock (3), and repository publication (5) views.

All 29 now separate database failures from domain validation: database failures
receive a fixed conflict message, while domain messages and existing 400/409
statuses remain unchanged. This does not weaken database constraints or change
authorization. The original bounded database gate passed 123 checks, including
the real API reproduction, handler source guard, catalog/inventory/stock/invoice
behavior, and runtime RLS. The source guard is not a substitute for fault
injection at every endpoint. Three publication/evidence regressions are also
included in the persistent gate. No claim is made that all 126 CodeQL
exception-exposure alerts are resolved; other exception provenance still needs
individual review and the fixed source has not been rescanned by GitHub.

`TD-SOURCE-REMOTE-DOCUMENT-CLEANUP` (Low): a transport regression reproduced
an unclosed response when a remote-document read timed out. Response and pool
cleanup now run in nested `finally` blocks, retaining the existing fixed safe
error code. The regression passed after the fix. Its transport call bypasses
the database decorator and uses a fake connection; the existing documents and
operational suites provide the separate persistence/authorization coverage.
No live network request or provider test is claimed.

Ruff passes for all nine touched source/test files and mypy passes for the six
runtime files. No schema, dependency, API shape, or permission changes were
required for these two fixes.
The final rebuilt backend image is
`sha256:b98676bcca4583ba29b75083ea01c1f939054989cffd7951caf010a0957ebde3`.
All 64 database-handler source checks and the remote timeout regression passed
again together in that image (65 checks), after removing five unused exception
aliases from the publication handlers.
The rebuilt combined operational gate also passed all 126 checks. This closes
the scoped local S2 review; commit-matched release validation remains in S5.
All three selected publication regressions passed in the same image: safe staff
evidence/portal denial, exact organization scoping, and the primary-file
package/STATIC/portal chain. These exercise existing behavior; they do not
inject a database failure into each publication handler.

### Managed-media restore preflight — 2026-10-12

`TD-SOURCE-RESTORE-MEDIA-MEMBERS` (Medium): the restore script authenticated
media bytes but did not validate archive members before replacing volumes.
The new source-order regression failed on the missing preflight call before
the implementation. This reproduces the missing safeguard, not a demonstrated
unauthenticated archive injection or a destructive production restore. Recovery
set authentication and possession of the recovery key remain prerequisites.

The existing read-only, network-disabled preflight helper now accepts a media
mode. It rejects links, sparse/special entries, absolute/parent/ambiguous paths,
duplicate normalized names, file-as-parent conflicts in either order, and
truncated content. It reads regular bytes in bounded chunks without extracting;
empty files and empty media directories remain supported. Validation runs after
authentication and before secret extraction or `restore_compose down`.

Verified in Docker: `make test-recovery-archive` passes 49 checks, including 15
media cases. A regular-file archive generated with the exact pinned PostgreSQL
Alpine image and tar invocation used by backup passes the new CLI. The three
restore contract tests pass (including the existing four Compose-environment
subcases); the ordering assertions are source checks, not a full-stack restore.
Ruff and helper mypy pass; shell syntax and diff whitespace checks pass.
The production setup/Traefik Compose contract gate also passes.
Image: `sha256:3c7202200c9eb4d150ee23bcb85f16b9ac346c5d9e8157888ec850d9bbc2bd6c`.
README and the unpublished Wiki draft describe the new archive contract.

S3's scoped local preflight review is complete. Final encrypted whole-stack
restore, free-space/capacity behavior and candidate-matched recovery evidence
remain release checks; structural archive validation does not guarantee that
every restore can complete or make destructive restore atomic.

The closeout checklist also records local dispositions for all seven high-rated
baseline CodeQL alerts and the synthetic-cookie medium alert. These source
dispositions add no suppression and perform no hosted dismissal. Remaining
exception-exposure paths and unrated quality findings keep S4 open.

### Network exception provenance review — 2026-10-12

Reviewed 17 baseline CodeQL exception-exposure alerts across six network/NetBox
view families. The five mixed-error translators already use fixed database
conflict messages; their callers catch bounded domain/Django validation types.
The remaining network alerts concern fixed owner-denial or assignment-conflict
guidance, or domain messages whose input/scoped-record provenance was inspected.
No runtime defect was reproduced and no runtime behavior was changed for this
group. The closeout checklist maps the alert numbers and source rationale.

`make test-network-error-security` passed all 98 checks, including 15 new direct
translation cases plus the existing network inventory/addressing/endpoint/
service/circuit/NetBox and runtime RLS suites. The new tests preserve permitted
domain messages while rejecting a synthetic database diagnostic; they do not
inject failures into every endpoint. Ruff and diff whitespace checks pass.
Rebuilt backend image:
`sha256:7097ad481d26d64551ef92573ec6ef22065404492c821e5f5e0fe39fc65d774b`.

Source review also dispositioned four literal-message alerts in site hierarchy,
reminders and relationships. These four did not receive fresh full-service
regression runs in this network gate. In total, 21 of the 126 exception-exposure
alerts now have complete local dispositions; 105 remain, including the remaining
domain-message provenance of the 29 previously fixed database branches. No
hosted alert was dismissed, and no scanner suppression was introduced.
README documents the bounded gate; no user-facing runtime/Wiki behavior changed.

### Catalog, inventory and invoice exception review — 2026-10-12

Traced 56 further baseline exception-exposure alerts across catalog, hardware/
CSV, software inventory, commercial, stock and invoice views. The checklist
records exact alert numbers and message origins. This completes the domain
provenance review for 24 of the 29 earlier database-handler fixes; the five
publication handlers still require their domain-message review.

The remaining messages in this group are intentional business rules, canonical
submitted values, scoped-record quantities, JSON-schema field explanations or
model field validation. Invoice delivery separately replaces unexpected
transport errors with a fixed message. Domain wrappers catch Django validation,
not arbitrary database failures. Standard validation is not value-free and may
include model constraint labels; this review distinguishes that contract from
raw database row diagnostics and stack traces. No new runtime defect was
reproduced, and no runtime logic was changed in this pass.

Verified: the expanded `make test-database-error-security` passed all 141 checks,
including eight new wrapper cases, commercial and inventory stabilization,
catalog/inventory/stock, invoice draft/issue/delivery, runtime RLS, the handler
source guard, and three existing publication regressions. The eight direct
tests check that database exceptions are not converted into public domain
errors; they are not fault injection through every endpoint. Ruff and diff
whitespace checks pass. Rebuilt image:
`sha256:7aff6e705bddf14911e6e2259c510cb02d1c5b26758becb31baf678b3027feef`.

After that pass, accounting was 77 complete local exception-alert dispositions and 49
remaining. The review remains local: no hosted rescan, dismissal, suppression,
commit, or publication occurred. The README describes the expanded gate; no
public runtime contract or Wiki behavior changed.

### Document and remaining exception provenance — 2026-10-12

Reviewed 48 additional exception alerts across repository publication, authoring,
document operations, placement/revision, downloads, taxonomy, compliance,
domain/certificate management, custom fields, recovery and recurring invoices.
The per-alert mapping and message provenance are recorded in the closeout
checklist. Five source guards require literal messages at publication workflow
exception constructors. Controlled field validation can include submitted
values; these dispositions do not certify every message as value-free.

The rebuilt `make test-document-error-security` passed all **218 checks**:
document, composition, authoring and database/publication message guards.
Image: `sha256:2f66203e00b142e73a35916cd05941347dbc53dd3d0c243cf32a18c3e40d6dd1`.
Upgrade tests are deliberately excluded from this bounded gate and remain
required in S5. The other domain-family dispositions are source review, not
fresh runtime suites for every subsystem.

The remaining alert, #198, exposed broad `ValueError` diagnostics while linking
a NetBox conflict. Two direct service regressions reproduced the problem before
the fix: malformed stored remote identifiers echoed their input, and an internal
reference failure echoed its diagnostic. The paired controlled-domain case
already passed. The handler now preserves `NetBoxReferenceError` guidance and
returns a fixed message for other `ValueError` failures. All three direct cases
pass with the fix, including the assertion that malformed identities never
reach reference creation. These mocks test error translation, not transaction
rollback or ordinary provider ingestion; the latter already validates integer
identities. The persistent integration-security gate now includes the cases.

The rebuilt integration-security gate passed **176 checks**, covering the new
cases plus integration behavior, authorization and runtime isolation. Image:
`sha256:31a2a31257cd78d28ff7fcaa5592ada8337eeeb11c976fb4b6c266e67b5b286e`.
Ruff, service type checking and diff whitespace checks pass. S4b now has local
dispositions for all 134 security-rated baseline alerts: the 126 exception
findings plus the eight previously reviewed hashing/fixture cases. No hosted
rescan or dismissal, release commit, publication or deployment occurred.
S1, S4c and final-candidate S5/S6 work remain open.

### Quality triage and retained empty-file reads — 2026-10-12

Source-reviewed 26 unrated findings, with the per-alert disposition in the
closeout checklist. Protocol stubs, layered settings, type-only import cycles,
bounded readiness retries and rollback-test context unwinding are intentional.
The remaining 122 unrated findings are not yet dispositioned.

Alert #302 exposed a real fallback ambiguity in `_review_attachment`: a failed
storage open after initial evidence verification could be mistaken for a valid
empty attachment. Three direct fault-injection cases reproduced HTTP 200 for
`OSError`, `ValueError` and `TypeError`; the successful empty-file control passed.
Unavailable content now has a separate `None` sentinel, including errors while
closing the stream, and returns the existing fixed HTTP 409 response. Valid
empty bytes remain downloadable. The four regressions are permanently included
in the bounded document-error gate; they mock authorization/evidence lookup to
isolate this post-verification read boundary, not to prove those earlier gates.
No schema, permission or API shape changes are introduced. The local Wiki draft
clarifies that an unreadable retained attachment is unavailable even when empty;
it has not been published.

Verified in rebuilt Docker image
`sha256:4841355212a6d540d772be4b21eb7016454c5a72606d2e6393eeea0f2af11876`:
all four focused cases, Ruff and publication-view type checking pass.
The first broader document-error run was **blocked by Docker disk exhaustion**:
PostgreSQL test-database setup raised `DiskFull` while creating an
attachment index. Docker's data filesystem had only 27 MiB free despite the
host having 98 GiB available. Approved cleanup removed only dangling images
labeled for the TekDocs Compose project; Docker reported 0 bytes reclaimed,
with cached layers still present. No containers, volumes or database records
were removed. The operator subsequently approved unused build-cache cleanup.
Pruning the `desktop-linux` builder cache reclaimed 7.586 GB, leaving about
8.8 GiB available inside Docker. Containers, volumes and the separate
`cairn-multiarch` builder were untouched. Removed cache can be regenerated by
future builds. The broader gate was retried using the same image and passed
all **222 checks**, including the four retained-file fault/control cases.
This clears the local verification blocker; it does not replace the final
commit-matched release, upgrade or recovery evidence.

### Quality inventory complete locally — 2026-10-12

Reviewed the remaining 122 unrated baseline findings, completing S4c's 148
local dispositions. The checklist maps every remaining alert family and records
non-blocking maintainer-owned cleanup. The 69 unused-import findings are explicit
same-name compatibility reexports; 69 new object-identity tests protect their
model/serializer/view entry points and pass in Docker, with the new test mounted
read-only into image
`sha256:4841355212a6d540d772be4b21eb7016454c5a72606d2e6393eeea0f2af11876`.
Ruff and diff whitespace checks pass. The 41 side-effect assertion findings are
test-only client mutations/dispatch calls under ordinary pytest assertion
rewriting. The remaining twelve are mixed test imports, dead assignments, local
name shadowing, declaration formatting, a help-publication switch and one unused
renderer import; no additional runtime defect was demonstrated.

No production source changed in this slice and no broad runtime rerun is
claimed. The previously repaired retained-file fallback remains backed by 222
document checks. All 282 baseline alerts now have local dispositions across
S4b/S4c, but hosted alerts remain untouched and final-candidate CodeQL evidence
is still required. S1 provider/import review and S5/S6 remain open. No Wiki or
API behavior change, release commit, publication or deployment occurred.

### Import CSV surplus-cell rejection — 2026-10-12

The S1 input-boundary review reproduced silent loss of surplus CSV cells.
`DictReader` puts them under a `None` key, and header normalization discarded
that key. Two decoder cases reproduced acceptance for an extra non-empty cell
and an extra trailing empty cell. A corrected supported-column control confirms
quoted commas and blank optional cells remain valid. Reject surplus cells with
a row-number-only validation error before staging. A new authenticated API case
also requires HTTP 400 and no ImportBatch, ImportRow or Site creation.

Reviewed the upload/container and top-level preview/apply/cancel/report boundary,
including scoped lookup, policy resolution, transaction use and output escaping.
This is not a completed review of every normalization branch, domain writer or
provider adapter. S1 remains open. README and the local unpublished Wiki draft
are updated; no database schema, permission or response-shape change is made.

Verified: all **77 checks** in rebuilt `make test-imports` pass, including the
four new cases and existing permission/runtime-isolation regressions. Ruff,
import-service types and diff whitespace checks pass. Backend image:
`sha256:e5bc473e1d32bc6707a1c6553ab3eabcdb4c3df1872a9b629e8a1379a4d870ae`.
No commit, hosted scan, Wiki publication or deployment occurred.

### Provider credentials and remaining import paths — 2026-10-12

Completed the remaining scoped source pass over import normalization and domain
dispatch, provider credential setup/rotation/encryption/serialization, shared
HTTPS egress, five provider adapters and their pagination/projections, sync
error retention, and the separately credentialed NetBox publication boundary.
The closeout checklist records exact protections and limitations: no live
provider assurance, independent Graph JWT verifier, automatic secret detection
inside authored content, or distributed remote-write transaction is claimed.
No additional release-blocking defect was demonstrated in this pass.

The shared `test-integration-security` gate passed all **176 checks** again.
Added `test-provider-security` to run the provider-specific suites as a focused
companion without frontend or upgrade reruns. README and the unpublished Wiki
Scripts Reference explain that scope. No runtime code, schema or permission
policy changed. All **47 provider-specific checks pass**, completing local S1
alongside the earlier 77 import checks. Both integration/provider reruns used
backend image
`sha256:e5bc473e1d32bc6707a1c6553ab3eabcdb4c3df1872a9b629e8a1379a4d870ae`.
Diff whitespace checks pass. S5/S6 final-candidate validation remains separate;
no commit, hosted scan, alert dismissal, publication or deployment occurred.

### Remaining source and release review

Wiki reconciliation follow-up on 2026-10-12: added the 32 missing guides to the
existing unpublished Wiki checkout, preserved the prior edits and legacy setup
guides, updated navigation and corrected text-only diagram-export guidance.
The full checkout check now passes with 37 required and 45 total guide pages.
Two tests first reproduced the supplemental-page validator defect (valid links
rejected and broken supplemental-page links skipped); the corrected validator
checks all safe-named guide pages while retaining the fixed required inventory.
All six new Wiki tests and all 59 script tests pass. Read-only remote inspection
confirmed the earlier 14-file baseline remains published; no Wiki push or
application help-link activation occurred. This resolves the local inventory
gap noted below, not final candidate or human acceptance.

S5 preparation on 2026-10-12: local readiness passed in two parts. The first
`make check` passed all 758 frontend tests and frontend verification, then
reproduced a stale release-plan test expecting two rather than the intentionally
configured three performance commands. Replaced the loose count/presence checks
with an exact command multiset, preserving latency enforcement and the single
sharded backend boundary. All 53 script tests pass; resuming with
`make -o check-frontend check` passes the remaining checks without repeating the
unchanged frontend suite. This is not full candidate release evidence. The full
local Wiki checkout check separately fails: its 14-page baseline lacks 32 of the
37 expected pages. Preserve its four edited pages and reconcile that inventory
before claiming documentation readiness. The closeout checklist records the
workflow/category mapping and exact limitations. No runtime change, commit,
version bump, push, publication or deployment occurred.

- Bind the passing worktree Git/browser checks to the final frozen candidate
  and rerun the required release checks after its commit is selected.
- Recheck any source changes made after the completed S1–S4 local review and
  verify final production configuration with the candidate's image/Compose
  gates. The scoped provider/OIDC evidence does not claim live-provider testing.
- Obtain commit-matched supported-upgrade and encrypted-recovery evidence.
- Assemble all ten categories and carry the findings above into the final
  value-minimized record with owners, retests, and current review dates.
- Keep technician walkthroughs, pilot, and performance acceptance explicit in
  the wider 0.9.8 checklist; these are not replaced by the security record.

The candidate JSON template remains `not_started` under the repository's rule
that it is completed only after the entire frozen-candidate review. This dated
record preserves the work already performed without claiming that gate passed.
