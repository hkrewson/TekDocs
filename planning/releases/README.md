# Release operations: current status first

For release status, evidence closeout, CI failure triage or operator acceptance,
start here. Historical review narratives are supporting evidence, not the live
work queue. `.github/release-candidate.json` still names the historical 0.9.12
security/status packet. The latest exact-source publication record below names
the later release; the checkout's HEAD may be an evidence/tooling commit.

## Future release delivery

The [single-push delivery contract](ci-release-delivery.md) makes image verification,
application tagging and durable updater receipt delivery part of CI for new
versions on main. It replaces the manual tag/receipt handoff for future releases.
Existing release records below remain historical evidence.

The [annotated release catalog](release-tag-catalog.md) adds reviewed two-line
messages to future application tags without changing receipt or image authority.
Historical lightweight tags, including v0.9.19, remain immutable.

## Published and deployed 0.9.19

The [0.9.19 candidate](0.9.19-candidate.md) freezes the accumulated Git-backed
document workflow, migrations 0213-0223, CI/release operations, and dependency
security corrections after published v0.9.18. The
[source/security review](0.9.19-source-review.md) covered all 125 changed source
files in the exact release range with no findings. Supporting main Build
42101197293 passed on attempt 2, including the corrected shard allocation,
browser, production-container, SBOM, vulnerability, and final gates. It was not a
versioned release run and is not relabeled as candidate acceptance.

Corrected exact-source Build
[42148451278](https://github.com/hkrewson/TekDocs/actions/runs/42148451278)
passed on attempt 2 after attempt 1's hosted-runner shutdown. It verified the
supported upgrade and recovery paths, published four images, verified all eight
attestations, delivered `v0.9.19` plus `receipts/v0.9.19`, and passed the final
`Validation passed` job. Production deployed v0.9.19 on November 8, 2026 through
the verified updater, completed migrations 0213-0223, and passed its service,
readiness, release-identity, and immutable-image checks. The Sunday 03:30
America/Chicago updater remains configured with a host-level lock and a 48-hour
minimum release age.

The maintainer accepted the unchanged medium inline-style CSP allowance and low
missing-COEP limitation for v0.9.19 only, with review or remediation due before
the next runtime candidate or November 12, 2026. The maintainer also authorized
the versioned push and its single-push delivery pipeline. Production deployment,
existing-data promotion, Wiki publication, and final 1.0 acceptance remain
separate.

Post-v0.9.19 development has implemented the bounded
[CSP/COEP hardening slice](../csp-coep-hardening.md). The source policy now removes
TekDocs-owned inline styles and adds `Cross-Origin-Embedder-Policy: require-corp`
without claiming full cross-origin isolation. Mermaid rendering is isolated,
Cytoscape's injected rule has an external checked replacement, and Milkdown's
optional inline-style cursor helpers are disabled. Exact-source Build 42439813889,
CodeQL 42449387473 and Extended validation 42449370137 passed, including all five
browser configurations and production-shaped passive DAST. The release-bounded
inline-style CSP and missing-COEP findings are retired as of November 8, 2026. ZAP's
distinct missing-COOP warning remains outside this slice; no full cross-origin
isolation claim is made. The prior v0.9.19 acceptance remains historical.

The [CodeQL alert triage and provider fingerprint hardening
slice](../codeql-alert-triage.md) narrows code scanning to shipped source without
hiding the remaining shipped-code queue. Provider observation schema v2 now
derives retained fingerprints only from the allowlisted safe projection and
rejects mismatched digests before persistence; provider identity keys retain
their established semantics. Historical v1 observations remain readable. The
repository-wide stack-trace alert view combines analysis configurations and
branch instances; exact standalone analysis results are the pre-1.0 API error
contract authority.

The first bounded [exception-response hardening
slice](../exception-response-hardening.md) removes caught-exception text from 19
ambiguous sites across eleven response families while retaining established
400/409 statuses, response shapes, audit behavior, and fixed conflict messages.
Regression tests inject private diagnostics and the guard is part of the backend
image security gates. Build 42544014776 passed every selected job and final
validation. Exact-source CodeQL 42551427527 passed both languages and evidence,
reducing Python stack-trace results from 131 to 112: exactly the selected 19.
The invoice/stock follow-up covers another fifteen results with explicit public
domain-error contracts and fixed framework-validation translations. CodeQL
42552963371 passed and reduced the exact queue from 112 to 97. Build 42552901893
passed every other executed job but failed one `core-c` compatibility assertion:
the initial boundary also replaced the internal `StockError` string. The
reproduced correction separates that retained bounded diagnostic from the fixed
public detail. Corrected-source Build 42559060835 passed its final validation
job, and CodeQL 42559099854 passed both language analyses and evidence delivery.

The next bounded slice selects all twelve exact results in `document_views.py`.
Document operations, composition, export and publication conflicts now expose
only explicit public details, including through taxonomy, content-key and
diagram-renderer wrappers. Unexpected renderer `ValueError` instances are no
longer translated into public conflict text. Build 42565561039 passed its final
validation job; CodeQL 42565622117 passed both languages and reduced the exact
stack-trace queue from 97 to 85, closing exactly those twelve selected paths.

The inventory-handler follow-up selects all nine results in
`inventory_views.py`. Inventory, asset-CSV and software-inventory exceptions
now carry explicit public details; framework model diagnostics receive fixed
hardware/software explanations, CSV row wrappers propagate only nested public
details, and retained publication downloads reuse the reviewed publication
contract. Existing controlled business refusals and HTTP behavior remain
unchanged. Build 42627936205 passed its final validation job; CodeQL 42628004806
passed both languages and reduced the exact stack-trace queue from 85 to 76.

GitHub's open-alert total is larger because it spans every CodeQL rule and two
analysis configurations: 337 current standalone alerts plus 127 retained from
the retired Build configuration at `ef6c57c`. The current exact stack-trace
queue remains 76; cyclic-import and unused-import results are separate review
queues and are not represented as stack-trace remediation progress.

The catalog-handler follow-up selects all eight `catalog_views.py` results.
Catalog exceptions now carry explicit public details, stale revisions preserve
their fixed 409 detail and current-revision payload, and catalog-document
associations reuse the reviewed inventory contract. Complete catalog/inventory
and boundary validation passes locally. Exact-source CodeQL 42671675386 passed
on attempt 2 and reduced the stack-trace queue from 76 to 68. Build 42671601875
attempt 2 ran the source, security, browser and database work but remains
incomplete because the unrelated `template-migration-a` shard reached its
30-minute runner limit; the final gate correctly failed closed.

The software-inventory handler follow-up selects all seven
`software_inventory_views.py` results. The workspace ownership denial and six
software installation/license mutation handlers now expose only their explicit
public detail. Existing controlled seat, license and installation refusals keep
their established messages, error envelope and 400/403 behavior. The boundary
guard and direct DRF regressions pass locally. Build 42695200570 passed every
selected job and final validation on attempt 1; CodeQL 42695221641 passed both
languages and reduced the exact stack-trace queue from 68 to 61.

The commercial handler follow-up selects all seven `commercial_views.py`
results. The workspace ownership denial and six contract/cost mutations now use
explicit public details. Framework model validation receives a fixed commercial
record explanation, while controlled provider, linked-circuit and cost refusals
retain their established messages and 400/403 behavior. The boundary guard and
direct DRF regressions pass locally. Exact-source CodeQL 42741303468 passed and
reduced the stack-trace queue from 61 to 54. Build 42741286617 remains incomplete
because the unrelated `core-a-4` PostgreSQL shard was cancelled and final
validation failed closed.

The repository-publication workflow follow-up selects the five remaining
`repository_publication_views.py` results. Package creation, package approval,
STATIC creation, release/withdrawal control, and delivery authorization now use
explicit public details through one reviewed 409 translator. Existing bounded
domain refusals and response shapes remain unchanged; injected private
diagnostics and the static boundary guard pass locally. Exact-source Build
42762718287 passed final validation, and CodeQL 42762767250 reduced the exact
stack-trace queue from 54 to 49.

The content-authoring handler follow-up selects all four
`content_authoring_views.py` results. Authoring input, primary-file history and
append, and repository export conflicts now expose only explicit public details
through fixed 400/409 translators. Existing bounded messages and structured
compare-and-swap conflict payloads remain unchanged. Exact-source Build
42825216132 passed final validation, and CodeQL 42825279413 reduced the exact
stack-trace queue from 49 to 45.

The network-endpoint handler follow-up selects all four
`network_endpoint_views.py` results. Workspace ownership uses the reviewed
inventory public contract, while interface, IP and MAC assignment conflicts use
an explicit public detail through one 409 translator. Existing reload and
assignment guidance remains unchanged. Private-diagnostic injection and network
translation controls pass locally. Exact-source Build 42937377177 passed final
validation, and CodeQL 42937418397 reduced the exact stack-trace queue from 45
to 41.

The network-inventory handler follow-up selects all three
`network_inventory_views.py` results. Workspace ownership reuses the reviewed
inventory public contract; ordinary inventory validation and hardware-binding
conflicts now expose only explicit public details through status-specific 400
and 409 translators. Existing placement, ownership and reload guidance remains
unchanged. Private-diagnostic injection and the combined boundary suites pass
locally; exact-source Build and CodeQL remain required after push, with an
expected stack-trace queue of 38.

The first exact-source Build for that slice passed all source, database, browser
and coverage work but its SBOM job twice received HTTP 504 while downloading the
pinned Syft checksum asset. The bounded retries then exhausted against the same
provider endpoint. The [Syft delivery resilience
follow-up](2026-11-08-syft-download-resilience.md) now uses Anchore's official,
digest-pinned Syft container without changing SBOM or vulnerability policy.
Corrected-source hosted acceptance remains pending.

## Native template enrollment for new documents

The [bounded native-template slice](../git-native-templates.md) connects saved MSP
Git sources to new client documents with independent copies, live/pinned sections,
reviewed updates and detach. Evidence v4 retains selected source proof without
changing older signed formats. Local combined Docker validation passes 796 cases;
883 frontend cases with coverage, types, contracts and source review pass. All 15
real browser/server journeys pass without retries. Exact-source hosted upgrade,
independent encrypted recovery and security checks follow the authorized push.
This is 0.9.18 development, with no deployment or existing-data transition.
See [development notes](native-template-enrollment-notes.md) and
[source review](native-template-source-review.md).

## Native field/content keys and entity references

The [bounded native-keys slice](../git-native-keys.md) connects new Git-only
binding configuration and entity insertion to protected authoring. Evidence v3
freezes exact field values, fragment source proof and entity cards while retaining
older signed contracts. Migration 0220 adds validators and refuses populated
rollback without rewriting existing records. Local validation passes 202 authoring cases,
868 frontend cases, populated rollback/custody and all 14 browser/server journeys
without retries. Both source reviews are clear; the legacy-fragment permission
bypass is reproduced and fixed at discovery, authoring, runtime and SQL boundaries; exact-source hosted recovery and upgrade
remain required after the authorized direct-main push. This is 0.9.18 development,
not a release or deployment. No existing data is changed. Template and monitored
configuration remain later slices; the six legacy migration gaps stay deferred.

## Native primary-file version controls after publication

The [bounded primary-file slice](../git-native-primary-files.md) connects newly
created Git documents to scanned upload, explicit compare-and-swap replacement,
paged retained history and private downloads. Files and Markdown drafts survive
conflicts/denials; signed publications and their independent files/PDFs remain
intact. The reproduced promoted-owner history gap and service validation-contract
regression are corrected without rewriting existing data.
Verified November 3: remote main `61908a2c7679b42c044bd75e0050094b10f2be23` passed
[Build 41677910926](https://github.com/hkrewson/TekDocs/actions/runs/41677910926)
on attempt 2, [CodeQL 41677944767](https://github.com/hkrewson/TekDocs/actions/runs/41677944767)
on attempt 1 and [Extended 41677948851](https://github.com/hkrewson/TekDocs/actions/runs/41677948851)
on attempt 2. All twenty database groups, combined coverage, thirteen hosted
browser/server journeys without retries, supported upgrades and independent
encrypted restore passed. Restored native file versions, signatures and PDFs were
verified exactly. Production image, diagram, SBOM and vulnerability gates passed.
Local frontend validation passed 849 cases; combined authoring passed 196 cases;
the final contract correction passed all 62 owner/authoring/file-migration cases.
Both source reviews are clear. Commit-bound artifacts and digests are verified.
The task record preserves the first contract failure and two intermittent browser
failures. The template-copy and WebKit dialog cases passed unchanged local and
hosted replays; their timing causes remain unknown and require follow-up before
aggregate 1.0 acceptance. No causal fix is claimed for those unchanged retries.
Version remains 0.9.18 development. No deployment, release/tag publication,
production export or existing-data change occurred. Configuration and final
clean-start acceptance remain next; the six optional migration gaps stay deferred.
Wiki/status closeout edits remain local post-push records.

## Native staff and client publication controls after discovery/export

The [native publication slice](../git-native-publication-interface.md) connects
new Git-only documents to snapshots, staff/client publishing, corrections,
withdrawal, history and retained PDF downloads. Staff decisions are append-only;
client delivery retains independent approval and exact-client authorization.
Verified November 3: remote main `a598cf003790f495d15a0a408223c300b9b10731`
passed [Build 41591436635](https://github.com/hkrewson/TekDocs/actions/runs/41591436635)
on attempt 2 and [CodeQL 41591450327](https://github.com/hkrewson/TekDocs/actions/runs/41591450327)
and [Extended 41591452633](https://github.com/hkrewson/TekDocs/actions/runs/41591452633)
on attempt 1. All twenty database groups, 89% combined backend coverage, all
twelve real browser/server journeys without retries, production-image scans,
supported upgrades and independent encrypted restore passed. Local frontend
validation passed 818 tests, coverage, lint, types and bundle checks. Both source
reviews are clear. Downloaded commit-bound upgrade/recovery/diagram receipts and
browser evidence were verified against GitHub artifact digests.
The task record retains unsuccessful attempts, the reproduced/fixed upload-test
synchronization defect, and the unconfirmed startup/template timing failures;
passing unchanged replays are not claimed as causal fixes for those timings.
Version remains 0.9.18 development. Migration 0219 remains unapplied to retained
development data; no deployment or existing-document change occurred. Primary-file
controls and configuration remain later bounded slices; the six automatic-migration
gaps remain deferred. These results do not establish aggregate 1.0 acceptance.

## Git-native discovery/export correction after the clean-start audit

The [bounded discovery/export correction](../git-native-discovery-export.md)
reproduced omission of native-only documents before fixing the library and
cross-checked Markdown inventory. Native selection now opens the repository
editor; fragments and archived legacy shadows are excluded from new-document
fallback. Local aggregate/runtime, nine discovery, thirteen exporter, 104
component and ten real browser/server journeys passed; both source-review axes
are clear. Verified November 2: exact source
`b716026742e513c94dbaaf65a5c30a2cf8d2c3ce` is on remote main and passed
[Build 41562895300](https://github.com/hkrewson/TekDocs/actions/runs/41562895300)
and [CodeQL 41562938749](https://github.com/hkrewson/TekDocs/actions/runs/41562938749)
on attempt 1. All 20 database groups and 89% combined coverage passed. All ten
live publication journeys passed without retries and server verification passed.
[Extended 41562941477](https://github.com/hkrewson/TekDocs/actions/runs/41562941477)
completed successfully on attempt 2: attempt 1's diagram fixture render failure
remains unexplained after a passing exact local replay, 34 surrounding tests and
100 required synthetic renders. The unchanged-source upgrade retry passed; no
application fix is attributed to that retry. Commit-bound upgrade, independent
recovery and diagram receipts were downloaded and verified. The task record and
failure ledger retain artifact identities, hashes and unsuccessful attempts.
No existing data or schema was changed, no production export/deployment occurred,
and version remains 0.9.18 development. These results do not establish aggregate
1.0 acceptance or reopen the six deferred migration gaps.

## Cross-Workspace reuse and remaining-gap audit after 0.9.18

Current scope revision, November 2, 2026: the maintainer chose a clean Git-backed
start with manual document copying/recreation. The six remaining automatic
legacy-migration gaps are deferred, not 1.0 blockers or completed closures.
Existing data remains intact. The [current closeout plan](../1.0-closeout-plan.md)
orders manual-copy review, Git-backed workflow validation and final candidate
acceptance. The development and CI records below retain their historical scope;
this planning decision neither changes release status nor waives recovery gates.

The maintainer authorized the [remaining migration audit](../migrations/remaining-migration-audit.md),
starting with [cross-Workspace reuse](../migrations/cross-workspace-reuse-migration.md),
preserving signed publications, PDFs and file versions with isolation, rollback
and recovery. [Development notes](cross-workspace-reuse-migration-notes.md) record
the reproduced library/listing, compound publication, source projection and
read/write isolation gaps. Implementation, both source-review axes, 704 combined
Docker cases and nine final real browser/server journeys passed. Deliver this
reviewed continuation directly to main; exact-source Build, CodeQL and Extended
artifacts provide its hosted validation record. Version remains 0.9.18.
Source-bound hosted upgrade and independent encrypted restore are required;
historical release acceptance does not stand in for this development source.

Follow-up source `b8afcca6` passed Build 41479545080 and CodeQL 41479558453.
Extended 41479563043 passed its browser, performance, DAST and supported-upgrade
jobs but failed supported recovery. The [recovery follow-up](cross-workspace-recovery-follow-up.md)
records the reproduced baseline-timing defect and corrected-source validation
requirements. The [immediate 1.0 plan](../1.0-closeout-plan.md) now orders manual
document copying, Git-backed workflow validation and candidate acceptance;
the distinct interface rework is the first post-1.0 priority.

Corrected runtime `3e275779` passed CodeQL 41499022087 and all of Extended
41499026415, including independent encrypted recovery and supported upgrades.
Build 41499000231 repeated a core-a capacity cancellation and a live-browser
loading assertion in attempts 1 and 2. The follow-up preserves both unsuccessful
attempts and original timing uncertainty. Local corrections split the complete
core-a test set under the same job/coverage limits and synchronize functional
browser checks with completed scoped Git reads. All nine final browser/server
journeys, privacy/selection checks, lint and types passed; corrected-source
hosted validation follows the next authorized push. No production data or
permission behavior changed.

Verified November 2: follow-up HEAD `64bb580534e326717dcb725594316d995b511947`
passed [Build 41518555143](https://github.com/hkrewson/TekDocs/actions/runs/41518555143),
[CodeQL 41518952177](https://github.com/hkrewson/TekDocs/actions/runs/41518952177) and
[Extended 41518956667](https://github.com/hkrewson/TekDocs/actions/runs/41518956667)
on attempt 1. Exact-source upgrade and independent encrypted-recovery receipts
were downloaded and checked. All nine live publication journeys passed with
zero retries. The [clean-start workflow audit](../git-backed-workflow-audit.md)
records artifact identities and limits: migrated journeys do not establish
complete Git-native interface coverage. A fresh local Docker probe reproduced
native main-library omission and legacy-route 404s. Those findings do not reopen
the six deferred migration gaps or authorize production changes. No new release
or aggregate 1.0 acceptance is claimed.

## Repeated shared-block migration development after 0.9.18

The maintainer authorized [#105/#106 repeated shared-block migration](../migrations/repeated-shared-block-migration.md),
including distinct pins, retained signed publications/PDFs/file versions and
verified rollback/recovery. Commit and push directly to main after validation.
Implementation, both source-review axes, 644 broad Docker cases, 17 final cases,
795 frontend cases and eight real browser/server journeys passed. Exact-source
hosted upgrade and independent restore remain mandatory. Version remains 0.9.18. Historical release
acceptance does not substitute for exact-source development validation.

## Published 0.9.18: client-published migration

Application `81fed48fd2d4810542af43e703f5842589ed0ff4` passed
[Build 41362859970](https://github.com/hkrewson/TekDocs/actions/runs/41362859970)
on attempt 1, including reusable CodeQL/Extended gates, eighteen database groups,
89% coverage, 795 frontend cases, seven live publication journeys, all five browser
configurations, supported upgrades and independent encrypted recovery. Four tested
images were published and all eight attestations verified. CI delivered v0.9.18
and receipts/v0.9.18 atomically; receipt commit is
`b36334b1b8fa860dead425461eb4517188a4b36c`. Independent read-only checks reconciled
both tags, exact artifact/Git receipt bytes, sole parent/path, verification identities
and all four registry version/commit aliases. The
[candidate notes](0.9.18-candidate.md) and [source review](0.9.18-source-review.md)
retain preparation and bounded maintainer risk acceptance. Production deployment,
live-data migration and final 1.0 acceptance remain separate. The pinned manifest
still names historical 0.9.12 evidence.

## Client-published migration development after 0.9.17

The maintainer authorized the [#105/#106 client-published slice](../migrations/client-published-document-migration.md),
including MSP-only and client-only sections. Preserve client access, signed
publications, PDFs and all file versions; verify portal workflows, isolation,
rollback and independent recovery. [Development notes](client-published-migration-notes.md)
and ADR 0121 define the bounded behavior. Implementation, both source-review axes
and local validation passed: 623 combined Docker cases, ten final portal/edge
cases, 795 frontend cases and seven real browser/server journeys. Exact-source
Actions checks and commit-bound artifacts on the feature commit following
`34f7b864` establish hosted Build, CodeQL, fresh/0.8.46 upgrade and independent
encrypted recovery. These are delivery gates, not an operator-requested follow-up.
Version remains 0.9.17; release preparation and production changes are
separate. Existing risk decisions and original unknown browser causes remain open.

## Post-publication 0.9.17 CI investigation

The subsequent closing run `41325634983` passed workspace notifications but failed
publication acceptance. The [publication follow-up](0.9.17-publication-ci-follow-up.md)
records a reproduced premature server shutdown and the bounded coordination fix.
The delayed HTTP replay, six browser/server cases and standard publication Make
gate passed locally; both source-review axes are clear. Exact-source hosted
validation is required after push.

The later documentation commit `1d903780` failed the workspace browser gate in
[Build 41282154536](https://github.com/hkrewson/TekDocs/actions/runs/41282154536):
the client inbox stayed empty for the original 75-second notification assertion.
The [follow-up](0.9.17-portal-notification-follow-up.md) preserves that unknown
cause, passing unchanged local replays and the reproduced loss of worker evidence.
The bounded correction adds failure-only service/task/count diagnostics before
teardown; it makes no application-fix claim. The complete unchanged baseline retry
passed on attempt 2. Exact diagnostic source `844d3673` passed
[Build 41322102488](https://github.com/hkrewson/TekDocs/actions/runs/41322102488)
on attempt 1, including all seventeen database groups, 89% coverage, 793 frontend
cases, the workspace and five publication/server journeys, production-image
rehearsals and scans. All original assertions and deadlines are unchanged. Causal
diagnosis of the original notification failure remains blocked by lost evidence
and no reproduced recurrence. Published release identities below are unchanged;
later evidence-only commits make no new application-validation claim.

## Published 0.9.17: migration consolidation

The [0.9.17 release notes and risk decision](0.9.17-candidate.md) consolidate the
completed file, shared-block, enrolled-template, field/content-key, diagram and
monitored-source slices. The [publication closeout](0.9.17-operational-closeout.md)
records exact application `835c4ff4`, successful
[Build 41275992112](https://github.com/hkrewson/TekDocs/actions/runs/41275992112)
attempt 2, four published images, eight attestation verifications and automatic
application/receipt tag delivery. Receipt commit is `63225d49`; independent
read-only checks reconciled both tags, receipt contents and all four registry
version aliases. The updater receipt needs no manual follow-up.

All seventeen database groups, 89% combined backend coverage, 793 frontend cases,
five browser configurations, five real publication journeys with server custody
checks, supported upgrades and encrypted recovery passed on the exact release
source. The performance retry passed four constrained-browser cases without
browser retries after an MCR image retrieval failure. Successful source checks
retain attempt-1 evidence; performance and delivery have attempt-2 provenance.

Initial source `524d1d75` failed two live journeys twice. The reviewed
[diagnostic follow-up](0.9.17-live-validation-follow-up.md) preserves those unknown
causes and adds bounded failure-only timing evidence without weakening checks.
The [failure ledger](validation-failures.json) retains every failed attempt;
recurring browser stability and separate tooling findings remain 1.0 obligations.
The maintainer's bounded CSP/COEP/KaTeX decision is unchanged. Production deployment,
live migration and Wiki publication remain separate.

## Monitored-source development after 0.9.16

The maintainer authorized the [monitored-source #105/#106 slice](../migrations/monitored-source-publication-migration.md)
to preserve settings, observations, local edits, signed publications, PDFs and
every file version. The bounded implementation adds reviewed current-Git apply,
local-edit protection and promoted-reader controls. [Development notes](monitored-source-migration-notes.md)
describe the behavior. Both source-review axes and five live browser/server
journeys passed. Local validation passed 656 combined Docker cases, 34 final
source/transport cases and 793 frontend cases. Exact runtime `6c3824c6` passed
[Build](https://github.com/hkrewson/TekDocs/actions/runs/41243680921) and
[CodeQL](https://github.com/hkrewson/TekDocs/actions/runs/41243682650), including
all seventeen database groups, 33 monitored cases, 89% backend coverage and five
live publication journeys. Hosted fresh/0.8.46 migration and exact encrypted
recovery passed in [Extended validation](https://github.com/hkrewson/TekDocs/actions/runs/41243684051);
attempt 2 passed after an unchanged mobile Chromium retry. The slice record retains
the original Alpine package-index TLS failure before browser assertions and the
original attempt-1 upgrade/recovery packet identities. The bounded slice is
complete; later evidence-only commits make no new runtime claim. Version remains
0.9.16; no release, deployment or production migration is claimed.

## Diagram development after 0.9.16

The maintainer authorized the [diagram-bearing #105/#106 slice](../migrations/diagram-publication-migration.md),
preserving source revisions, signed graphics, PDFs, file versions, rollback and
recovery. Implementation, both source-review axes, local Docker validation and
all four live-browser/server journeys passed. Exact runtime source `5b7a9314`
passed [Build](https://github.com/hkrewson/TekDocs/actions/runs/41228928621),
[CodeQL](https://github.com/hkrewson/TekDocs/actions/runs/41228934806) and
[Extended validation](https://github.com/hkrewson/TekDocs/actions/runs/41228937218),
including all sixteen database groups, 33 diagram cases, 89% backend coverage,
fresh/0.8.46 migration and independent encrypted recovery of diagram revisions,
signed graphics, file versions and PDFs. [Development notes](diagram-migration-notes.md)
describe the bounded behavior. The slice is complete; version remains 0.9.16.
No release or production migration is claimed. Later evidence-only commits make
no new runtime claim.

## Content-key development after 0.9.16

The maintainer explicitly included content-key block substitution in the
[next #105/#106 continuation](../migrations/content-key-publication-migration.md).
Implementation, both source-review axes, 65 focused Docker cases and all three
real browser journeys with server-side custody/rollback verification have passed.
The final combined Docker regression passed all 496 cases. Exact runtime source
`781f1ad` passed [Build](https://github.com/hkrewson/TekDocs/actions/runs/41213064315),
[CodeQL](https://github.com/hkrewson/TekDocs/actions/runs/41213066706) and
[Extended validation](https://github.com/hkrewson/TekDocs/actions/runs/41213068455),
including all fifteen database groups, 89% backend coverage, three live publication
journeys, fresh/0.8.46 migration and independent encrypted recovery. [Development notes](content-key-migration-notes.md) describe the
bounded behavior and exact-source custody evidence. The bounded development
slice is complete; version remains 0.9.16. No release or production migration
is claimed. Evidence-only closeout commits make no new runtime claim.

## Field-key/entity development after 0.9.16

The [addressed-document slice](../migrations/key-entity-publication-migration.md)
extends internal migration to exact-Workspace portable field keys and typed
record links. [Development notes](key-entity-migration-notes.md) describe current
values, frozen snapshots and readable bindings. Implementation, source review,
local Docker/browser checks and exact-source hosted validation are complete.

Runtime `6ce9519` passed [Build](https://github.com/hkrewson/TekDocs/actions/runs/41185521728),
[CodeQL](https://github.com/hkrewson/TekDocs/actions/runs/41185526785) and
[Extended validation](https://github.com/hkrewson/TekDocs/actions/runs/41185528840),
including 72 key/entity cases, 89% backend coverage, all browser groups,
fresh/0.8.46 migration and exact encrypted recovery of bindings, file versions,
signatures and PDFs. ADR 0117 records the bounded custody decision. The slice
retains the reproduced fixture MFA correction, earlier unexplained WebKit failure
and open development-tool advisories; passing the retest does not establish the
original WebKit cause. Evidence-only closeout commits make no new runtime claim.
Version remains 0.9.16; no release, deployment or live production migration is claimed.

## Template enrollment development after 0.9.16

The [template enrollment slice](../migrations/template-enrollment-migration.md)
extends migration to MSP sources and enrolled client documents together. Its
[development notes](template-enrollment-migration-notes.md) describe creation,
reviewed updates, local copies and retained history. Implementation, both source
review axes and local Docker/browser validation are recorded in the slice.
Runtime source `4bb6bdd` has the exact-source hosted receipt linked below;
evidence-only closeout commits make no new runtime claim. Earlier release runs
cannot substitute for those checks. No new release or deployment is claimed.
ADR 0116 records the bounded library-custody decision.
The first `d80983c` hosted attempt exposed settings, transaction-fixture, heading
locator and restored-network harness defects. Their reproduced corrections and
original failed runs are retained in the slice record and failure ledger; the
corrective source requires its own complete hosted receipt.
The second attempt verified exact encrypted template recovery, then exposed a
separate foundation-fixture transaction failure, a core-shard capacity limit and
a template-apply browser synchronization defect. Reproductions and corrections
are recorded in the slice; the original hosted apply timeout cause remains unknown.
Subsequent validation added required template test partitions and stronger write/URL
checks, which reproduced and fixed a completed-creation navigation-guard race.
Exact runtime source `4bb6bdd` passed [Build](https://github.com/hkrewson/TekDocs/actions/runs/41169545095),
[CodeQL](https://github.com/hkrewson/TekDocs/actions/runs/41169552546) and
[Extended validation](https://github.com/hkrewson/TekDocs/actions/runs/41169552522), including all
109 template cases, 89% merged backend coverage, real browser/server verification,
fresh/0.8.46 migration and independent encrypted recovery. The bounded slice is
validated; later evidence-only commits carry no new runtime claim.

## Shared-block development after 0.9.16

The [shared-block migration record](../migrations/shared-block-publication-migration.md)
tracks same-Workspace live/pinned references, atomic live dependency groups,
signed history/PDF custody, rollback and recovery. See its exact-source validation
boundary before treating it as accepted. No version, image or production change
is part of this slice. The [development release notes](shared-block-migration-notes.md)
describe the supported behavior.
Exact source `3495d96` passed [Build](https://github.com/hkrewson/TekDocs/actions/runs/40985517155),
[CodeQL](https://github.com/hkrewson/TekDocs/actions/runs/40985578137) and
[Extended validation](https://github.com/hkrewson/TekDocs/actions/runs/40985580577),
including fresh/0.8.46 signed-document migration and independent encrypted recovery.
The slice record retains the original rehearsal media-loss failure and its
reproduced correction. Later closeout-only commits carry no new runtime claim.

## Published 0.9.16: bounded internal Git publication

Subsequent development: the [file-backed migration slice](../migrations/file-backed-publication-migration.md)
adds managed files and all primary versions to the bounded internal workflow,
with immutable signed history, retained PDFs, rollback and recovery validation.
It does not change the 0.9.16 release images or production authority. Its own
validation record distinguishes local runtime checks from hosted recovery.
The [development release notes](file-backed-migration-notes.md) describe the user
behavior without relabeling the published version.
Exact-source validation at `d85f574` passed [Build](https://github.com/hkrewson/TekDocs/actions/runs/40814940764),
[CodeQL](https://github.com/hkrewson/TekDocs/actions/runs/40814961602) and
[Extended validation](https://github.com/hkrewson/TekDocs/actions/runs/40814959514).
The slice record retains the original BuildKit failure, unchanged successful
retry and evidence attempt boundaries.

The [0.9.16 publication closeout](0.9.16-operational-closeout.md) records successful
[Build 40637961760](https://github.com/hkrewson/TekDocs/actions/runs/40637961760)
at `0ebb981`, four images, eight attestation verifications and both application
and receipt tags. It retains the bootstrap correction and unchanged timeout
retry. The [candidate packet](0.9.16-candidate.md) contains release notes and the
maintainer's risk decision; the [source review](0.9.16-source-review.md) is separate.
Production remains on 0.9.15; Wiki publication and live migration remain separate.

The [publication interface slice](../migrations/git-publication-interface.md)
connects supported promoted documents to internal publishing, corrections,
withdrawal, retained history and PDF downloads. It adds Git-aware readiness and
browser coverage without changing the version or production authority.

The subsequent [publication-history migration slice](../migrations/publication-history-migration.md)
adds guarded import/promotion of intact internal history, legacy-to-Git
supersession and mixed-history rollback/re-promotion. Source `aa2cd43` passed [main CI](https://github.com/hkrewson/TekDocs/actions/runs/40460675424)
and [Extended validation](https://github.com/hkrewson/TekDocs/actions/runs/40460698493),
including independent encrypted recovery and supported upgrades. The linked
closeout distinguishes those results from aggregate release acceptance.
These earlier slice records precede the aggregate 0.9.16 publication above;
they do not claim a live migration.

The [CI follow-up](2026-10-26-publication-ci-follow-up.md) repairs synthetic-owner
MFA setup in recovery and resource-sensitive network property generation.
Original failed runs remain recorded; this is subsequent validation work.

The [internal publication lifecycle](../migrations/internal-git-publication-lifecycle.md)
adds signed current-Git snapshots and verified-v5-only rollback for an
already-promoted simple document. That preceding implementation kept legacy publication-history import/promotion
blocked; its hosted checks passed at `bef8c90`. The subsequent extension above
has its own validation boundary. The bounded work is now included in 0.9.16;
neither record establishes a production deployment.

## Publication-history diagnostic included in 0.9.16

The [read-only publication-history assessment](../migrations/publication-bearing-document-assessment.md)
adds value-minimized evidence to the existing staff migration-status route.
The diagnostic itself does not clear import/promotion blockers or implement
post-promotion publication parity. The subsequent slices and 0.9.16 release
above have their own evidence; no production migration is claimed.

## Prepared 0.9.15

The [0.9.15 candidate](0.9.15-candidate.md) packages the promoted-document reader
identity correction from `13c05fc`. The maintainer authorized preparation,
commit and a direct main release push. Candidate risk disposition and
preparation checks are recorded in the packet; publication must complete the
full single-push release pipeline. The pinned 0.9.12 manifest remains historical.

## Published 0.9.14; reader correction pending

PR #141 merged as `cc6a4c075eb0ffc69b1178c71046ad686314e6aa`.
[Build 40256015056](https://github.com/hkrewson/TekDocs/actions/runs/40256015056)
passed release CodeQL, extended validation and publication; application and
receipt tags were delivered. The [candidate packet](0.9.14-candidate.md) retains
the preparation context and subsequent production report.

The operator reported mostly successful production checks, but opening a
promoted guide from Documentation failed. The
[promoted-reader identity correction](../migrations/promoted-document-reader-identity.md)
is subsequent development, not part of the published images. Production
verification of that correction remains pending. The pinned manifest still
records historical 0.9.12 and must not be treated as later-candidate evidence.

## Published 0.9.13

[Build 40221980804](https://github.com/hkrewson/TekDocs/actions/runs/40221980804)
completed the required release jobs at `352abdc`, including CodeQL, extended
validation, production-image scans and publication. GitHub has both `v0.9.13`
and `receipts/v0.9.13`; see the [publication closeout](0.9.13-operational-closeout.md).
The [production follow-up](0.9.13-production-smoke-closeout.md) records the
operator's successful update and its evidence limits. The original
[candidate packet](0.9.13-candidate.md) retains its pre-publication review context.
The pinned 0.9.12 manifest is historical; no complete 0.9.13 security/status
manifest is claimed by this reconciliation.

## Published 0.9.12

The pinned manifest now identifies `b45a543`, published as v0.9.12 by
[Build 40055908733](https://github.com/hkrewson/TekDocs/actions/runs/40055908733).
All four images, eight signed provenance/SBOM verifications, application and
receipt tags were delivered by that single run. See
[publication closeout and update commands](0.9.12-operational-closeout.md).
The operator reported production document/asset checks on October 25; supplied
SVG and PDF exports also passed inspection. See the
[production follow-up](0.9.12-production-smoke-closeout.md) for evidence limits. The historical 0.9.11 and 0.9.9
records below do not describe the current release.

## Historical 0.9.11 publication

[Security maintenance](0.9.11-candidate.md) updates Node and rebuilds Mailpit
with a fixed Go toolchain. v0.9.10 was tagged but its Mailpit scan failed and
publication was skipped. The v0.9.11 publication succeeded; all four image
aliases and eight signed provenance/SBOM checks passed. The reviewed receipt and
[production update commands](0.9.11-production-guidance.md) are available.
Its standalone full publication-record assembly was superseded by the current
0.9.12 record. Retained 0.9.11 evidence remains historical.

## Published 0.9.9

The historical 0.9.9 candidate was f52b210. All three image
aliases and signed provenance/SBOMs were verified; all security and diagram
categories assembled. See [publication closeout](0.9.9-publication-security-closeout.md),
[operational validation](0.9.9-operational-closeout.md), and the
[accepted security decision packet](0.9.9-security-decision-packet.md).
Production deployment remains an operator action; use the
[update instructions](0.9.9-production-update.md).

The following 0.9.8 records describe the preceding production release and its
historical manifest; they do not replace the current 0.9.9 manifest.

## Released 0.9.8 access-fix candidate

Start with [0.9.8 operational closeout](0.9.8-operational-closeout.md) for the
current 05abb13 hosted results, later rehearsal fixes, accepted header risks and
remaining publication decisions. [Access candidate validation](0.9.8-access-candidate-validation.md)
retains the earlier access/compression and browser chronology.
The historical 0.9.8 candidate was 05abb13. All three image aliases
and signed provenance/SBOMs were verified; see the publication security closeout.
The operator completed production deployment and reported successful document/asset
smoke checks; see [production closeout](0.9.8-production-update.md). The reviewed Wiki is now published and its public pages verified; see
[Wiki review and publication](0.9.8-wiki-review.md). Application Wiki-link enablement
and authority handoff remain separate decisions.

## Status and evidence

1. Run `make release-status`. This performs read-only GitHub checks for the
   pinned workflow identities, checks their repository/workflow/commit and successful conclusion,
   validates the security record and expiry dates, and hashes local source reports.
   Hosted run identifiers must match the run attempt and evidence category.
   Production-image digests are compared with the exact run/attempt's downloaded
   evidence artifact; a missing, expired or mismatched artifact blocks verification.
   For single-push releases, all three identities name the same main-push run;
   successful CodeQL, extended and publication jobs are required explicitly.
   Offline `python3 scripts/release_status.py` deliberately reports hosted checks
   unverified and returns nonzero. An unavailable API is not a cached pass.
2. Read `blockers` and `remaining_release_actions` separately. Zero verification
   blockers does not mean tagged, deployed, or independently audited. Operator
   acceptance records the decision, not individual unperformed manual tests.
3. Freeze the tested application SHA. Record evidence in a later documentation
   commit without relabeling it as evidence for HEAD. For the current pipeline, authorize the versioned main push; CI tags its
   successfully tested SHA and delivers the receipt. Historical manual tagging
   is not the normal release path. Runtime changes require a new candidate and fresh
   complete validation; documentation alone does not manufacture a new tested SHA.

The historical `.github/automated-security-review.json` remains a template. Use
the manifest's `security_record`, not that placeholder, for the current candidate.
The existing strict validator and ten-category assembler remain authoritative
for record structure. The status verifier adds reference checks; it does not
prove the reviewer was correct or independently authenticate every hosted artifact.
Production-image evidence is downloaded for identity comparison. A dependency scan
retained from an earlier partial-run attempt additionally requires its exact-source
successful job and original artifact bytes. Other hosted categories verify
run/attempt/category identity, not artifact bytes.
Review dispositions and broader artifact provenance
remain review work, not assertions inferred from green workflow execution.

## Local release-gate composition

`make release-gate` runs current-destination validation, including the supported
minor-version upgrade matrix, file/diagram upgrade, supported encrypted recovery,
repository-foundation acceptance and recurring-invoice restore. Existing current
feature rehearsals, security, browser, production-image and clean-install checks
remain part of the aggregate.

Seven historical checkpoint targets remain available separately, with their
original destination guards. They are excluded from the current aggregate:

| Historical target prefix | Required destination |
| --- | --- |
| `client-portal` | 0.5.2 |
| `outbox` | 0.5.4 |
| `notification` | 0.5.7 |
| `publication-control` | 0.5.1 |
| `key-publication` | 0.9.0 |
| `placement-audience` | 0.9.0 |
| `monitoring` | 0.7.13 |

Each is still invoked as `make <prefix>-upgrade-rehearsal` at its appropriate
historical checkout. Their precise historical fixtures are not claimed as current
migration coverage. Current support is defined by the retained supported matrix
and current feature rehearsals, plus PostgreSQL migration and isolation tests.
The aggregate's command-plan regression rejects reintroducing these incompatible
targets and requires the current upgrade/recovery boundaries.

A passing command plan proves composition, not runtime success. Record actual
Docker gate outcomes separately. Publication attestations and security-risk
acceptance remain independent release requirements.

## Failed validation

Run `python3 scripts/ci_status.py --run-id RUN_ID` for a compact read-only summary.
Fetch logs only for named failed jobs. Extended validation adds a failure-summary
job assigning follow-up to the maintainer for manual and scheduled failures,
including browser and diagram evidence generation/upload failures.

Track each failed run/job in `validation-failures.json` with `run_id`, `job`,
`owner`, `reproduction`, `cause` (explicitly `unknown` until established),
`next_action`, then `fix_commit` and `retest_run`. A tracked failure remains a
failure. Reproduce with the smallest existing gate before editing; retain useful
unfinished runs, run focused retests, then complete final candidate validation.
The workflow summary is not an issue notification service or a substitute for
the maintainer attending to scheduled failures.

Both recovery rehearsals call the same Linux bind-mount/free-space preflight
before provisioning. It tests an unrelated service UID reading one read-only
synthetic key beneath a private host directory, plus a 2 GiB minimum of Docker
filesystem space. This catches basic custody/capacity failures; it does not
estimate the full rehearsal's peak space or prune anything.

## Wiki publication

See [Wiki publication contract](wiki-publication.md) for the current draft,
validation and approval workflow. Local page/link validation does not publish the
Wiki or enable application links.

## Operator acceptance

Prepare a new disposable installation, using unused loopback ports:

```sh
python3 scripts/operator_acceptance.py prepare --directory artifacts/acceptance-next --port 3308 --mail-port 8108
python3 scripts/operator_acceptance.py check --directory artifacts/acceptance-next
```

Preparation builds current clean runtime source, creates a randomly named Compose
project and new volumes, and refuses an existing destination. It never chooses
the production or ordinary local project and never deletes existing data.
Backend networks are internal-only, frontend/Mailpit ports are loopback-only,
and workers/scheduler stay stopped. Local fixture actors use synthetic data;
owner MFA enrollment stays a normal human step. This is source-build acceptance,
not verification of registry-published images or real provider integrations.

Application and Compose overrides from the invoking shell are discarded. The
resolved project, ports, backend networks and named volumes are checked before
any service starts; Docker connection settings remain available to its CLI.

Setup and the read-only application verifier are separate. A successful check
generates `walkthrough.md` beside a private `access.txt`; never commit or upload
the acceptance directory. Readiness checks must pass immediately before handing
the guide to the operator. Failures leave the stack for diagnosis, not marked
ready; private command diagnostics must not be pasted into CI or chat. Check
does not reseed or repair application data. Changes made by the operator may
require engineering to revise the fixed-count fixture expectations.
Publication readiness invokes the current client portal read handlers and policy
checks for the fixture client, PDF, attachments and both retained primary-file
versions. Historical preparation response codes are not reused as readiness.
This does not exercise browser authentication/MFA; those remain human steps.

To rerun the opt-in live regression probes against a prepared disposable project:

```sh
TEKDOCS_ACCEPTANCE_TEST_DIRECTORY=artifacts/acceptance-next python3 -m unittest scripts/tests/test_acceptance_live.py -v
```

These simulate unavailable publication state/storage in-process without changing
the database or deleting files, then check that normal readiness still succeeds.

Use the named records and exact controls in that guide. Missing fixture,
environment, account or route is engineering work. Phone access, screen-reader
sessions, imported-provider provenance and outages require separate preparation.
Reviewers should reject a handoff whose guide has not been exercised against the
named environment. Record Pass/Fail/Blocked/Not run separately from the operator's
release decision. Keep credentials out of all acceptance records.

These process improvements are follow-up tooling, not new 0.9.8 acceptance gates.
