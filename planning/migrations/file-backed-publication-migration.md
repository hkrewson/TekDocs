# File-backed document publication migration

Bounded #105/#106 follow-up to 0.9.16. The maintainer authorized implementation,
validation and a direct main commit/push. No production mutation or new versioned
release is included.

Acceptance: migrate the supported single-owned-fragment internal/permanent shape
with clean managed attachments and a complete primary-file version chain. Keep
file identities, ownership, paths, bytes, signed snapshots and retained PDFs
unchanged. Reject missing/corrupt/foreign/unscanned files and stale plans. Preserve
legacy writer retirement, supported Git body edits, explicit rollback and
re-promotion. Verify the same custody after recovery through the existing fixture
and required hosted independent encrypted restore.

Tests exercise existing migration/operator services, authorized file/publication
HTTP routes and the recovery verifier with real PostgreSQL/Git/private files.
Local runs reuse the standard Compose services with separate test databases;
additional-environment gates remain hosted. Templates, keys/entity dependencies,
diagrams, client delivery and broader structural edits remain outside this slice.

New file-bearing Git snapshots use a versioned manifest rather than changing
the meaning of signed v5 records. Existing publication formats remain verifiable.
Runtime bytes and workflow state remain outside Git. Validation and review
results will be recorded before delivery.

## Implementation contract

Import previews bind all active ordinary attachments and the complete primary
chain, including file identity, ownership, path, metadata and checksum. Preview,
apply and authority changes recheck custody; an added version invalidates a stale
plan. Existing signed legacy snapshots may retain attachment artifacts as well
as their PDF, provided their trusted signatures, exact owner and retained bytes
verify. Original snapshots need not equal today's draft.

New file-bearing Git publications use `tekdocs-static-publication/v6`. The signed
manifest binds every retained artifact to its source file, owner, purpose,
version and predecessor. The established count/byte limits apply to the complete
set; no file or older version is silently omitted. Readiness and publishing share
the same checks. Retained verification is independent of current Git and live
file state; current source files still require verified custody for migration.
Existing v4/v5 behavior and signed records remain unchanged. Migration 0197
installs the additive SQL guard with a reversible V5 predecessor.

Repository uploads for a promoted document retain the original durable Document
owner. Explicit rollback copies supported Git text changes to a new legacy
revision and keeps subsequent files downloadable. Body edits may link only the
same Document's verified files, including older primary versions. An oversized
set after promotion may roll back without loss, but cannot be published or
promoted again above the supported limits. Every other shape, authorization,
review, byte-custody and signed-history gate remains enforced.

## Reproductions and corrections

- File-backed promotion previously retained `publication_parity_required` and
  rejected ordinary Git publication. The supported mixed legacy/file-bearing
  v6 path now passes through the actual services and restricted-role HTTP routes.
- A blank-note primary-file document hit the Markdown-empty preflight blocker.
  Empty notes now require a verified frozen primary file; ordinary empty documents
  remain blocked.
- A post-promotion repository upload reached the database's legacy-owner guard
  without a Document link. New promoted uploads retain that exact durable owner.
- A SQL insert with omitted attachment projections reached the deferred artifact
  guard instead of rejecting the incoherent manifest itself. The v6 insert guard
  now checks the exact projection before artifact persistence.
- Review found that adding enough files after promotion could prevent rollback.
  The reproduced 51-file case now returns to legacy with all files downloadable;
  re-promotion remains refused without truncation.
- Three file-link cases reproduced valid-primary rejection and missing/foreign
  link acceptance. The reversible writer now accepts owned primary IDs and
  rejects missing/foreign references before advancing the accepted Git commit.
- The broad inventory test expected file-bearing publishing to fail. After the
  new behavior reproduced that failure, its assertion now requires v6, the exact
  complete retained file set and verified signed custody.
- Review identified that storage could write a new artifact and then raise
  before its name entered the cleanup list. The third-write fault reproduced an
  orphan after database rollback. The Git publisher now registers the opaque
  UUID path before writing, refuses an existing path and also tracks any returned
  alternate name. Failure-before-write and write-then-fail tests require no new
  publication row or file and intact original signed custody.

## Source review and risk disposition

The two-axis code review uses baseline `6e68459` and this bounded spec. The final
source patch was frozen as SHA-256
`33c226c9ddfb0777f4144ce260c5c35b42b3aabde0a6d9eac0da95bffebce307`.
Both reviewers checked the file-link guard, live browser fixture, recovery
verifier, storage correction and documentation read-only. Runtime validation
remains separate from those source judgments.

### Standards

No remaining source-level documented-standard breach. The new cleanup behavior
matches ADR 0026. One optional Data Clumps heuristic concerns the recovery
fixture's repeated five-part tuple; deferred as test maintainability. The
scanner-container execution violated the root container-reuse instruction and
is disclosed below; this is an execution breach, not an outstanding source defect.

### Spec

Two P2 findings were reproduced and corrected: adding files above snapshot
capacity could strand rollback, and storage could leave an orphan after a
write-then-raise failure. The 51-file and two storage-fault regressions verify the
corrections. The final follow-up found no remaining concrete Spec mismatch.

Review totals: Standards zero source defects, one execution breach and one
optional heuristic; Spec two P2 findings resolved, zero remaining findings.

### Risk boundary

No new dependency, grant, public endpoint or cryptographic primitive is added.
The versioned manifest extends existing Ed25519 signing and private storage.
Existing 0.9.16 CSP/COEP/KaTeX dispositions remain historical; this feature push
does not establish a new release acceptance or renew those decisions.

## Validation boundary

Local Docker runs reuse `tekdocs` and separate test databases in its existing
PostgreSQL service. The `document-migration-release-gate` constituents are adapted
to `compose exec`, avoiding the target's per-run containers. The full aggregate
also provisions independent upgrade/recovery/image environments; those portions
must run in hosted Build and Extended validation, not an additional local stack.

Execution deviation: the source-secret wrapper was run before its implementation
was inspected and launched a separate read-only Gitleaks container. It reported
no leaks and touched no application data. This violated the no-per-run-container
rule; it is not evidence of full local execution compliance. Runtime acceptance
and recovery fixture replay otherwise use the existing services.

The required Wiki update is prepared in the existing local Wiki checkout's
Documentation page, preserving maintainer changes. Public Wiki publication is
separate and no Wiki push is included.

Verified local and hosted results, exact source commit and remaining limits are
recorded below when each gate completes. No production mutation is authorized
or claimed by this development slice.

### Verified local checks

- Backend Ruff, strict mypy (273 source files), migration drift check and Bandit
  pass. No new model migration drift or security-analysis finding.
- OpenAPI regenerates byte-identically: zero errors, four existing operation-ID
  warnings. Existing HTTP contracts serve the added artifacts.
- Frontend lint, API/type checks, 774 tests across 127 files, production build and
  compressed bundle budgets pass in the existing frontend service.
- The actual extended recovery fixture passes under the restricted runtime role
  in the existing migrate/database services: create, repeated verify, refusal
  of missing ordinary and superseded-primary files, exact repair and re-verify.
  This is logical recovery-verifier replay (80.66s), not independent encrypted
  backup/restore; hosted evidence is required for the latter.
- Tooling tests pass (121 tests, three optional skips), as do version, pinned
  supply chain, local Wiki links, product/UI language, responsive-ledger and
  production Compose contracts. Version remains 0.9.16. Source-secret scan
  reports no leaks with the execution deviation disclosed above.
- Broad runtime validation passes 322 tests in 361.80s, covering content parsing,
  indexing/composition/reads/authoring, source validation, migration, publication,
  forced RLS, ordinary documents, recovery and API contracts. After the final
  storage correction, all 43 file-backed and Git-publication tests pass in
  47.18s, including both storage failure modes; Ruff/mypy/Bandit pass again.
- `make test-publication-browser-live` passes with the real restricted-role
  application and Chromium (18.475s, zero retries). It publishes v6, downloads
  both primary versions and the attachment with exact hashes, corrects legacy
  and Git snapshots, withdraws a successor, verifies history and old PDFs,
  checks denied actors and mobile layout, then verifies server-side rollback
  and re-promotion. Browser artifact hygiene and server verification pass.
  The harness restored the existing frontend/migrate services to stopped base
  configurations and removed its generated test database.

### Pending verification

Implementation was committed and pushed directly to main as
`ade9dbbda56acb6eddd10153c8f5732ab90cd6de`. No branch, PR, version or tag was
created; private ignored AGENTS files were not staged.

Exact-source hosted checks are running:

- [Build 40813776462](https://github.com/hkrewson/TekDocs/actions/runs/40813776462).
- [CodeQL 40813798595](https://github.com/hkrewson/TekDocs/actions/runs/40813798595).
- [Extended validation 40813797244](https://github.com/hkrewson/TekDocs/actions/runs/40813797244).

No hosted acceptance is inferred from source review or earlier release runs.
Independent encrypted backup/restore, supported upgrades and production-image
checks must confirm the pushed source. Production and public Wiki remain
unchanged. Subsequent evidence-only commits do not change this runtime source.

Hosted coverage correction: inspection found that the existing supported-upgrade
matrix omitted `document-migration-upgrade-rehearsal`, a constituent of the
strongest relevant aggregate gate. Extended validation now runs that existing
fresh/0.8.46-upgrade rehearsal before publishing upgrade evidence. Its script
creates isolated projects/volumes and is therefore hosted-only under the local
container rule. This is validation wiring; application source remains `ade9dbb`.
The earlier Extended run does not establish this omitted constituent.
