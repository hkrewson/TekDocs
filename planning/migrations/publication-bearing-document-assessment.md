# Publication-bearing document: read-only assessment and implementation plan

October 26, 2026. Scope: #105 migration/coexistence and #106 publication parity.
Authorized: read-only production assessment and a scoped implementation plan.
Not authorized: implementation, import, promotion, editorial changes, publication
changes, commit, push or another production update.

## Current baseline

Production runs published 0.9.15 at `6a06b2a`. The operator confirmed that the
first promoted guide now opens correctly in Documentation after the reader-ID
fix. This closes that reported loading defect, not all first-guide editorial,
rollback or publication acceptance. Earlier planning notes describing the first
handoff as entirely pending are historical.

## Verified production assessment

Both queries ran inside explicit PostgreSQL READ ONLY transactions through the
existing production backend and tenant/MSP scope. Output was limited to counts,
blocker codes and verification booleans. No document titles, identifiers, bodies,
artifact bytes, credentials or signatures were retained here.

- Exactly one MSP document reports `publication_parity_required`.
- It has one placement and no other inventory reason.
- The repository reports no blockers; its accepted and indexed heads agree.
- It retains one `msp_internal` publication and one PDF artifact.
- Publication digest, signature, key fingerprint and trusted-key checks pass.
- Retained artifact custody verifies successfully.
- No superseding publication is present in the inspected history.

No production content, database records, repository commits, files, publication
controls or authority state changed. The assessment does not imply promotion
eligibility or verify arbitrary publication shapes.

## Source findings

`document_migration_inventory.py` unconditionally adds
`publication_parity_required` when any legacy publication exists.
`prepare_document_import` respects that blocker, so this record cannot currently
be copied through the supported import path.
`document_migration_coexistence.py` also adds
`legacy_publication_history_present` to authority-handoff blockers.
The ordinary `publish_document` path rejects Git-authoritative documents until
publication parity exists. Existing repository publication/evidence primitives
are available, but their existence alone does not prove the normal document
workflow or retained legacy-history transition.

The current regression
`test_migration_status_identifies_retained_legacy_publication_history` explicitly
proves refusal and legacy authority. It is an intentional guard, not an assertion
to remove. No failure or missing-data defect is claimed by this assessment.

## Next bounded implementation: retained-publication parity assessment

Build a read-only, exact-owner parity assessment for the inspected class:
one ordinary owned-placement document with retained internal STATIC publication
history. Initially report readiness evidence without clearing import or
promotion blockers. This isolates the evidence contract before changing the
supported authority boundary.

Acceptance:

1. Reproduce the production shape with synthetic content and a retained PDF in
   the existing Docker development project/test database. Capture the existing
   import and promotion refusals unchanged.
2. Verify every historical snapshot independently of the current editable body:
   stable publication/artifact identities, signed payload/digest, trusted key,
   retained byte hashes, original audience, retention and append-only control
   history. Do not require an old publication's text to equal today's draft.
3. Missing/corrupt artifacts, untrusted signatures, cross-tenant/Workspace
   ownership, inconsistent supersession and unsupported publication shapes must
   yield explicit reasons. No mutation or publication recreation is permitted.
4. Keep status/preview execution valid inside READ ONLY transactions, with
   value-minimized reporting and no new permission grant.
5. Add positive, negative, tenant/client-denial and runtime-role tests. Keep
   the existing refusal regression until the complete lifecycle is supported.

Likely seams: a dedicated publication-parity service called by coexistence
status, with tests alongside migration inventory and publication integrity.
Use existing verification functions rather than a second signature format or
copy of retained publication content. Determine whether additional durable
parity state is required during design; any schema change must use Django
migrations. No schema change is assumed by this plan.

## Subsequent lifecycle gate before enabling promotion

A successful history verifier is necessary but insufficient. Before the
inventory/import and authority guards can conditionally accept this class:

- Freeze the exact parity/plan identity and recheck under the established
  repository/database lock order to reject changes since preview.
- Preserve old publications and their controls/artifacts unchanged through
  shadow copy, promotion, allowed fragment-body edits and rollback.
- Prove the normal supported publication operation after promotion uses the
  accepted Git composition and exact dependency revisions. Existing snapshots
  remain historical; new snapshots append rather than rewrite them.
- Prove supersession, approval/withdrawal and retained artifact reads preserve
  authorization and history for the supported internal-publication scope.
- Include publication operations occurring after promotion in rollback design;
  rollback must not drop, rewrite or orphan those records.
- Prove fresh/0.8.46-upgraded fixture parity and independent network-isolated
  recovery with matching Git, PostgreSQL, publication history and retained PDF
  hashes. Client-visible publications, templates, shared/cross-Workspace sources
  and more complex shapes stay blocked until their own evidence is complete.

Do not simply discard `publication_parity_required` or
`legacy_publication_history_present`, delete history, or make an unsigned copy
of the PDF to satisfy migration eligibility. Keep fail-closed behavior until
the supported lifecycle is proven.

## Validation and delivery plan

Use the existing `tekdocs` project and `docker compose exec` selections for
migration inventory/runtime RLS, publication integrity and content authoring/read
regressions. Inspect Make commands before execution. The aggregate
`document-migration-release-gate` and supported upgrade/recovery/image rehearsals
must be confirmed in hosted CI where their separate environments are permitted;
no additional local stack is authorized. Align OpenAPI, ADR 0115, roadmap,
release notes and internal operator guidance with the implemented scope.

Freeze and release the validated implementation before preparing a new read-only
production preview. Any eventual copy/promotion needs a separately reviewed plan,
backup, rollback procedure and explicit production mutation authorization.
No external pilot, GitHub repository integration or end-user authority UI is
added to this slice.

## Disposition

Verified: the inspected production history and PDF are intact; the sole inventory
reason is the explicit publication-parity guard.
Inferred: this simple internal-publication case is a useful first parity fixture,
because it avoids template/client-delivery and supersession complexity.
Blocked by current implementation: supported import/promotion and normal
post-promotion publication parity. No release, promotion or broader migration
completion is claimed.

## Read-only assessment implementation — October 26, 2026

The maintainer subsequently authorized the next bounded implementation. Source
now includes `document_migration_publications.assess_retained_publications`,
consumed by the existing exact-owner staff migration-status route. The additive
`publication_history` field contains `state` (`absent`, `verified`, `blocked`),
publication/artifact counts, sorted reason codes and a nullable SHA-256 evidence
fingerprint. No publication identifiers, text, actor identities or signatures
are returned in that field. OpenAPI and generated TypeScript describe it.

Supported evidence is limited to ordinary single-owned-placement documents with
internal STATIC v2/v3/v4 snapshots and one retained PDF per snapshot. Other shapes
report unsupported. Each snapshot is verified using the existing signature and
artifact-custody functions, with exact document/Workspace ownership and signed
metadata correspondence. Supersession must stay within the inspected history,
advance publication time and avoid self-links. Control history must retain a
submitted event and valid scoped actions/timing. The fingerprint binds retained
publication/artifact identities and append-only control records; it is diagnostic,
not a signed approval, durable reservation or cryptographic attestation of the
unsigned control-event table.

The current draft need not equal an older signed snapshot. Changes to retained
history or controls change the fingerprint; missing/corrupt bytes and failed
verification return no fingerprint. All assessment queries are scoped; a record
hidden by the runtime role's tenant scope is refused, not treated as absent.
No schema migration, new permission or storage mutation is introduced.

`publication_parity_required` still blocks import, and
`legacy_publication_history_present` still blocks promotion. Successful history
verification does not enable ordinary publication after promotion. No copy,
authority transition or production execution of this new code is authorized.
No new public Wiki migration workflow is required: ADR 0115 keeps this staff
operator diagnostic internal. Existing Wiki drafts are preserved.

Synthetic tests cover read-only runtime-role execution, repeatable evidence,
unchanged signed history, continued import/promotion refusal, missing/corrupt PDF
bytes, untrusted signing keys, historical draft independence, legitimate
supersession/withdrawal fingerprint changes, corrupted loaded metadata/control
records, unsupported audience, and wrong-Workspace/foreign-tenant denial.
Corrupt-record injection changes loaded objects only; append-only database guards
are never disabled and retained database history is unchanged.

Verified locally: all 51 Docker tests passed across migration inventory, the
13-case publication assessment module, runtime RLS, API contracts and publication
read failures. This is the expanded `test-document-migration-inventory` Make
selection plus the API/publication failure modules, executed with
`docker compose exec -T migrate pytest ... --reuse-db` to reuse the existing
project and separate test database. Log: `/tmp/tekdocs-publication-parity-final.log`.
The focused assessment module also passed before the combined gate.

Ruff passed for the backend; mypy found no issues in 271 source files. Django
reported no migration changes. Docker schema generation had zero errors and four
existing operation-ID warnings; generated API agreement and frontend type checking
passed. All 120 tooling tests passed (three optional checks skipped), including
shard-discovery coverage for the new test module. Wiki page/link and diff checks
passed. The full document-migration release gate's upgrade, recovery and image
rehearsals remain for hosted CI because their local scripts create separate
stacks; this slice introduces no local exception or new runtime volume.

Verified: supported retained history and failures at the real storage/signature,
API, read-only transaction and runtime-role boundaries. Inferred: the same report
will diagnose the inspected production shape after a future release. Blocked
pending release and separate authorization: running the new code in production
and any publication-bearing import/promotion or publication lifecycle change. The original
focused runtime-role test first failed because its system-principal binding
inherited a user actor; explicitly supplying `actor_user_id=None` corrected that
fixture prerequisite without relaxing read-only execution or the role boundary.

The implementation remains uncommitted on main. Production remains on 0.9.15;
this code has not been deployed. Further lifecycle work remains necessary before
publication-bearing migration can be enabled.

## Subsequent bounded lifecycle work

The next local implementation adds signed internal snapshots for an already
promoted simple guide and a verified-v5-only rollback exception. It does not
clear legacy-history import/promotion blockers. See
[internal Git publication lifecycle](internal-git-publication-lifecycle.md) for
the supported shape, migration, tests, recovery-fixture extension and hosted
validation still required. The v2/v3/v4-only description above records the
initial read-only assessment slice; its implementation now also recognizes
verified v5 source descriptors.
