# Git-backed workflow audit for the clean-start 1.0 route

Date: November 2, 2026. Runtime source:
`64bb580534e326717dcb725594316d995b511947` (current committed HEAD).
Local planning and the uncommitted Markdown exporter were also inspected.

Scope: audit the six workflow categories in the
[1.0 closeout plan](1.0-closeout-plan.md), account for current evidence, and
produce a finite implementation/acceptance queue. No automatic legacy migration,
interface redesign, production operation or existing-data deletion is included.
The [six deferred migration gaps](migrations/remaining-migration-audit.md) remain
deferred. This audit does not reopen them or claim final 1.0 acceptance.

## Discovery correction follow-up

The [bounded discovery/export fix](git-native-discovery-export.md) follows this
audit. It reproduces both omissions before implementation, adds native summaries
and correct editor selection, and cross-checks/deduplicates both export
inventories. Local validation and source reviews are tracked there; exact-source
hosted checks are still required. The findings below retain the original audit
baseline. Native lifecycle/configuration work and final acceptance remain open.

## Finding

The core Git-backed implementation has substantial passing coverage, but the
clean-start interface is incomplete. Migrated documents retain a legacy
`Document` row; newly created repository documents need not have that row.
Several discovery, setup and lifecycle routes still require it. Passing a
migration journey therefore cannot prove that a newly created Git document can
complete the same task. Reuse the existing custody, publication and file APIs;
this finding does not justify rebuilding those systems.

## Verified evidence

The GitHub Actions API was checked against the full HEAD SHA, not a branch label
or the historical pinned 0.9.12 manifest. All three runs completed successfully
on attempt 1:

| Run | Evidence checked |
| --- | --- |
| [Build 41518555143](https://github.com/hkrewson/TekDocs/actions/runs/41518555143) | Static/frontend/security checks, PostgreSQL groups and combined coverage, live browser journey, Chromium regression and production-image scans passed. Image publication was skipped for this development source. |
| [CodeQL 41518952177](https://github.com/hkrewson/TekDocs/actions/runs/41518952177) | Python, JavaScript/TypeScript and evidence jobs passed. |
| [Extended 41518956667](https://github.com/hkrewson/TekDocs/actions/runs/41518956667) | Chromium, Firefox, WebKit, mobile Chromium/WebKit, performance, DAST, supported upgrades and supported backup/restore passed. |

Downloaded and checked source-bound upgrade/recovery receipts:

| Artifact | Checked contents | Downloaded ZIP SHA-256 |
| --- | --- | --- |
| `13177859970` | `scope_commit` equals HEAD; category `backup_and_restore`; status `passed`; immutable identifier `41518956667:1:supported-recovery` | `312652272227262a5567af0becf40b8705683856750e626282d031fc8d2f5b3c` |
| `13179847050` | `scope_commit` equals HEAD; category `upgrade`; status `passed`; immutable identifier `41518956667:1:supported-upgrades` | `850a3c7c229795c27c6d12b30f79e554d1a8126589cefd1da0d16929335d4025` |

Build artifact `13178806335`, `publication-live-summary`, reports all nine live
publication journeys passed, each with retry 0. Its ZIP SHA-256 is
`7032912562340a3c0ec1a4ebb06df5fbccc4a5540a317a7b3effe318fd4f8d48`.
Those journeys explicitly start with migrated content; they cover publishing,
corrections, withdrawal, keys, templates, diagrams, monitored sources, client
access and repeated/cross-Workspace reuse. They are strong preservation evidence,
not a clean-created equivalent of each journey
([journeys](../frontend/e2e/publication.live.ts)).

The native [repository browser journey](../frontend/e2e/repository-live-journey.ts)
does create a new Git-only document, save/reopen it, handle a two-tab conflict,
retain a draft, upload/link a file, verify the saved HTML download, reject a
foreign-Workspace lookup and check mobile layout/axe. It is called by
[live-workspace.spec.ts](../frontend/e2e/live-workspace.spec.ts:1339), whose hosted
live-browser job passed. It does not publish/correct/withdraw that new document.

## Fresh local Docker reproduction

Verified: `test_native_document_discovery_and_legacy_route_boundary` passed
**1 case in 53.49 seconds** using `docker compose exec` in the existing `tekdocs`
project. A generated, separate pytest database inside the existing database
service and temporary repository files isolated synthetic state from retained
development records. No additional container, project, service or volume was
created. The temporary probe was an audit instrument, not a permanent regression
or a fix; add maintained regression tests when implementing the correction.

Reproduction steps/assertions:

1. Reuse `test_content_authoring.authoring_context` and `_create` to author a new
   Git document; assert that no `Document` row exists for its content UUID.
2. Sign the fixture owner into Django's test client. Repository listing returns
   200 and includes that UUID; repository detail returns 200.
3. Ordinary `/api/v1/documents/search` returns 200 with count 0.
4. Resolve that UUID through ordinary document detail, key-binding list and
   publication list routes. Each returns 404. This verifies a route boundary,
   not an authorization bypass or absence of all native backend alternatives.

The source cause is `_search_document_records` narrowing repository identities
through `_filtered_documents`/legacy rows
([document_views.py](../backend/apps/core/document_views.py:366)); ordinary
`_document` requires those rows before dispatch
([lookup](../backend/apps/core/document_views.py:202)). The local exporter only
enumerates that search endpoint. Its simulated mixed-list tests cannot prove
real native enumeration. Its previous broad native-export claim was too strong:
**do not accept its success count as a complete document inventory yet**.

## Workflow matrix

| Workflow | Verified coverage to retain | Remaining clean-start acceptance |
| --- | --- | --- |
| Create/read/edit/organize | Native browser create/save/reload/conflict/file/export; API authoring/move/index/conflict tests; current hosted runs pass. | Reproduced native main-library omission and exporter enumeration gap. Prove new documents are discoverable through supported daily-work routes, with metadata/search and truthful stale-index states. |
| Reuse/templates | Composition APIs and migrated live/pinned/copy journeys pass. | Native source-template enrollment still resolves a legacy source row. Exercise newly created source/consumer documents, including live changes and fixed pins, through the intended interface. No pre-Git history import is required. |
| Keys/entities/diagrams/monitored content | Entity links and diagram fences have native Markdown/profile support; migrated key/diagram/source journeys pass. | Native binding authoring is excluded by the metadata allowlist and no-legacy-row key publication is blocked. Monitored-source settings require a legacy row. Prove native keys and source settings; add new-document diagram/entity acceptance rather than inventing a missing diagram subsystem. |
| Files/publications | Native attachments, native primary-file APIs, evidence/packaging/control/delivery APIs and retained artifact tests exist; migrated lifecycle browser journey passes. | Native repository editor exposes ordinary attachments and read-only evidence history. Connect primary-file versions and publish/correct/withdraw actions through a supported native UI path, retaining history/PDF and approval guards. |
| Client isolation | Existing native attachment scoping/API denials, repository foreign-scope browser denial, migrated audience/portal journey and hosted RLS jobs pass. | Extend the clean-native lifecycle journey to authorized client delivery, sibling/foreign denials, revoked access and withdrawal. Do not treat staff-readable content as portal publication. |
| Recovery/operational failure | Exact-HEAD hosted upgrade and independent encrypted-recovery receipts passed; source/index/file/signature custody mechanisms exist. | Carry the final native workflow fixtures through the candidate's maintained recovery gates. Existing passes establish their tested scope, not automatic coverage of later fixes or a live clean-start deployment. |

Detailed code/test citations and the six individual source findings are in the
[companion source audit](git-native-workflow-source-audit.md). Only the library
and older-route boundary above were freshly reproduced locally. The other
findings are **source-inferred readiness gaps**, not six reproduced runtime
failures. Reproduce each intended task before changing code to fix it.

## Finite next-work queue

Proceed in this order, in bounded fixes with their own acceptance; do not combine
all rows into one implementation patch.

1. **Native discovery and copy completeness.** First create a maintained mixed
   older/native fixture and reproduce the omission. Correct the supported library
   and export enumeration; prove exact Workspace/content identity, no duplicate
   fragments, partial errors and no overwrite. Exit: every intended current
   document is accounted for and a real API-backed export journey passes.
2. **Native daily-work completion.** Connect native publication lifecycle and
   primary-file version controls to the existing backend, one bounded slice at a
   time. Exit: a UI-created Git-only document completes publish, correction,
   withdrawal, history/PDF/file downloads and scoped portal access without
   creating a legacy document merely to unlock the interface.
3. **Native configuration completion.** Address keys, template enrollment and
   monitored-source settings separately, reusing existing semantics and policy.
   Exit: each is configured and used on new Git-only documents; freezing,
   live/pinned/copy behavior, local-edit protection and negative permissions are
   proven. No new product capability or automatic legacy-history reconstruction
   enters this queue implicitly.
4. **One clean-start acceptance journey and release freeze.** Recreate the few
   wanted documents after reviewed private copies. Prove the completed workflows
   and independent recovery on the selected candidate, then close human and
   security acceptance. Existing data stays intact throughout; production
   operations require separate explicit authorization.

Engineering owns items 1–3 and automated candidate evidence. The maintainer owns
review of actual document copies, human walkthroughs, risk decisions and the
release decision. No user preparation is needed to start item 1.

## Pending release obligations, not new migration projects

- No 1.0 candidate is frozen by this audit. The pinned candidate manifest is
  historical 0.9.12 evidence and must not be relabelled as 1.0 acceptance.
- `planning/responsive-layouts/acceptance.json` still has a pending aggregate
  release gate and pending human reviews for all four Workspace rows: assets,
  contracts, networks and documentation/files. Reconcile the applicable current
  walkthroughs with the final candidate; do not mark them passed from CI alone.
- The 0.9.18 CSP/COEP/KaTeX risk decision is bounded to that runtime candidate and
  the next-candidate/November 12 limit
  ([decision](releases/0.9.18-candidate.md:90)). It is not a 1.0 waiver. Current
  dependency/build-tool findings and new candidate scans need their own
  disposition; this audit performs no fresh vulnerability scan.
- Actual production copies, manual recreation and live cutover have not been
  performed. No production inspection, source export or deletion occurred.
- The broad interface redesign remains first after 1.0; functional accessibility
  and usability defects in the supported workflows remain acceptance work.

Closeout: **verified** source inspection, exact-HEAD hosted run/receipt checks and
one fresh Docker boundary reproduction; **inferred** the remaining native setup
and interface gaps; **pending** their reproductions/fixes and final human/security
acceptance. No runtime implementation, schema, OpenAPI, permission policy or
retained data was changed. The audit is complete; the implementation queue is not.
