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
- **Pending:** exact-source hosted Build, CodeQL and Extended validation. The authoring/migration Make commands use per-run
  containers, so their union is adapted to `exec` in the existing `tekdocs`
  service with a separate test database. Backend pytest runs remain sequential.
- **Blocked locally by repository policy:** the independent fresh/0.8.46 upgrade,
  encrypted restore and production-image environments require separate projects
  and services. Hosted `document-migration-upgrade-rehearsal`,
  `supported-recovery-rehearsal` and production-image jobs must confirm them.
  The standalone source cohort preserves source settings/observations, actual
  file/PDF bytes, all local revisions, signatures, controls and accepted Git
  sources, without contacting an upstream server.

Both final source reviews have zero remaining findings. The final live rerun
passed all five browser/server journeys with the reuse-impact disclosure included.

Version remains 0.9.16. Existing CSP/COEP/KaTeX and development/build-tool findings
retain their ownership and expiry; this slice accepts or renews no exception.
No release, deployment, live production migration or Wiki publication is claimed.
