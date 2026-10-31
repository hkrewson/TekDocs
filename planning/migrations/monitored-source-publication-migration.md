# Monitored-source document migration

Bounded #105/#106 continuation after diagram runtime `5b7a9314` and closeout
`ab48a667`. The maintainer authorizes preserving source settings, observation
history, local edits, signed publications, PDFs and every file version; verify
rollback/recovery and commit/push directly to main after validation. Version
remains 0.9.16. No release, deployment, production migration or Wiki publication.

Acceptance at existing migration, source/read/apply, publication/download, browser
and upgrade/recovery interfaces:

- Preserve stable source/observation identities and all settings, scheduling,
  applied pointer, immutable observation bytes/metadata, local source revisions,
  signed artifacts, control events, PDFs and managed-file versions. Settings and
  observations remain SQL workflow state, never copied into authored Git files.
- Bind reviewed migration plans to retained source state and refuse corrupt,
  missing, out-of-scope or unsupported history. Recheck under authority locks.
- Checks retain observations and do not change authored content. A reviewed
  observation can update an exact owned primary Git fragment atomically with
  the applied pointer and audit. Require a current review fingerprint; refuse
  stale settings, authority, Git/index/body or observation state without partial
  SQL, Git or retained-file changes. Use the maintained coordinated writer.
- Preserve local edits: when current text differs from the last applied remote
  body, refuse automatic replacement. A missing baseline also requires manual
  integration unless the current body already equals the selected observation.
  No automatic merge or force-overwrite workflow is introduced in this slice.
- Keep central edit/MFA, tenant/client, source egress, body/file ownership and
  shared-consumer boundaries. Keep source operations available in the promoted
  document interface with current review/conflict and retry behavior.
- Verify ordinary and grouped rollback/re-promotion, fresh/0.8.46 upgrade and
  exact independent encrypted recovery without network access. Align API,
  tests, ADR, roadmap, development notes, Wiki draft and risk dispositions;
  complete source review and local Docker gates before the authorized push.

Use only existing `tekdocs` services and a separate test database locally.
Independent stacks remain hosted-only. General cross-Workspace reuse, client
portal delivery and aggregate 1.0 acceptance remain separate.

## Source review and reproduced corrections

The [two-axis source review](../releases/monitored-source-source-review.md)
records both independent read-only reviews and their re-reviews. Standards and
Spec each have zero remaining actionable findings. The initial lock-order,
legacy nesting and apply/read-outcome findings were reproduced at public seams
before correction. Full timestamp precision was also proved by a failing custody
fingerprint test and its passing correction.

The first broad Docker run completed 505 cases: 504 passed, and an unowned-file
negative fixture failed because its all-zero UUID was not a valid managed-file
link. The maintained extractor returned zero identities for that fixture and
one for a valid synthetic UUID. The corrected fixture keeps the rejection and
no-partial-change assertions; no production parser or guard was weakened.
All 32 focused monitored-source/transport cases then passed. The final source
retest passed 34 cases, including pending unchanged observations and a large-history
resource probe. That probe first measured 39,205,291 traced peak bytes with the
old cursor batch; smaller batches pass the unchanged 24 MiB bound. The final
source retest includes all source/transport behavior after that batching correction.

The first live browser run passed four journeys and timed out during the source
retry. A controlled deferred-save reproduction verified that an old success
message remains visible while the next save is pending and the navigation guard
correctly blocks departure. The original timeout's save/close race is inferred
from that mechanism; its per-step response events were not retained. The test
now requires the actual settings-save/restoration responses to be 201 and the
save control to be ready before closing. The timeout and original assertions
remain unchanged. The complete live rerun passed all five journeys and its
server-side retained-byte and authority round-trip checks.

## Current validation boundary

- **Verified:** the final 656-case combined Docker migration/authoring gate,
  followed by 34 final source/transport cases after the small cursor-batch correction;
  the final full frontend gate with 793 cases; API generation, Ruff, mypy (293 files),
  Bandit, build/bundle, dependency/license, script, pin, language, responsive and
  Compose checks; all five real browser journeys and server custody/rollback.
  The local Wiki draft validates with 53 pages and is not published. No model
  changes were detected using the actual retained test database.
- **Verified hosted at exact runtime source `6c3824c66ce3afdf485ce27c4ea6194b1af8120a`:**
  [Build 41243680921](https://github.com/hkrewson/TekDocs/actions/runs/41243680921)
  and [CodeQL 41243682650](https://github.com/hkrewson/TekDocs/actions/runs/41243682650)
  passed. Build passed all seventeen database groups, including 33 monitored-source
  cases, 89% combined backend coverage, 793 frontend cases, production-image scans
  and all five live publication journeys with server-side preservation and authority
  round-trip verification. The downloaded publication summary has five passed tests
  and `server_verification: passed`.
- **Verified hosted upgrade/recovery:**
  [Extended 41243684051](https://github.com/hkrewson/TekDocs/actions/runs/41243684051)
  attempt 1 passed fresh/0.8.46 document migration and the supported upgrade matrix,
  plus independent encrypted recovery. Original upgrade job `124662618366` logged
  both monitored rollback cohorts and fresh/0.8.46 acceptance. Original recovery
  job `124662618164` logged monitored settings, observations, local edits, signed
  publications, files and PDFs recovered exactly at `2026-10-31T21:46:37Z`.
  Downloaded security packets for authorization/RLS, dependency/license/secrets,
  image scans, CodeQL, DAST, upgrade and backup/restore, and the diagram
  upgrade/restore packet, identify the exact source and report `passed`.
- **Verified final Extended conclusion:** attempt 2 passed with unchanged source.
  Retried mobile Chromium job `124677581401` passed all four responsive cases;
  the downloaded browser packet identifies `41243684051:2:chromium+firefox+webkit+mobile`, the
  exact source and status `passed`. The other nine Extended jobs succeeded in
  attempt 1; their retained packet identities remain `41243684051:1:*`, not
  re-execution claims for attempt 2. Original attempt 1 failed that browser image
  build: `apk upgrade --no-cache`
  could not fetch Alpine v3.23 main APKINDEX (`TLS: unspecified error`), then exited
  99 with stale/unavailable repositories before any browser assertion. The underlying
  network cause remains **unknown**. No code, package policy, timeout or assertion
  changed for the retry. The original failure and diagnostic cascade remain in the
  [failure ledger](../releases/validation-failures.json).
- **Blocked locally by repository policy, resolved by hosted evidence:** independent
  fresh/0.8.46 upgrade, encrypted restore and production-image environments require
  separate projects and services. They ran in hosted CI rather than provisioning
  parallel local stacks. Locally, authoring/migration Make commands were adapted to
  `exec` against existing `tekdocs` services with a separate test database and
  sequential backend tests. The standalone source cohort compares source workflow,
  all local revisions, signatures/control events, actual file/PDF bytes and accepted
  Git sources without contacting an upstream server.

The bounded slice is complete at runtime source `6c3824c6`; later evidence-only
commits make no new runtime claim. Both final source reviews have zero remaining
findings. The final live rerun passed all five browser/server journeys with the
reuse-impact disclosure included.

Version remains 0.9.16. Existing CSP/COEP/KaTeX and development/build-tool findings
retain their ownership and expiry; this slice accepts or renews no exception.
No release, deployment, live production migration or Wiki publication is claimed.
