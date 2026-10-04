# Version 1 transition work package

Status: complete; the immutable `0.9.0` database-first baseline is frozen
Prepared: 2026-10-02
Architecture input baseline: `35e93ca` at version `0.8.46`
Release baseline: version `0.9.0`, committed with this completed work package
Owning plan: [`v1-markdown-content-graph.md`](v1-markdown-content-graph.md)

## Outcome

The current 1.0 milestone is larger on GitHub than the remaining pre-transition
work in the repository. Most recurring-invoice and responsive-layout
implementation has retained code, test and runtime evidence but remains attached
to issues whose final shared human/security/release gates were never separated.

The correct next sequence is:

1. retain and close out the completed invoice void/credit boundary under issue #33;
2. close the already-evidenced current-model implementation issues after posting
   their retained evidence;
3. transfer storage-dependent Documentation work and final candidate acceptance
   to their named `0.9.x` slices; and
4. begin the bounded `0.9.1` local-repository foundation below.

This record was the evidence-backed input for the GitHub reconciliation applied
on 2026-10-03. The resulting milestones and issue owners are recorded below.

## Evidence vocabulary

- **Verified from retained evidence:** implementation and named validation are
  present in the repository. Those commands were not rerun while preparing this
  planning-only reconciliation.
- **Transfer:** the requirement remains valid, but validating it against the
  database-backed document model would create throwaway work. Its new owner is
  named explicitly.
- **Open blocker:** new implementation is still required before `0.9.1` begins.
- **Human/external:** completion requires a person, hosted system or final frozen
  candidate and cannot be inferred from source code.

## `0.9.0` milestone reconciliation

| Issue | Evidence-based state | Required disposition |
| --- | --- | --- |
| #30 structured topics | Verified from retained evidence at `0af8e7e`: topic schemas, conversion, guided authoring and preflight tests exist. | Close the database-model implementation checkpoint. Transfer frontmatter/schema indexing to `0.9.2`, Git authoring parity to `0.9.5`, and migration parity to `0.9.6`. |
| #31 publication preflight | Verified from retained evidence at `0af8e7e` plus later document/export validation. | Close the current dependency model checkpoint. Transfer Git link/dependency findings to `0.9.2` and exact Git-object publication proof to `0.9.7`. |
| #32 taxonomy governance | Verified from retained evidence at `a1c3df7`, the taxonomy test suite and the responsive metadata-administration checkpoint. | Close the governance implementation checkpoint. Taxonomy definitions stay database-authoritative; transfer file selections/indexing to `0.9.2` and migration proof to `0.9.6`. |
| #33 invoice boundary | **Implementation and recovery complete in the current worktree.** Privileged void-before-delivery and separately numbered, signed, immutable credit notes now use append-only lifecycle evidence without mutating the source invoice. Focused service, database, artifact, portal, authorization, OpenAPI, UI, migration-cycle, billing restore and supported encrypted recovery evidence passes. | Resolve the local product-boundary document mismatch, retain the final composed-gate result, and close the issue before `0.9.1`. Payment allocation, a ledger and mutable issued invoices remain excluded. |
| #38 security assurance | Human/hosted final-candidate work. | Transfer to `0.9.8`; run focused authorization, path, repository and recovery security tests in every earlier slice. |
| #39 pilots | Human/external final-system work. | Transfer to `0.9.8`. Pilot the migrated Git-backed system, not the superseded authoring store. |
| #40 hotspot decomposition | Verified in part: focused publication, file, template, review, source, authoring, reuse, key and export serializers plus source/template/key model seams are retained. | Close the behavior-preserving decomposition checkpoint. Stop mechanically extracting the retiring content aggregate; transfer repository/service/index/migration boundaries to `0.9.1`–`0.9.6`. |
| #60 interface review | Final-candidate acceptance. | Transfer to `0.9.8` so Documentation is reviewed after the Git-backed interface exists. Preserve completed shared interface corrections. |
| #75 recurring invoice drafts | Verified from retained evidence: enrollment, period claims, preview/apply, interface, versioned terms, stop and withdrawal are implemented. | Close the feature issue after posting the retained commits and records. Move only shared release/security/human evidence to #38/#39/#85. |
| #76 recurring recovery and acceptance | Verified from `planning/recurring-invoice-lifecycle-acceptance.md` and the clean backup/restore record. | Close the feature-specific issue. Its stated full release gate and technician review are shared candidate obligations, not missing recurring-invoice behavior. |
| #77 responsive epic | Most implementation is verified; the enforced ledger reports automated and recovery completion for the four broad groups. Human review and final release gate remain pending. | Retire the old implementation epic after its children are reconciled. Transfer shared human/final acceptance to `0.9.8`. |
| #78 foundations | Verified by the route inventory, data router, shared drawer/collection patterns, navigation guard and maintained-browser evidence. | Close as an implemented foundation; recurrence remains part of `0.9.8`. |
| #79 Assets | Automated and recovery status are complete in `acceptance.json`; human review is pending. | Close the implementation phase and transfer the four human profiles to `0.9.8`. |
| #80 Contracts and Networks | Automated and recovery status are complete. The Networks scope was deliberately corrected and completed under ADR 0104 rather than retaining the earlier IPAM-like surface. | Close against the corrected product boundary; transfer human profiles to `0.9.8`. |
| #81 remaining operational layouts | The enforced inventory records no pending implementation routes after Domains and Certificates. | Close the implementation phase; transfer shared human/release recurrence to `0.9.8`. |
| #82 Documentation and Files | Automated and recovery status are complete for the current model, but its storage and some interaction paths will change. | Close the database-first checkpoint or mark it superseded. Transfer read paths to `0.9.4`, authoring to `0.9.5`, files/publications to `0.9.7`, and final interface acceptance to `0.9.8`. |
| #83 financial/compliance/integration layouts | Retained responsive checkpoints cover invoices, compliance/evidence and integration workflows; #33 still independently owns invoice correction semantics. | Close the layout phase after evidence is posted. Transfer final human/release recurrence to `0.9.8`; do not use this issue to mask #33. |
| #84 shell and remaining surfaces | The enforced inventory records no pending routes after metadata, security/access, help/status, client entry and shell-overlay checkpoints. | Close the implementation phase; transfer shared final acceptance to `0.9.8`. |
| #85 responsive acceptance | Production image, automated workspace and recovery evidence are complete; `release_gate.status` and all sixteen human review rows remain pending. | Transfer/rewrite as the `0.9.8` acceptance issue. Do not perform final Documentation human review before migration. |
| #86 bounded collection APIs | Verified for the current responsive collections and exact-workspace summaries used by completed layouts. | Close the current API checkpoint. The new document collection is a derived-index read contract owned by `0.9.4`, not an extension of the old serializer. |
| #87 preferences | Persistence/isolation and visible collection use are retained across the responsive implementation. | Close the current foundation; require new v1 content-graph views to consume the same preference contract where applicable. |
| #88 navigation/draft protection | URL-backed records, guarded edits and shared navigation foundations are retained across completed routes. | Close the current foundation. Extend it for base-commit conflicts and Git-backed drafts in `0.9.5`. |

## `0.9.0` exit checklist

- [x] Implement issue #33 void-before-delivery and immutable credit notes.
- [x] Run focused service, database-trigger, authorization, portal, artifact,
  OpenAPI, UI and upgrade/downgrade migration evidence.
- [x] Run billing-specific and supported encrypted backup/restore rehearsals for
  the completed invoice correction boundary.
- [x] Run the tracked-code portions of the composed `0.9.0` gate: frontend tests
  and verification, automation contract tests, Wiki contract, responsive and
  Compose checks, workflow lint, backend lint/type checks, migration drift and
  OpenAPI validation.
- [x] Normalize `docs/PRODUCT_BOUNDARY.md` Markdown/Git row to
  the five-column capability contract and pass `make check` as one composed
  command.
- [x] Post retained evidence to #30–#32, #40, #75–#84 and #86–#88, then close or
  supersede each as described above.
- [x] Move #38, #39, #60 and #85 to the exact `0.9.8` candidate scope without
  closing them from current evidence.
- [x] Create the `0.9.0`–`0.9.8` milestones and attach every transferred
  acceptance criterion to exactly one issue owner.
- [x] Resolve #99 with the controlled Networks legacy-data cleanup result in
  [`network-legacy-cleanup-rehearsal.md`](network-legacy-cleanup-rehearsal.md).
  Lossless VLAN, rack, IP-asset and MAC-asset projections pass exact-workspace,
  `0.4.9` upgrade and clean backup/restore rehearsals. Compatibility rows remain
  intentionally retained; destructive removal requires a separate deprecation
  and operator-approved migration.
- [x] Resolve #100 by replacing the final parameterized-label exceptions with
  complete catalog messages. No wording required transfer to #60.
- [x] Run the strongest proportionate `0.9.0` composed gate after the code is
  complete.
- [x] Freeze the `0.9.0` baseline in an immutable commit, close #33, and update
  release, Wiki, risk and roadmap records from that same commit.

## `0.9.1` issue-ready implementation set

Create these as separate, ordered implementation issues. They are deliberately
smaller than one repository-foundation epic so migrations, storage custody and
recovery cannot disappear inside a generic “add Git” task.

### `V1-REP-001` — Repository identity and accepted-head authority (#92)

**Status: complete and locally validated 2026-10-03.**

**Outcome:** represent one managed repository for the MSP workspace and one for
each organization workspace without making repository state an authorization
authority.

**Included:** Django models/migration for stable repository UUID, exact workspace
binding, storage-relative path, lifecycle/health state, accepted commit, indexed
commit and last reconciliation state; explicit RLS/control-plane classification;
same-tenant and one-repository-per-workspace constraints.

**Acceptance:** duplicate/cross-workspace bindings fail at application and
database boundaries; no absolute host path or credential is exposed through the
API; migration and rollback preserve all `0.9.0` data; an accepted head cannot
name an unverified object.

**Evidence:** fresh migration, exact-prior upgrade, migration cycle, model-boundary
inventory, forced-RLS/control-plane tests and OpenAPI drift check.

### `V1-REP-002` — Persistent repository custody and initialization (#93)

**Status: complete and locally validated 2026-10-03.**

**Outcome:** create isolated local repositories in managed persistent storage for
new and existing workspaces without requiring a remote service.

**Included:** Compose/production volume, safe deterministic directory mapping by
repository UUID, atomic initialization, ownership/mode enforcement, idempotent
repair, and bootstrap/backfill for the existing MSP and organizations.

**Acceptance:** two organizations never share a repository root; traversal,
symlink and wrong-owner paths fail closed; initialization survives retry and
container recreation; application images retain read-only roots outside the
explicit repository volume.

**Evidence:** unit/path corpus, restricted-runtime integration, production-image
inspection and container-recreation rehearsal.

### `V1-REP-003` — Bounded repository service and commit protocol (#94)

**Status: complete and locally validated 2026-10-03.**

**Outcome:** give application code one safe interface for repository reads and
writes.

**Included:** per-repository locking, bounded Git invocation or reviewed library,
timeouts/output limits, safe environment, object validation, deterministic
service identity, expected-base compare-and-swap, staged-write cleanup and
value-minimized errors/logging.

**Acceptance:** concurrent writers cannot silently overwrite; failed commands
leave no accepted partial commit; a process interruption is recoverable; branch,
path, option-injection and malicious-repository inputs fail closed; callers
cannot execute arbitrary Git arguments.

**Evidence:** concurrency, interruption, hostile-path/ref, resource-limit,
logging-redaction and restricted-container tests.

### `V1-REP-004` — Portable workspace manifests and MSP organization directory (#95)

**Status: complete and locally validated 2026-10-03.**

**Outcome:** make each repository self-describing while keeping PostgreSQL
authoritative for organization identity and operational records.

**Included:** versioned `.tekdocs/repository.yml` and `workspace.yml`; an MSP-only
organization directory containing stable organization/workspace UUIDs, display
name, classifications and repository identity; deterministic generation and
validation.

**Acceptance:** no asset, serial, user, contract, permission, audit, token or
integration credential enters these manifests; organization repositories contain
only their own identity; renamed organizations retain stable UUIDs; unknown
forward-compatible fields are preserved according to the schema contract.

**Evidence:** schema fixtures, deterministic-byte checks, hostile-value/redaction
tests, cross-organization negative tests and rename/upgrade tests.

### `V1-REP-005` — Audit attribution, health and reconciliation (#96)

**Status: complete and locally validated 2026-10-03.**

**Outcome:** distinguish Git history from TekDocs audit evidence and expose safe
operational health.

**Included:** append-only audit mapping from authenticated action to resulting
commit, accepted-head reconciliation, missing/advanced/corrupt state detection,
last-known-good reads, readiness/system-status projections and operator-safe
repair guidance.

**Acceptance:** Git author text cannot impersonate an approver; health responses
contain no paths or content; mismatched repositories disable writes but permit
bounded diagnosis; no process silently advances an accepted head to the newest
commit.

**Evidence:** audit immutability, crash-window, mismatch matrix, corrupt-object,
permission-denial, logging and health API/browser tests.

### `V1-REP-006` — Repository-inclusive backup and network-isolated restore (#97)

**Status: complete and locally validated 2026-10-03.**

**Outcome:** extend supported encrypted recovery to the new canonical authored
content before any content migrates into it.

**Included:** complete Git bundles for every repository, unreachable retained
objects required by accepted evidence, repository/workspace/accepted-head
manifest, component checksums, existing PostgreSQL/media/artifact/key streams,
pre-destruction authentication and post-restore index/repository reconciliation.

**Acceptance:** restore succeeds without DNS, GitHub or another remote; missing,
swapped, advanced and truncated repository bundles fail before destructive
replacement; restored accepted heads match PostgreSQL; optional remotes are never
counted as backup completion.

**Evidence:** clean restore, wrong-key, corrupt/swapped component, missing-object,
database/repository mismatch, network-isolation and exact-prior upgrade rehearsals.

### `V1-REP-007` — Repository foundation composed acceptance (#98)

**Outcome:** prove the whole `0.9.1` boundary before parser or authoring work
starts.

**Fixture:** create one MSP workspace and at least two differently classified
organization workspaces; initialize all repositories; write deterministic
manifest commits; attempt cross-workspace access; interrupt and retry a commit;
recreate containers; capture and restore the encrypted recovery set on a clean,
network-isolated stack.

**Exit criteria:** every repository is isolated, correctly owned, bound to one
workspace and restored at the exact accepted head; derived/index state can be
empty at this slice; GitHub credentials and network access are absent; all new
risks have a disposition; setup, architecture, Wiki and release evidence agree.

## Explicitly not in `0.9.1`

- Markdown/frontmatter parsing or content indexing (`0.9.2`).
- Reusable fragments or inclusion resolution (`0.9.3`).
- Document/entity read APIs (`0.9.4`).
- UI authoring, renames or three-way merge presentation (`0.9.5`).
- Migration of existing document content (`0.9.6`).
- Publication conversion beyond proving repository objects can be backed up
  (`0.9.7`).
- GitHub authentication, remotes, pull requests or inbound synchronization
  (accepted post-1.0 backlog issue #107).

## Start condition for implementation

Issue #92 may now begin against the frozen `0.9.0` baseline and its recovery
evidence.
#93 depends on the identity model. #94 can proceed
beside storage once the path/binding contract is fixed. Manifest, health and
backup work then compose through #98.

## Local closeout evidence — 2026-10-03

- `make recurring-invoice-backup-rehearsal` passed after the fixture was extended
  to restore separately numbered issued invoices and credit notes, a voided
  invoice, signed PDF bytes, lifecycle links, balances, numbering sequences,
  forced RLS and database immutability.
- `make supported-recovery-rehearsal` passed against the production-target
  Compose contract, including encrypted artifacts, plaintext-secret checks,
  exact destructive confirmation, wrong-key rejection, independently named
  restore volumes, restored secret custody and full-stack health. The rehearsal
  exposed and fixed a restore defect that failed to build project-scoped service
  images before they were needed.
- The composed frontend gate passed 688 tests across 122 files, generated-client
  drift, lint, type checking, production build and bundle budgets. The automation
  contract suite passed 52 tests. Wiki, language, responsive, Compose, workflow,
  backend lint and type checks, migration drift, and OpenAPI generation also
  passed; OpenAPI retains four known operation-ID collision warnings and no
  errors.
- The focused invoice issue/delivery, full authorization matrix and migration
  stabilization suite completed successfully with one existing skip.
- After the local product-boundary status was normalized to the supported enum,
  `make check` passed end to end. This confirms the frontend test and build
  gates, generated API client, repository contracts, workflow lint, backend
  lint and types, migration drift, and OpenAPI validation in one composed run.
- GitHub milestones `0.9.0` through `0.9.8` now own the transition. Issues
  #92–#98 own the repository foundation, #101–#106 own the later implementation
  slices, #38/#39/#60/#85 own final-candidate acceptance, and #108 owns the
  `1.0.0` compatibility freeze. Optional per-organization GitHub repository
  integration is retained after 1.0 in #107.
- The #100 copy closeout replaced the final five parameterized button-label
  exceptions with complete catalog messages and removed the exception register.
  The all-component label scan, 686 frontend tests, UI-language contract and
  full composed `make check` gate pass.
- The #99 Networks rehearsal now inventories every retained compatibility type
  and relationship, runs the command under the restricted runtime role, adds the
  missing MAC-to-asset projection, and passes both `0.4.9` upgrade and clean
  backup/restore rehearsals. Destructive removal is explicitly outside this
  boundary; all legacy records remain intact.
