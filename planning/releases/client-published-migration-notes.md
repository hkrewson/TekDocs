# Client-published migration development notes

Development after published 0.9.17; candidate preparation for 0.9.18 is separate.
The bounded [#105/#106 slice](../migrations/client-published-document-migration.md)
adds client-visible retained history and audience-specific sections to the
existing reviewed Git authority handoff.

- Existing client links, approved access, signed publications, PDFs and file
  versions keep their identities and retained bytes. Pending, withdrawn and
  superseded records keep their existing portal restrictions.
- Staff can publish a promoted organization document for the client audience,
  including review-on-date retention. A separate authorized approver must approve
  it before it appears in the portal. Corrections and withdrawal use the same
  retained-history controls as before migration.
- MSP-only and client-only sections stay in their respective editions. Client
  snapshots exclude staff-only text, ordinary-file references and unused field-key
  bindings. Referenced client files and all primary-file versions are retained.
- Existing portal list/detail/download and notification targets remain in use.
  This does not convert old publications into the separate repository-native
  STATIC delivery workflow or silently authorize client distribution.

The implementation and source review are complete. Exact-source hosted Build,
CodeQL and Extended validation are the completion authority, including fresh/0.8.46
migration and independent encrypted recovery. Inspect the Actions checks on the
feature commit descending from `34f7b864`; their artifacts bind the exact source.
No new release, production action,
Wiki publication or renewal of existing risk exceptions is claimed here.

## Review and reproduced failures

Both source-review axes were rerun after corrections and report zero remaining
actionable findings. The specification review found an unavailable 0.8.46-only
seed import and incomplete notification lifecycle/recovery evidence. The shared
fingerprint now uses the baseline's signature verifier and strict artifact-byte
reads; current-only verification checks full custody. Notification edges and
current authorized targets now participate in lifecycle, rollback and recovery
checks. Hosted execution remains necessary to establish the actual upgrade and
independent restore result.

The standards review identified early indexing of an empty retained v5 source
list. A copy of an otherwise valid signed-history object reproduced `IndexError`;
list/nonempty/root-object checks now fail closed. All four malformed-source cases
pass without mutating the retained object. The stale-preview test initially named
a nonexistent error token; the maintained `preview_changed` rejection was
confirmed, and the test now also proves that the history changed the plan digest.
No rejection or no-partial-write assertion was removed.

Two initial local browser attempts failed in the new scenario. Bounded timing
records distinguished no publication request from a later 404 workspace read.
The first used the wrong submit selector; a focused component test confirmed the
existing `Publish correction` control. The second reproduced an unassigned
approver's workspace denial under the runtime role. The fixture now uses the
maintained exact-organization assignment service; an unrelated organization still
returns 404. No authorization policy, timeout, retry or original assertion was
weakened. The third run passed all seven browser/server cases in 2.3 minutes.
A frontend type check also caught an unsupported Testing Library selector option;
string-name matching retains the same exact control assertion without that option.
These fixture corrections make no claim about earlier unknown notification or
browser failures recorded for 0.9.17.

## Known risks and evidence boundary

No dependencies, endpoints or publication formats were added. Existing CSP,
COEP, KaTeX and separately recorded build/development-tool findings retain their
original decisions and remediation obligations; this slice accepts no new risk or
extends an exception. Unsupported history, generic cross-Workspace references,
invalid custody and nonreversible graphs stay blocked.

Local validation uses only the existing `tekdocs` services and a separate test
database in the existing database service. Unmodified `make check`, PostgreSQL
partition scripts, fresh/upgrade and independent recovery scripts create additional
containers or projects, so their relevant components are adapted to `compose exec`
locally. Actionlint, independent image rehearsals, fresh/0.8.46 migration and
independent encrypted restore require the exact-source hosted gates. Passing an
in-process recovery fingerprint does not establish an independent restore. Local
Valkey was already restarting with retained AOF damage; this task neither repairs
it nor treats the direct outbox dispatcher checks as worker transport evidence.

## Local verification

The final standard `make test-publication-browser-live` gate passed all seven
real browser journeys in 2.2 minutes with zero retries, followed by server custody,
notification, byte-preservation and authority-round-trip checks. Browser artifact
hygiene passed. Both source-review axes are clear.

- **Verified:** the adapted migration/authoring/authorization gate passed 623
  Docker cases. Ten additional portal, storage-failure and final edge cases passed,
  including filtered empty-file custody, same-audience corrections and the
  0212-to-0211-to-head guard cycle. Both original and new client signatures and
  retained PDF bytes survived that cycle; cleanup restores migration head in
  `finally`. The final new client test file contains 24 cases.
- **Verified:** 795 frontend cases across 128 files, generated API types, lint,
  type checking, production build and bundle budgets, and licenses for 609
  dependency versions. All seven failure-diagnostic contracts passed.
- **Verified:** Ruff, mypy over 293 source files, Bandit with no findings, Django
  model/migration consistency on the real test database, and zero OpenAPI drift.
  The tooling gate completed 141 cases: 138 passed and three environment-specific
  cases skipped. Version,
  dependency pins, Wiki links, product boundaries, language, responsive ledgers,
  Compose contracts and edited shell syntax passed.
- **Inferred:** the baseline-compatible seed and current recovery proof are ready
  for independent execution; source review and the in-process cohort establish
  readiness, not the outcome of a separate restore.
- **Blocked locally by the repository topology rule:** independent fresh/0.8.46
  upgrade, encrypted restore, image rehearsals and Actionlint confirmation. Hosted
  Build, CodeQL and Extended validation must establish those results on the
  feature commit. This is part of delivery, not a request for operator follow-up.

## Hosted browser contract follow-up

Feature source `b7db480a` passed the dedicated 24-case client-publication group,
795 frontend cases, static/policy/runtime checks and both CodeQL analyses plus
commit-bound evidence. Extended Chromium, Firefox and WebKit exposed the older mocked organization
publication journey's `disabled` audience/retention assumptions at 320px and
1440px. Both cases reproduced unchanged in the existing frontend container with
zero retries before any test edit. The fixture is an organization Workspace, and
the real server journey plus runtime-role tests independently establish the
intended audience capability; no application authorization defect is inferred.

The focused correction tests enabled client selection and review-date retention,
then restores the internal/permanent selection and retains exact request checks,
permission-denial recovery, correction/withdrawal/history/PDF/accessibility
assertions. Correction audience is explicitly required to remain disabled and
unchanged. No assertion deadline or retry policy changes. The failure ledger
preserves the original run and the red/green reproduction; follow-up hosted gates
must validate the exact corrected source. Earlier passing source results do not
substitute for that confirmation.

The focused corrected file passed all 12 Chromium/Firefox/WebKit cases with zero
retries in the existing frontend service, plus lint/typecheck and both review
axes. The superseded source's incomplete Build/Extended runs are not passing
evidence; their logs and original Chromium artifact remain retained. Final
corrected-source Build, CodeQL and Extended runs must complete all gates, including
independent fresh/upgrade/recovery, before delivery closes.
