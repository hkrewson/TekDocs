# Template-backed document and enrollment migration

Bounded #105/#106 continuation, authorized October 29, 2026. Preserve template
lineage, selected revisions, local client edits, existing signed publications,
PDFs and supported managed-file versions. Verify update previews, conflicts,
detach, rollback, recovery and fresh/upgraded behavior before closing the slice.
Continue the authorized direct-main workflow after validation; no new version,
production deployment or public Wiki push is included.

The checkpoint sections below preserve the investigation history. The final
validation section, when present, supersedes their outstanding-work lists.

The public testing boundaries are the existing copy/handoff operator services,
template instantiation/preview/apply/detach operations, authenticated APIs and real
browser journeys, plus the supported recovery and upgrade fixtures. Use real Git,
PostgreSQL and retained bytes in the existing local tekdocs services; separate
stack gates remain hosted-only. Implement one behavior and its red/green at a time.

Acceptance:

- Existing immutable template revisions, enrollment identity, applied revision,
  placement mappings, ownership and independently edited client content survive
  migration. Template/enrollment controls remain database authoritative.
- Copied, live and pinned section choices retain their meanings. MSP-to-client
  dependencies require explicit library visibility and exact tenant/client
  authorization; this does not authorize general cross-Workspace reuse.
- Promoted content reads and writes use Git. Preview/apply bind the reviewed
  source version and enrollment state; stale previews, conflicts and unauthorized
  sources fail without partial changes. Copied local edits are never overwritten.
- Supported template updates and detach preserve immutable source proof and
  allow rollback to the original owner graph. Retained publications and PDFs are
  not rewritten and remain verifiable independently of live Git.
- Existing publication, review, file custody, scope and source-freshness gates
  remain in force. Missing objects and unsupported shapes remain explicit blockers.
- Docker positive/negative, runtime-role and cross-client checks, browser journeys,
  rollback/recovery and normal reversible migrations agree with the API contract,
  architecture, roadmap, release notes and prepared Wiki change.

Keys/entity dependencies, arbitrary structural editing, general cross-Workspace
reuse, repeated Block occurrences, unrepresented legacy pins, client publication
delivery and final 1.0 acceptance remain separate work. These exclusions do not
permit converting live/pinned template references into independent copies.

Baseline: 7581b74. The preceding runtime source 3495d96 passed Build, CodeQL and
Extended validation; its record retains the rehearsal media-volume correction.

## First vertical checkpoint (incomplete)

The first copy-only enrolled-client case reproduced `publication_parity_required,
template_enrollment` before implementation. A read-only retained lineage verifier
now checks the applied immutable manifest/checksum, source revision custody and
exact copied placement mapping while allowing local destination text edits. Its
fingerprint binds import and authority previews. Copied client promotion, Git
editing, publishing and rollback preserve enrollment metadata and retained PDF
custody in the initial Docker test.

Additional real reproductions and corrections:

- Metadata-only enrollment advancement left an authority preview valid because its
  group fingerprint omitted enrollment evidence. The checksum now includes it.
- Under the restricted database role, an inner join to an RLS-hidden MSP source
  made an existing enrollment appear absent. Enrollment is now fetched separately;
  an unavailable source produces a blocker rather than losing lineage evidence.
- Two database connections reproduced a rollout committing enrollment changes
  after promotion: rollout had passed its unlocked legacy check. Rollout now
  locks the exact destination Document before its Enrollment, matching handoff.

Six focused Docker cases pass at this checkpoint. Standards and Spec review both
identified the concurrent rollout issue before its reproduction/fix. These results
are partial: promoted rollout/detach, Git-backed template sources, live/pinned
library dependencies, full browser/recovery/upgrade evidence and final review
remain required. No completed slice, commit, push or deployment is claimed yet.

## Confirmed source-and-client scope and library adapter checkpoint (incomplete)

The maintainer selected migrating MSP source templates and enrolled client
Documents together. Copies, LIVE and PINNED references keep their original
meaning. An explicit cohort preflight checks every named Workspace's central
edit/MFA policy, validates all immutable historical source revisions, includes
client-local edits in its fingerprint and refuses omitted live consumers.
The final authority transition must retain the global SQL hidden-consumer guard.

A typed optional `includes.library_workspace` UUID distinguishes an approved
foreign MSP template reference from an ordinary same-Workspace include. A trusted
adapter validates the actual scoped Enrollment and placement map before reading
one fixed fragment path through the existing Git custody service. It never uses
an unrelated same-ID client fragment or a database Markdown fallback. Migration
0201 adds a nullable projection field and validates the distinct foreign edge
against the current enrolled library source; ordinary include rules remain.

Repository bindings are already authorization control-plane records. A runtime
probe disproved an initial assumption that they were organization-hidden. An
uncommitted privileged descriptor function was removed after reversing it only
in the separate test database and restoring migration head; the implementation
uses existing scoped model reads and custody locks without that function.

The reader rechecks actual foreign Git custody even when the client's own head
has not changed. A changed LIVE source rebuilds the disposable client projection;
a pin keeps its selected commit. Revoked/archived or missing sources fail closed.
Existing database guards already forbid withdrawing library visibility while
client placements reuse the source; tests must exercise that rejection rather
than disable it to fabricate an impossible supported state.

Standards review found that a raw file-URI substring missed entity-escaped
Markdown links and rejected inert code examples. Both failures were reproduced;
the foreign-file boundary now uses the existing semantic attachment parser.

The next implementation path retains previously applied template snapshots under
service-owned non-Markdown paths in the MSP repository, preserving the immutable
TemplateRevision manifest and exact selected fragment bytes without creating
extra current ContentNode identities. Snapshot additions are resumable custody
preparation; authority stays legacy until the reviewed full cohort is ready.
Git-backed source edits must rebuild derived immutable workflow snapshots from
verified Git bytes before preview/rollout. Controlled apply/detach, offline
publication provenance, rollback, export, browser/recovery/upgrade validation and
final review remain required. No completed slice or external delivery is claimed.

## Git/SQL transaction integrity preemption (incomplete)

A real Docker request-middleware probe reproduced a database rollback leaving the
canonical Git head advanced: the database accepted pointer was absent while Git
still contained the failed request's commit (`advanced` reconciliation). The new
coordinated request/operator scope retains thread-bound filesystem locks through
the database outcome and restores refs after rollback. Reconciliation-recording
reads retain their locks too, avoiding a writer taking the filesystem lock while
waiting on an uncommitted repository row. Read-only foreign custody checks keep
their existing shared/read-only path.

Review found two additional failures, both reproduced before correction:

- A nested savepoint explicitly marked for rollback exited normally, so its Git
  change survived while earlier successful SQL committed. The nested scope now
  restores its own checkpoint for this outcome as well as raised exceptions.
- Existing post-commit workspace-manifest synchronization tried to enlist in an
  already committed coordinator. It now runs in a fresh coordinated operation;
  committed refs are never compensated because a later callback fails.

Copied contexts cannot keep using expired filesystem leases. Local coverage
includes late failure, explicit request rollback, caught nested failure, silent
nested rollback, callback failure after commit, normal manifest synchronization,
and an expired copied context contending with a real writer lock.

The combined earlier migration/publication/authoring/runtime-role regression
command completed successfully. Subsequent coordination/manifest regressions and
static checks are being rerun against the newer changes. These are foundation
checkpoints: full atomic source/client handoff, Git-derived source workflow
snapshots, controlled rollout/detach, foreign publication proof, rollback and
recovery/export/browser evidence remain unfinished. No commit or push has been
made for this slice.

## Cohort handoff and rollback checkpoint (incomplete)

An explicit reviewed handoff now leases every enrolled Workspace repository,
locks retained owners under exact authorized Workspace scopes, and binds accepted
Git heads, exported bytes, enrollment/source evidence, retained publication
history and review state. All roots stage together before fragment writers are
retired; the existing global hidden-consumer SQL guard remains in force. Prepared
historical/current copies remain resumable preparation, not an authority switch.

Docker reproductions added at this checkpoint:

- A caught ordinary Django savepoint failure left Git ahead of the committed
  database pointer even inside the coordinated outer request. Only repositories
  with a validated write attempt are now aligned to their final SQL accepted
  pointer before commit; reading/rejecting preexisting drift must not repair it.
- Matching content IDs and commit IDs in distinct Workspaces falsely triggered a
  composition cycle. Cycle identities now include the Workspace namespace.
- A source-only rollback left repository LIVE clients behind. Spec review also
  identified the inverse client-only rollback; that case was reproduced too.
  Migration 0203 defers the global LIVE authority-compatibility check until the
  complete transaction outcome, permitting whole-cohort transitions but rejecting
  either partial rollback without disclosing foreign document details.

Initial group promotion, full rollback, stale-preview and injected late-failure
cases pass. Runtime-role round trips, broader regressions and read-only review are
being checked against the latest changes. The full slice remains unfinished:
controlled promoted template updates/detach, independent-copy source retirement,
foreign offline publication proof, browser/recovery/export/upgrade evidence and
final documentation/risk alignment are still required. No commit/push was made.

## Publication and controlled-workflow checkpoint (incomplete)

Foreign template publications use a separate v8 STATIC manifest and v2 dependency
proof. Each selected foreign section records its Workspace/repository, selected
and accepted commits, object format, exact path/blob/content hashes, applied
immutable template revision/checksum and body-only expansion semantics. Earlier
v1-v7 formats keep their guards. Source and client repositories are leased in a
consistent order until signing completes. Live/pinned positives, offline custody
with Git storage unavailable, scoped runtime publishing and forged-source SQL
negatives pass at this checkpoint. Review identified a nullable SQL comparison;
a database truth-table probe confirmed NULL could evade the rejection expression,
and the v8 ordinary-source branch now uses a null-safe comparison. No supported
application path to the missing-authority state was demonstrated.

Copy-only enrollment verification uses its own immutable initial revisions and
its selected immutable definition, without requiring visibility of the current
MSP Document. Migration 0205 exposes only that scoped applied definition; later
private definitions and the source Document remain hidden. Copied attachment
URIs belong to client-owned files and deliberately differ from source IDs. Their
initial copy checksum, retained mapping and owned file identities are verified;
this retains lineage without asserting byte identity with an unrebound source.

A controlled pinned rollout passes with the restricted database role and
preserves independent Git edits in the client introduction. The exact-document,
thread-bound operation permits only the complete reviewed export dictionary to
change the protected graph. Migration 0206 checks the final graph/index and
selected enrollment definition at transaction completion. A temporary operation
lease without the matching Git projection cannot commit. Review found a setup
failure leaving the lease active in a later transaction; that failure was
reproduced, and cleanup now covers both SQL setup stages.

Opening a rollout preview creates an immutable workflow definition. A real
source-edit/rollout/rollback journey reproduced that new definition's missing Git
snapshot files blocking rollback. Returning to legacy now requires verified
current Git bytes and complete checksum-validated retained database revision
history, while permitting absent derived template-snapshot files. Git promotion
still requires all historical Git snapshots; corrupt retained definitions remain
blockers. Both normal and restricted-role journeys preserve local edits and the
selected pin through the full return to legacy.

Live and pinned detach now retain the exact selected body and enrollment identity.
A new immutable audit proof binds the selected source and its commit/revision/hash
to the new client-owned initial revision. A forged fork commit was reproduced as
accepted before this proof was added; its negative regression is now running.
API/UI controls, broader regressions, complete browser journeys, portable recovery
and upgrade evidence, required Wiki draft and final review remain unfinished.
Nothing from this slice has been committed or pushed.

## Interface, file cleanup and recovery checkpoint (incomplete)

The library now returns a bounded current-choice DTO instead of the complete
Document serializer. Git source creation binds a reviewed source/file definition;
missing/stale reviews are rejected. Promoted documents expose reviewed rollout
and local-copy controls. Missing source Git is a retryable conflict, and a private
source no longer breaks the list of independently copied enrollments.

Review findings reproduced and corrected in Docker:

- Two primary versions attempted duplicate destination version 1; copies now keep
  an ordered replacement chain. Source file versions remain unchanged.
- A later outer rollback left copied files orphaned. A second reproduction found
  the registration gap after the constructor returned. Each file now registers
  with the outer coordinator during creation. A post-commit callback failure
  preserves durably committed files. Failed cleanup attempts every independent
  artifact, records a value-free recovery error and preserves the primary error.
- A nested foreign section could be resolved from an incorrect root parent. The
  adapter, composition caller and SQL edge now bind the actual retained parent;
  legitimate nested LIVE/pinned migration and hoisting refusal pass together.

The 776-test frontend suite passed before subsequent accessibility changes.
Six API-mocked browser cases pass across Chromium, Firefox and WebKit at 320px and
1440px, including reviewed creation, denial/stale draft preservation, explicit
retry, detach, overflow and accessibility checks. These are UI evidence, not the
required real-API journey; that existing harness is being extended separately.
Assigned MSP contributor creation/detach passes under the restricted database
role. Existing client-portal policy remains read-only. Whole-repository recovery
into different Git/media roots preserves foreign compositions, signed manifests,
PDF bytes and recovery verifier results. A 0200-to-head schema upgrade round trip
preserves existing enrollments/publications and permits promotion/rollback.

The expanded migration gate is running. Full source review, exact-source hosted
upgrade/encrypted-recovery evidence, real browser acceptance, remaining negative
cases and final documentation/risk disposition are still pending. The prepared
Wiki page is a new uncommitted `Template-library.md` in the sibling Wiki checkout;
its pre-existing user edits were preserved. No Wiki publication, commit, push,
application release or production deployment has occurred for this slice.

## Operator procedure

Run the following through the existing installation's owner-role `migrate`
service, with the approved actor and exact Workspace/Document record UUIDs.
These are procedure examples, not authorization to run against production.
First create and authenticate a supported encrypted recovery set containing
PostgreSQL, all accepted repositories, private media and deployment keys; retain
the separate recovery key. Use the existing backup/restore procedure rather than
an editable ZIP. A single-Workspace ZIP cannot recover a foreign library cohort.

1. Inventory each exact Workspace with `inventory_document_migration --workspace
   <workspace-uuid>`. Resolve missing files, unsupported dependencies, publication
   custody or source visibility blockers before continuing. List the MSP source
   and every enrolled LIVE consumer explicitly; the hidden-consumer SQL guard
   rejects an incomplete transition. Include selected pinned/copy enrollments in
   the reviewed cohort rather than changing their semantics.
2. Copy the source first: `preview_document_migration --workspace <msp-uuid>
   --document <source-uuid>`, then `import_document_migration` with the same
   Workspace/Document, `--actor <actor-uuid> --base-commit <reviewed-base>
   --plan-sha256 <reviewed-hash> --apply`. Copying alone keeps legacy authority.
3. Review `retain_template_library_history --workspace <msp-uuid> --source
   <source-uuid> --actor <actor-uuid>`, then repeat with `--apply --plan-sha256
   <reviewed-history-hash>`. Repeat previews/applications until `missing_files`
   is zero and the retention result reports `indexed: true`. The bounded
   retention operation is resumable and does not switch
   authority. Never reuse an earlier hash after a source or repository change.
4. Preview/import each client Document in its own Workspace, using newly reviewed
   base commits and hashes as in step 2. Recheck copy parity and original signed
   publications/PDFs. Every supported file version must remain available.
5. Review `transition_template_library_authority --workspace <msp-uuid> --source
   <source-uuid> --document <client-document-uuid> --actor <actor-uuid> --authority
   repository`, repeating `--document` for every cohort member. Apply only a
   `prepared` result by repeating exactly those arguments with `--apply
   --plan-sha256 <reviewed-cohort-hash>`. A `blocked` response is a refusal;
   command completion alone does not establish migration success.
6. Verify Git reading, client-local edits, selected live/pinned bodies, reviewed
   updates/detach, all file-version downloads and retained/new publication PDFs.
   Keep the before/after enrollment identity and applied revision evidence.

For authority rollback, preview the same full cohort with `--authority legacy`,
then apply its new hash. Rollback projects verified current owned Git bodies back
into the original owner graph; it is not an old-content restore and does not
delete signed publications. Missing/corrupt retained history remains a blocker.
New derived template definitions may not yet have Git snapshots: returning to
legacy permits that gap only with verified current Git and complete retained SQL
history. Re-promotion requires running history retention again and reviewing a
new repository-authority plan. For storage loss, stop writes and use the complete
authenticated recovery set, then accepted-head reconciliation and the publication
and managed-file recovery verifiers before reopening writes. Never choose the
newest on-disk commit as authority.

## Final source review and nested-section reproduction

Separate Standards and Spec reviews found the same supported-shape gap at two
callers: a borrowed LIVE/pinned section beneath a client-owned section rendered
successfully but detach and publication passed the root Document to the strict
library adapter. Four new real Docker cases reproduced the parent mismatch.
Passing the actual retained parent fixed both detach cases; both publication
cases then reproduced the remaining v8 database guard's root-only edge lookup.

The final guard now explicitly distinguishes root from nested placements, binds
the actual client-owned parent ContentNode to the accepted/indexed repository,
and checks sibling order plus the retained proof's last ordinal. The full
composition manifest still binds the entire ancestry. The parent-hoisting denial
is retained. Both review axes found no remaining concrete defect in the repair.
All four new cases, the existing parent-hoisting denial and the 0200-to-head
upgrade round trip then passed together (six Docker tests). Seventeen subsequent
template publication/detach, restricted-role and forged-proof regressions passed.

## Final local validation and hosted delivery boundary

Verified on October 30, 2026, against the staged implementation in the existing
`tekdocs` project, with test records isolated inside its existing PostgreSQL
service:

- Expanded document migration, template enrollment/composition, runtime RLS,
  repository coordinator and manifest suites: **300 passed**.
- Authoring/profile/index/read, API contracts, document/taxonomy and existing
  Git/file/shared publication regressions: **281 passed**.
- Nested-section repair, parent denial and schema upgrade: **6 passed**; final
  affected template publication/detach and denial subset: **17 passed**.
- Frontend: **776 tests / 127 files passed**, lint, immutable API generation and
  production build/bundle budgets passed. Template/publication browser regressions:
  **18 passed** across Chromium, Firefox and WebKit at narrow/desktop sizes.
- Fresh test-database real browser-to-proxy-to-Django/PostgreSQL journey:
  **1 passed**, with **server verification passed**. It covers copied/live/pinned
  template reads, source Git editing, reviewed pinned update, detach, creation,
  both file-version hashes, original signed PDF hash, new v8 publication, rollback
  and re-promotion. The existing correction/withdrawal/read-only/anonymous journey
  remains included. Only the value-free browser summary is retained; generated
  sessions and the temporary test database were removed by the harness.
- Backend Ruff and mypy (**286 source files**), no migration drift, exact OpenAPI
  comparison (zero errors; four existing warnings), Bandit (zero findings), staged
  secret scan (zero findings), version/pin checks, **121 script tests** (three
  existing skips), Compose contracts, product boundary, UI language, responsive
  inventory/ledger and Wiki checkout/link checks passed.
- Standards review: **zero remaining findings**. Spec review: **zero remaining
  findings**. The actual red/green investigation above is retained rather than
  treating source inspection as reproduction.

Inferred: no production, manual acceptance or aggregate 1.0 completion is inferred
from these local results. Risk IDs and recurring obligations remain in the
[risk disposition](../../docs/ENGINEERING_RISKS.md#template-sourceenrollment-development-after-0916).

Blocked locally by the repository's single-project rule: the unmodified
`document-migration-release-gate` uses per-run containers in `check` and separate
projects in its upgrade/production-image rehearsals. Its applicable unit/static
components were executed with `docker compose exec` instead. Independent encrypted
recovery likewise provisions separate source/restore stacks, so it was not run
locally. **Build, test, and secure**, **CodeQL**, and **Extended validation** on the
containing commit must supply the hosted receipt, including fresh/0.8.46 document
migration, production-image checks and the extended encrypted template-cohort
recovery fixture. Passing workflow definitions or previous commits is not proof.

Delivery is one descriptive DCO commit directly to `main` under the maintainer's
authorization. No version change, application tag,
image publication, production deployment or live-data migration is included.
The required `Template-library.md` Wiki change is prepared locally; its separate
checkout's pre-existing edits are preserved and publication remains separate.
