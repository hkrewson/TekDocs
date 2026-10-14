# Architecture deepening backlog

Accepted for backlog: 2026-10-12. Owner: maintainer. Source review:
`31daa14125a60dc3cbea86583abb1340fc3ecaee` and the temporary architecture HTML
report produced that day. This document preserves the actionable findings so
implementation does not depend on that temporary file.

Both items are `candidate`, not scheduled implementation or release blockers.
Consider them after 0.9.8 acceptance; do not interrupt its frozen validation for
refactoring. Assign a later release only after scoping. A newly demonstrated
security/data-integrity defect may preempt that order, but does not authorize
the entire refactor. These refine the repository/storage work associated with
#40; no new GitHub issue has been created and neither item closes #40.

| ID | Recommendation | Order | Scheduling gate |
| --- | --- | --- | --- |
| TD-BACKLOG-ARCH-001 | Deepen retained-publication reads — Strong | First | Select initial callers and preserve integrity checks |
| TD-BACKLOG-ARCH-002 | Deepen authority-aware document reads — Worth exploring | Second | Prove shared semantics without widening audience access |

## TD-BACKLOG-ARCH-001 — Deepen retained-publication reads

Status: `candidate`. Recommendation: **Strong**. Dependency category:
local-substitutable. No dependency on ARCH-002.

### Problem and evidence

The retained-publication read interface leaves integrity choreography in its
callers. Staff review and STATIC export verify complete evidence, then separately
open and check returned bytes. Understanding one successful download requires
following both paths. The recent unreadable-empty-file defect illustrates why
storage failure must not be represented as valid empty bytes.

Start at these paths (line numbers refer to the reviewed commit):

- `backend/apps/core/repository_publication_views.py:355,393,619`: review PDF,
  attachment and STATIC export callers.
- `backend/apps/core/repository_publication_evidence.py:575,699,760`: primary
  history, PDF and ordinary attachment reads/checks.
- `backend/apps/core/tests/test_publication_read_failures.py:15`: regression
  patches permission, lookup and initial verification to isolate the later read.

### Intended change and limits

Concentrate retained-publication reading, descriptor consistency, bounded byte
reads and integrity failure handling in a deep module. Keep authorization at
the appropriate caller and keep format-specific verification in the
implementation. Agree the interface before coding; this brief does not prescribe
function names or a generic storage framework.

Whole-evidence signature/chain verification and verification of bytes actually
returned are distinct obligations. Preserve both. Storage can change after
initial verification: a cached `verified=True` must not replace checking the
bytes delivered. Do not assume that reducing read count is itself correctness.

Retain existing managed-file IDs, Workspace ownership, signed formats, immutable
history, scanner requirements and private storage. ADRs 0114 and 0108 remain in
force. No new attachment table, custody model, schema, remote storage provider or
publication format belongs in this item. Do not expand the first slice into all
attachment upload/copy/download code merely because similar checks exist there.

The existing storage adapter and failing-storage/BytesIO test doubles provide
real variation. Introduce no hypothetical S3 adapter. Use real private-file
storage and PostgreSQL for integration checks; doubles alone do not prove custody
or authorization.

### Delivery sequence

1. Inventory each selected caller's signature, manifest, ownership, length,
   checksum, response and failure obligations; select a bounded first slice.
2. Preserve/reproduce current valid-empty and failed-read behavior. Add a case
   where storage fails or changes after initial evidence verification.
3. Agree the module's interface and migrate one caller with equivalent checks.
4. Migrate the remaining selected callers. Delete duplicate choreography only
   after tests through the shared interface cover it. Keep independent
   authorization, signed-evidence and database guard tests.
5. Compare the old/new call paths and record what knowledge callers no longer
   need. A shallow forwarding module is not completion.

### Acceptance

- [ ] Valid empty and nonempty files remain readable; failed opens/reads,
  truncation, oversized bytes and checksum mismatch fail closed.
- [ ] Mutation/unavailability after initial verification cannot return unchecked
  bytes; malformed descriptors and source/owner mismatch remain refused.
- [ ] Altered signatures, manifests or historical primary files remain refused;
  existing evidence formats remain readable without rewriting history.
- [ ] Existing permission, sibling-organization, cross-tenant and portal-denial
  tests pass. Response status, download headers and cache controls are preserved.
- [ ] Regression tests cross the same interface callers use, rather than
  patching away unrelated orchestration merely to reach a read failure.
- [ ] Docker publication/review/export tests and `make test-document-error-security`
  pass; run the complete affected composition/publication suites beyond that
  target's excluded upgrade cases. Rehearse repository-inclusive recovery if
  shared verification changes affect recovery, and record exact evidence.
- [ ] Locality improves: read-failure rules concentrate in one implementation.
  Leverage improves across the selected callers without weakening verification.

Deletion test: removing repeated caller choreography concentrates complexity
inside the module. Removing the verifier would scatter essential invariants
and is explicitly not the recommendation.

## TD-BACKLOG-ARCH-002 — Deepen authority-aware document reads

Status: `candidate`. Recommendation: **Worth exploring**. Dependency category:
local-substitutable. Second in priority, not technically dependent on ARCH-001.

### Problem and evidence

Review and search separately interpret authority state, accepted/indexed
readiness, composition and portable metadata. The interface for “current
document” is spread across callers, increasing the knowledge needed to change
authority behavior safely. Similar-looking branches are not necessarily
interchangeable: review reads the `all` composition while search filters records
and metadata for its authorized Workspace.

Starting paths at the reviewed commit:

- `backend/apps/core/document_operations.py:31,113`: reviewed Markdown and
  portable metadata consistency.
- `backend/apps/core/document_views.py:361`: authority-aware search and index
  readiness.
- `backend/apps/core/documents.py:62,75` and
  `backend/apps/core/content_authoring.py:290`: contrasting writer guards that
  must remain intact, not targets for an automatic read/write merger.
- `backend/apps/core/document_authority_handoff.py:34,91`: rollback projection
  and transactional transitions; separate responsibilities to preserve.

### Intended change and limits

First map authority/readiness rules and caller-specific projections. Explore a
deep read module that concentrates shared current-content selection while
preserving the distinctions callers genuinely need. Choose its interface only
after the comparison. Reject the extraction if it merely forwards the same
branches and increases navigation without hiding complexity.

Legacy and repository reads are existing implementations, not justification for
a universal persistence abstraction. Establish which behavior actually varies
before introducing an adapter seam. Test with real PostgreSQL and Git; do not
replace the revision/locking guarantees with in-memory approximations.

Preserve exact Workspace and stable content identity, field permissions,
audiences, accepted/indexed equality and stale-index refusal. Repository-owned
content must never fall back to stale legacy content. Do not widen review's
composition visibility to search or ordinary readers.

ADR 0105's Git-content/PostgreSQL-workflow split stays unchanged. ADR 0115 was
still marked proposed during review: clarify its status with the maintainer if
the design needs to rely on a new decision; this backlog does not approve it.
Do not merge handoff, rollback, review, search and authoring into one module,
remove database guards, change transition locking, or activate handoff. No new
schema or public contract is assumed.

### Delivery sequence

1. Produce a caller/rule matrix covering legacy-only, copied-but-legacy-owned,
   promoted and Git-only documents; include missing/stale index and denied reads.
2. Separate genuinely shared selection rules from caller-specific audience,
   query, composition and workflow behavior. Confirm the smallest useful scope.
3. Agree the interface and capture current behavior through caller-visible tests.
4. Migrate one read path, then a second only after proving the shared semantics.
   Preserve bulk search behavior; avoid per-document query or Git-read expansion.
5. Remove duplicated selection knowledge, demonstrate locality/leverage, and
   retain transition, writer-guard and review-pinning regressions.

### Acceptance

- [ ] Legacy-only, copied, promoted and Git-only identities resolve consistently
  through the selected read paths without manufacturing legacy owners.
- [ ] Missing, mismatched or stale accepted/indexed state fails closed for
  repository-owned documents; no silent legacy fallback is introduced.
- [ ] Exact-Workspace, sibling-organization, cross-tenant, field and audience
  restrictions remain unchanged, including search results and review content.
- [ ] Revision-pinned review remains bound to the content reviewed; later edits
  cannot silently validate an earlier approval.
- [ ] Promotion/rollback, database guards and legacy/repository writer refusal
  tests remain green despite being outside the implementation scope.
- [ ] Docker `test-content-read`, `test-content-authoring`, and
  `test-content-composition` gates plus affected document-operations and migration
  inventory suites pass; affected query/latency budgets do not regress.
- [ ] At least two callers lose duplicated authority/readiness knowledge.
  A forwarding-only module or broader interface without leverage is rejected.

## Closeout expectations

Neither entry authorizes implementation, GitHub issue publication, deployment,
or changes to 0.9.8 acceptance. When scheduled, name the release/issue, settle
open interface choices, and record before/after paths, preserved tests, Docker
evidence and any operational documentation changes. Keep the recommendation
strength distinct from proof of a new runtime defect.
