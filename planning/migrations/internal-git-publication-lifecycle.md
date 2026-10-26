# Internal publication after promotion: bounded lifecycle implementation

October 26, 2026. #105/#106 follow-up to the retained-history assessment.
Authorized scope: local implementation and validation. No commit, push, release,
production update or production authority transition is authorized by this work.

## Supported boundary

A migrated, already Git-authoritative ordinary document may create a permanent
internal STATIC snapshot when it has one owned fragment and no managed files or
unfrozen references. Client-visible publication, other retention modes, templates,
managed-file shapes, diagrams and unsupported references fail closed. This does
not enable importing/promoting the production publication-bearing legacy guide.
The existing frontend still hides publication controls for promoted documents;
this slice proves the backend service and existing authenticated POST route,
not complete end-user interface parity.

## Source and database contract

`publish_document` routes promoted documents to the bounded publisher before
legacy composition locks. It requires the established publication permission/MFA,
exact tenant and Workspace, active ordinary-document state and current Git index.
Git and repository state are pinned before locking the document, matching writer
and authority-transition lock order. The root and owned fragment are frozen at
one accepted commit; indexed text and composition digest must match that source.
Pending/rejected reviews and an approved digest that differs from the pinned Git
text refuse publication. Ordinary unreviewed text retains the existing internal
publication behavior; this is not a new blanket review requirement.

STATIC v5 signs the retained Markdown, sanitized HTML and exact Git dependency
proof, with a separately retained PDF. It has no synthetic legacy revision IDs
or claim that legacy placement revisions authored the snapshot. The existing
STATIC signing domain, crypto library, signature verifier and artifact custody
checks are reused; no new signing key or dependency is introduced.

Django migration 0196 preserves the v4 guards and adds v5 admission checks for
internal audience, empty legacy/key/file/reference projections, the exact owner,
current accepted/indexed repository head, root/fragment shape, source commit/blob
identities and Markdown checksum. Python model validation recognizes v5. No new
table or runtime permission grant is introduced. Source object validation remains
the pinned repository service's responsibility; SQL cannot independently read Git.

The signed source descriptor can be checked without live Git. Common publication
custody checks also validate v5 descriptors, so supported backup/recovery sweeps
include the new snapshots. Verification does not compare old snapshot text with
a later draft or require the live accepted head still to equal the old snapshot.

## History, controls and rollback

Publishing appends existing publication/artifact/control rows; it never rewrites
an older signed record. Supersession is limited to verified internal v5 snapshots
of the same document/Workspace with a supported lifecycle state. Existing
withdrawal controls apply and are covered by the lifecycle test.

Rollback may ignore the publication-history blocker only when every retained
publication is a verified v5 snapshot and the read-only history assessment also
passes, including metadata, ownership, control and supersession checks. The
existing reversible-shape projection still runs. All legacy or mixed publication
history remains blocked. Damaged PDF custody prevents rollback without changing
authority. After successful rollback the edited text becomes a new legacy
revision and all signed Git snapshots and control events remain unchanged.
Re-promotion of a now publication-bearing legacy document remains blocked; that
is not silently treated as an already solved migration case.

## Local evidence

The Docker lifecycle fixture imports and promotes a synthetic ordinary guide,
edits its owned fragment, calls the ordinary publication service, verifies the
Git text/commit, changes the text again, appends and withdraws a correction, and
rolls back. Both retained snapshots still verify afterward and the first digest
and Markdown remain unchanged. A separate authenticated POST test exercises the
existing API route, and a runtime-role test publishes inside its bound user scope.

Additional cases cover stale indexes, unsupported references/client audience,
permission/Workspace denial, corrupted PDF refusal before rollback, a direct
low-level stale-source insert rejected by PostgreSQL, and a guard migration
reverse/upgrade cycle that retains records and restores migration head in finally.
The new migration was also installed from a newly created test database inside
the existing database service. Development records were not replaced.

Verified: the serial combined selection passed 124 tests across migration
inventory, retained-publication assessment, the new lifecycle, runtime RLS, API
contracts, publication-read failures and ordinary document regressions. Log:
`/tmp/tekdocs-git-publication-serial.log`. The final focused lifecycle selection passed all 11 cases after the review-digest
and control-event timestamp checks were finalized. Log:
`/tmp/tekdocs-git-publication-final-lifecycle.log`. The runtime-role publication
and authenticated API route passed, as did stale-approval refusal. Ruff passed;
mypy reported no issues in 272 source files. Django reported no missing migration
state changes, and Docker schema generation had no drift, zero errors and four
existing operation-ID warnings. Frontend type/API-generation checks, all 120
tooling tests (three optional checks skipped), Wiki links and diff checks passed. The API and read-only assessment contracts
remain aligned with generated TypeScript.

Two runs were accidentally overlapped against the same test database during an
earlier pass. Bootstrap, permission-fixture teardown and a concurrent-export test
then conflicted. Recreating only the test database and running the entire selection
serially passed without changing those assertions or product code. Other fixture
corrections preserved the PostgreSQL error class/message and nullable-join lock
boundary; no authorization, integrity or concurrency assertion was relaxed.

## Required hosted recovery evidence

The existing repository-content recovery fixture now seeds a separate promoted
guide and signed v5 snapshot before encrypted backup. Restore verification checks
its text/signature/PDF, rolls that guide back, then rechecks the unchanged retained
digest and custody. It keeps the older reversible-edit fixture separate so retrying
restore verification need not bypass the legacy publication-history promotion guard.

This fixture extension is prepared, not a claimed successful independent restore.
The full `supported-recovery-rehearsal`, supported upgrade matrix, production-image
rehearsal and aggregate document-migration release gate create separate environments.
They must run in hosted CI under the repository's local-container policy. No local
exception, additional Compose project or data volume was created. The fixture is
syntax-checked locally; hosted execution must confirm its complete archive path.

## Disposition

Verified locally: bounded backend publication, exact-source freezing, retained
history, controls and rollback at the real PostgreSQL/storage boundaries.
Inferred: the extended recovery fixture covers that lifecycle after independent
restore; its actual hosted result is still required.
Blocked pending hosted evidence: independent encrypted recovery and full release
acceptance. Production remains on 0.9.15 and has not run this code.

Remaining #105/#106 work includes enabling import of intact legacy publication
history, supporting its post-promotion publication lifecycle, broader file/template
and client-delivery parity, and interface integration. No broad migration or 1.0
acceptance checkbox is cleared by this slice.

Hosted execution can use the existing manually dispatched Extended validation
workflow against main after an authorized commit/push. A same-version push alone
will not run release-only extended jobs because 0.9.15 is already tagged. Running
that validation does not authorize tagging/publishing a new release or production
update. The migration and full archive/restore fixture therefore remain subject
to that hosted result before a future release decision.
